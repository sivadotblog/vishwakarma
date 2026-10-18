"""PydanticAI runtime: adapts VK tools and runs typed agents."""

import json
import logging
from collections.abc import Sequence
from typing import Any

from pydantic_ai import Agent, ToolOutput
from pydantic_ai import Tool as AiTool
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from vk.config import Config, build_model
from vk.tooling import Tool

log = logging.getLogger(__name__)


def adapt(tool: Tool) -> AiTool[None]:
    """Wrap a VK `Tool` so any failure goes back to the model without using retry budget."""

    def call(**kwargs: Any) -> str:
        log.info("tool %s", tool.name)
        log.debug("tool %s args=%s", tool.name, kwargs)
        try:
            result = tool.fn(kwargs)
        except Exception as exc:  # tool failures are model-visible by design
            log.warning("tool %s failed: %s", tool.name, exc)
            raise ToolFailed(str(exc)) from exc
        return result if isinstance(result, str) else json.dumps(result, default=str)

    return AiTool.from_schema(
        function=call,
        name=tool.name,
        description=tool.description,
        json_schema=tool.parameters,
        takes_ctx=False,
    )


def run_typed[T](
    name: str,
    output_type: type[T],
    instructions: str,
    message: str,
    tools: Sequence[Tool],
    cfg: Config,
    capabilities: Sequence[AbstractCapability[None]] = (),
    model: Model | str | None = None,
) -> T:
    """Run one agent to completion and return its output (`str` for plain text).

    `model` overrides `build_model` and is the seam tests use to inject a fake model.
    """
    agent: Agent[None, T] = Agent(
        model or build_model(cfg, name),
        name=name,
        instructions=instructions,
        output_type=output_type if output_type is str else ToolOutput(output_type),
        tools=[adapt(t) for t in tools],
        capabilities=list(capabilities),
        retries={"output": 3},
    )
    log.info("agent %s start", name)
    result = agent.run_sync(
        message,
        usage_limits=UsageLimits(output_tokens_limit=cfg.max_output_tokens, request_limit=None),
    )
    usage = result.usage
    log.info(
        "agent %s done requests=%d input_tokens=%d output_tokens=%d total_tokens=%d",
        name,
        usage.requests,
        usage.input_tokens,
        usage.output_tokens,
        usage.total_tokens,
    )
    return result.output
