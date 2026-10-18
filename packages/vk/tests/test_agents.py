"""Tests for the PydanticAI runtime, driven by `FunctionModel` (no network)."""

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from vk.agents import adapt, run_typed
from vk.config import Config
from vk.tooling import Tool, ToolError


class Verdict(BaseModel):
    verdict: str
    note: str | None


def make_cfg(budget: int = 1000) -> Config:
    return Config(
        repo="o/r",
        github_token="t",
        model="test:m",
        clan_models={},
        state_dir=Path("/tmp/vk-test"),
        max_output_tokens=budget,
    )


def final(info: AgentInfo, args: dict[str, Any], **kw: Any) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)], **kw)


def tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


def run(
    model: FunctionModel, tools: list[Tool], output_type: type = Verdict, budget: int = 1000
) -> Any:
    return run_typed("analyst", output_type, "be brief", "go", tools, make_cfg(budget), model=model)


ECHO = Tool(
    "echo",
    "echo",
    {"type": "object", "properties": {"x": {"type": "integer"}}},
    lambda a: {"got": a["x"]},
)


def test_tool_call_then_typed_output() -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = tool_returns(messages)
        if not returns:
            return ModelResponse(parts=[ToolCallPart("echo", {"x": 1})])
        assert returns[0].content == '{"got": 1}'
        return final(info, {"verdict": "ok", "note": None})

    assert run(FunctionModel(fn), [ECHO]) == Verdict(verdict="ok", note=None)


def test_invalid_output_is_retried() -> None:
    calls = 0

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return final(info, {"verdict": "ok"})  # missing required `note`
        return final(info, {"verdict": "ok", "note": "x"})

    assert run(FunctionModel(fn), []) == Verdict(verdict="ok", note="x")
    assert calls == 2


def test_invalid_output_gives_up_after_the_retry_budget() -> None:
    calls = 0

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        return final(info, {"verdict": "ok"})  # always missing `note`

    with pytest.raises(UnexpectedModelBehavior):
        run(FunctionModel(fn), [])
    assert calls == 4  # the first attempt plus 3 output retries


@pytest.mark.parametrize("exc", [ToolError("nope"), RuntimeError("nope")])
def test_tool_failure_is_visible_and_run_continues(exc: Exception) -> None:
    def boom(_: dict[str, Any]) -> Any:
        raise exc

    seen: list[ToolReturnPart] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = tool_returns(messages)
        if not returns:
            return ModelResponse(parts=[ToolCallPart("boom", {})])
        seen.extend(returns)
        return final(info, {"verdict": "ok", "note": None})

    tool = Tool("boom", "b", {"type": "object"}, boom)
    assert run(FunctionModel(fn), [tool]).verdict == "ok"
    assert "nope" in str(seen[0].content)


def test_tool_failure_does_not_use_retry_budget() -> None:
    def boom(_: dict[str, Any]) -> Any:
        raise ToolError("nope")

    tool = Tool("boom", "b", {"type": "object"}, boom)
    turns = 0

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal turns
        turns += 1
        if turns <= 5:  # more failures than the default retry budget of 1
            return ModelResponse(parts=[ToolCallPart("boom", {})])
        return final(info, {"verdict": "ok", "note": None})

    assert run(FunctionModel(fn), [tool]).verdict == "ok"


def test_non_string_result_is_json_text() -> None:
    echo: Callable[..., Any] = adapt(ECHO).function
    text_tool = Tool("t", "t", {"type": "object"}, lambda _: "plain")
    plain: Callable[..., Any] = adapt(text_tool).function
    assert echo(x=2) == '{"got": 2}'
    assert plain() == "plain"


def test_output_token_budget_exceeded() -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return final(info, {"verdict": "ok", "note": None}, usage=RequestUsage(output_tokens=50))

    with pytest.raises(UsageLimitExceeded):
        run(FunctionModel(fn), [], budget=10)


def test_plain_text_output() -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("final answer")])

    assert run(FunctionModel(fn), [], output_type=str) == "final answer"


def test_tool_calls_in_one_turn_run_in_order_without_overlap() -> None:
    events: list[str] = []

    def slow(_: dict[str, Any]) -> str:
        events.append("a start")
        time.sleep(0.05)
        events.append("a end")
        return "a"

    def quick(_: dict[str, Any]) -> str:
        events.append("b start")
        events.append("b end")
        return "b"

    tools = [Tool("a", "a", {"type": "object"}, slow), Tool("b", "b", {"type": "object"}, quick)]

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not tool_returns(messages):
            return ModelResponse(parts=[ToolCallPart("a", {}), ToolCallPart("b", {})])
        return final(info, {"verdict": "ok", "note": None})

    assert run(FunctionModel(fn), tools).verdict == "ok"
    assert events == ["a start", "a end", "b start", "b end"]


def test_token_usage_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return final(
            info,
            {"verdict": "ok", "note": None},
            usage=RequestUsage(input_tokens=100, output_tokens=5),
        )

    with caplog.at_level(logging.INFO, logger="vk.agents"):
        run(FunctionModel(fn), [])
    lines = [r.getMessage() for r in caplog.records]
    assert (
        "agent analyst done requests=1 input_tokens=100 output_tokens=5 total_tokens=105" in lines
    )
