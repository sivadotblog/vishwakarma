"""Tests for the PydanticAI runtime, driven by `FunctionModel` (no network)."""

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from vk.agents import adapt, compaction, run_typed
from vk.config import ClanOverride, Config
from vk.tooling import Tool, ToolError

from .helpers import SETTINGS, with_settings


class Verdict(BaseModel):
    verdict: str
    note: str | None


MAX_OUTPUT_CHARS = SETTINGS.tools.max_output_chars


def make_cfg(
    budget: int = 1000, input_budget: int = 2_000_000, total_budget: int | None = None
) -> Config:
    cfg = Config(repo="o/r", github_token="t", state_dir=Path("/tmp/vk-test"))
    defaults = {
        "model": "test:m",
        "max_output_tokens": budget,
        "max_input_tokens": input_budget,
        "max_total_tokens": total_budget,
    }
    return with_settings(cfg, defaults=defaults)


def final(info: AgentInfo, args: dict[str, Any], **kw: Any) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)], **kw)


def tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


def run(
    model: FunctionModel,
    tools: list[Tool],
    output_type: type = Verdict,
    budget: int = 1000,
    input_budget: int = 2_000_000,
    total_budget: int | None = None,
) -> Any:
    cfg = make_cfg(budget, input_budget, total_budget)
    return run_typed("analyst", output_type, "be brief", "go", tools, cfg, model=model)


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
    echo: Callable[..., Any] = adapt(ECHO, MAX_OUTPUT_CHARS).function
    text_tool = Tool("t", "t", {"type": "object"}, lambda _: "plain")
    plain: Callable[..., Any] = adapt(text_tool, MAX_OUTPUT_CHARS).function
    assert echo(x=2) == '{"got": 2}'
    assert plain() == "plain"


def test_output_token_budget_exceeded() -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return final(info, {"verdict": "ok", "note": None}, usage=RequestUsage(output_tokens=50))

    with pytest.raises(UsageLimitExceeded):
        run(FunctionModel(fn), [], budget=10)


def test_input_token_budget_exceeded_raises_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        usage = RequestUsage(input_tokens=600, output_tokens=1)
        if not tool_returns(messages):
            return ModelResponse(parts=[ToolCallPart("echo", {"x": 1})], usage=usage)
        return final(info, {"verdict": "ok", "note": None}, usage=usage)

    with caplog.at_level(logging.INFO, logger="vk.agents"), pytest.raises(UsageLimitExceeded):
        run(FunctionModel(fn), [ECHO], input_budget=1000)
    lines = [r.getMessage() for r in caplog.records]
    assert any(
        line.startswith("agent analyst done status=failed error=UsageLimitExceeded")
        and "prompt_tokens=1200" in line
        for line in lines
    )


def test_total_token_budget_exceeded() -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        usage = RequestUsage(input_tokens=400, output_tokens=200)
        return final(info, {"verdict": "ok", "note": None}, usage=usage)

    with pytest.raises(UsageLimitExceeded):
        run(FunctionModel(fn), [], total_budget=500)


def test_budgets_come_from_the_clan_settings() -> None:
    cfg = Config(repo="o/r", github_token="t", state_dir=Path("/tmp/vk-test"))
    cfg = replace(
        cfg,
        settings=cfg.settings.model_copy(
            update={"clans": {"analyst": ClanOverride(model="test:m", max_output_tokens=10)}}
        ),
    )

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return final(info, {"verdict": "ok", "note": None}, usage=RequestUsage(output_tokens=50))

    with pytest.raises(UsageLimitExceeded):
        run_typed("analyst", Verdict, "be brief", "go", [], cfg, model=FunctionModel(fn))
    assert run_typed("reviewer", Verdict, "be brief", "go", [], cfg, model=FunctionModel(fn))


def test_input_budget_defaults_to_two_million() -> None:
    assert SETTINGS.defaults.max_input_tokens == 2_000_000


def test_a_large_tool_result_is_capped_with_a_note() -> None:
    big = Tool("big", "b", {"type": "object"}, lambda _: {"blob": "x" * 100_000})
    small = Tool("small", "s", {"type": "object"}, lambda _: "short")
    capped: Callable[..., Any] = adapt(big, MAX_OUTPUT_CHARS).function
    untouched: Callable[..., Any] = adapt(small, MAX_OUTPUT_CHARS).function
    text = capped()
    assert len(text) < MAX_OUTPUT_CHARS + 100
    assert text.startswith('{"blob": "xxx')
    assert text.endswith("characters]") and "[truncated " in text
    assert untouched() == "short"


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


def test_per_request_usage_and_totals_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        usage = RequestUsage(input_tokens=100, output_tokens=5, cache_read_tokens=60)
        if not tool_returns(messages):
            return ModelResponse(parts=[ToolCallPart("echo", {"x": 1})], usage=usage)
        return final(info, {"verdict": "ok", "note": None}, usage=usage)

    with caplog.at_level(logging.INFO, logger="vk.agents"):
        run(FunctionModel(fn), [ECHO])
    lines = [r.getMessage() for r in caplog.records]
    assert any(line.startswith("agent analyst start model=") for line in lines)
    for turn in (1, 2):
        assert any(
            line.startswith("llm analyst model=")
            and line.endswith(
                f"turn={turn} prompt_tokens=100 cached_tokens=60 completion_tokens=5"
                " total_tokens=105"
            )
            for line in lines
        )
    assert (
        "agent analyst done status=ok turns=2 prompt_tokens=200 cached_tokens=120"
        " completion_tokens=10 total_tokens=210" in lines
    )


def test_usage_is_logged_when_the_run_fails(caplog: pytest.LogCaptureFixture) -> None:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return final(
            info,
            {"verdict": "ok", "note": None},
            usage=RequestUsage(input_tokens=100, output_tokens=50),
        )

    with caplog.at_level(logging.INFO, logger="vk.agents"), pytest.raises(UsageLimitExceeded):
        run(FunctionModel(fn), [], budget=10)
    lines = [r.getMessage() for r in caplog.records]
    assert any(
        line.startswith("llm analyst model=")
        and line.endswith(
            "turn=1 prompt_tokens=100 cached_tokens=0 completion_tokens=50 total_tokens=150"
        )
        for line in lines
    )
    assert (
        "agent analyst done status=failed error=UsageLimitExceeded turns=1 prompt_tokens=100"
        " cached_tokens=0 completion_tokens=50 total_tokens=150" in lines
    )


def test_tool_calls_are_logged_with_a_short_argument(caplog: pytest.LogCaptureFixture) -> None:
    sink = Tool("t", "t", {"type": "object"}, lambda _: "ok")
    call: Callable[..., Any] = adapt(sink, MAX_OUTPUT_CHARS).function
    with caplog.at_level(logging.INFO, logger="vk.agents"):
        call(path="src/a.py", content="SECRET BODY")
        call(command="x" * 200)
        call(other=1)
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert lines == ["tool t path=src/a.py", f"tool t command={'x' * 80}", "tool t "]
    assert not any("SECRET" in line for line in lines)


def test_compaction_follows_the_settings() -> None:
    on = make_cfg()
    off = with_settings(on, compaction={"enabled": False})
    names = [type(c).__name__ for c in compaction(on)]
    assert names == ["DeduplicateFileReads", "ClearToolResults"]
    assert compaction(off) == []


def test_compaction_clears_old_tool_results_during_a_run() -> None:
    cfg = with_settings(
        make_cfg(),
        compaction={"clear_after_tokens": 1, "keep_pairs": 1, "min_clear_tokens": 1},
    )
    big = Tool("big", "b", {"type": "object"}, lambda _: "y" * 20_000)
    seen: list[list[str]] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append([str(p.content) for p in tool_returns(messages)])
        if len(seen) < 4:
            return ModelResponse(parts=[ToolCallPart("big", {})])
        return final(info, {"verdict": "ok", "note": None})

    run_typed("analyst", Verdict, "be brief", "go", [big], cfg, model=FunctionModel(fn))
    *older, newest = seen[-1]
    assert older and all(c == "[tool result cleared]" for c in older)
    assert newest.startswith("yyy")


def test_rereading_the_same_range_supersedes_the_earlier_read() -> None:
    reader = Tool("read_file", "r", {"type": "object"}, lambda a: f"body of {a['path']}")
    calls: list[dict[str, Any]] = [
        {"path": "a.md"},
        {"path": "b.md"},
        {"path": "a.md"},
        {"path": "a.md", "offset": 5},
    ]
    seen: list[list[str]] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append([str(p.content) for p in tool_returns(messages)])
        if len(seen) <= len(calls):
            return ModelResponse(parts=[ToolCallPart("read_file", calls[len(seen) - 1])])
        return final(info, {"verdict": "ok", "note": None})

    run_typed("analyst", Verdict, "be brief", "go", [reader], make_cfg(), model=FunctionModel(fn))
    assert seen[-1] == ["[superseded file read]", "body of b.md", "body of a.md", "body of a.md"]
