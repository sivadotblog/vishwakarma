"""PydanticAI runtime: adapts VK tools and runs typed agents."""

import json
import logging
from collections.abc import Sequence
from typing import Any

from pydantic_ai import Agent, ModelMessage, ModelResponse, ToolOutput, capture_run_messages
from pydantic_ai import Tool as AiTool
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.models import Model
from pydantic_ai.usage import RequestUsage, RunUsage, UsageLimits

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
        # Tools share one clone, so keep the old in-order semantics: never run calls concurrently.
        sequential=True,
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
    llm = model or build_model(cfg, name)
    agent: Agent[None, T] = Agent(
        llm,
        name=name,
        instructions=instructions,
        output_type=output_type if output_type is str else ToolOutput(output_type),
        tools=[adapt(t) for t in tools],
        capabilities=list(capabilities),
        retries={"output": 3},
    )
    model_name = llm if isinstance(llm, str) else llm.model_name
    log.info("agent %s start model=%s", name, model_name)
    usage = RunUsage()
    with capture_run_messages() as messages:
        try:
            result = agent.run_sync(
                message,
                usage=usage,
                usage_limits=UsageLimits(
                    output_tokens_limit=cfg.max_output_tokens, request_limit=None
                ),
            )
        except Exception as exc:
            # Failed runs still spent tokens: log them before the error propagates.
            _log_usage(name, model_name, messages, usage, failure=exc)
            raise
    _log_usage(name, model_name, messages, usage)
    return result.output


def _log_usage(
    name: str,
    model_name: str,
    messages: list[ModelMessage],
    usage: RunUsage,
    failure: Exception | None = None,
) -> None:
    """Log one line per model request, then the agent's totals (marked failed on an error)."""
    per_request = [m.usage for m in messages if isinstance(m, ModelResponse)]
    # A response that trips a usage limit is counted in `usage` but never reaches the messages.
    extra = RequestUsage(
        input_tokens=usage.input_tokens - sum(u.input_tokens for u in per_request),
        output_tokens=usage.output_tokens - sum(u.output_tokens for u in per_request),
    )
    if extra.total_tokens > 0:
        per_request.append(extra)
    for turn, request in enumerate(per_request, start=1):
        log.info(
            "llm %s model=%s turn=%d prompt_tokens=%d completion_tokens=%d total_tokens=%d",
            name,
            model_name,
            turn,
            request.input_tokens,
            request.output_tokens,
            request.total_tokens,
        )
    status = "ok" if failure is None else f"failed error={type(failure).__name__}"
    log.log(
        logging.INFO if failure is None else logging.WARNING,
        "agent %s done status=%s turns=%d prompt_tokens=%d completion_tokens=%d total_tokens=%d",
        name,
        status,
        len(per_request),
        usage.input_tokens,
        usage.output_tokens,
        usage.total_tokens,
    )
