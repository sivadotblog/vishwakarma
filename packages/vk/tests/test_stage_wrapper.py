"""The optional stage wrapper on Stages and the pipelines."""

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from vk import agents, pipeline
from vk.ci_fix import run_ci_fix
from vk.config import Config
from vk.github import GitHub
from vk.models import Analysis, IssueTriage
from vk.pipeline import StageFailed, Stages, run_issue
from vk.pr_review import run_review

from .helpers import FakeSession
from .test_issue_pipeline import ROUTES, UNATTENDED, happy_models

CFG = Config(repo="o/r", github_token="t", model="m", clan_models={}, state_dir=Path("/x"))
ANALYSIS_RESULT = Analysis.model_construct()
TRIAGE_RESULT = IssueTriage.model_construct()


class Recorder:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def __call__[T](self, stage: str, call: Callable[[], T], /) -> T:
        self.seen.append(stage)
        return call()


def fake_clan(monkeypatch: pytest.MonkeyPatch, *outcomes: Any) -> list[str]:
    """Patch `run_clan`: each call returns the next outcome, or raises it if an exception."""
    calls: list[str] = []
    queue = list(outcomes)

    def run_clan(name: str, *args: Any, **kwargs: Any) -> BaseModel:
        calls.append(name)
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[no-any-return]  # outcomes are test-supplied models

    monkeypatch.setattr(pipeline, "run_clan", run_clan)
    return calls


def test_clan_without_wrapper_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_clan(monkeypatch, ANALYSIS_RESULT)
    assert Stages(CFG).clan("analyst", "m", Analysis) is ANALYSIS_RESULT


def test_clan_goes_through_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_clan(monkeypatch, ANALYSIS_RESULT)
    wrap = Recorder()
    assert Stages(CFG, wrap=wrap).clan("analyst", "m", Analysis) is ANALYSIS_RESULT
    assert wrap.seen == ["analyst"]


def test_agent_goes_through_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "run_typed", lambda *a, **k: TRIAGE_RESULT)
    wrap = Recorder()
    assert Stages(CFG, wrap=wrap).agent("triager", IssueTriage, "i", "m") is TRIAGE_RESULT
    assert wrap.seen == ["triager"]


def test_retry_happens_inside_one_wrapper_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_clan(monkeypatch, RuntimeError("flaky"), ANALYSIS_RESULT)
    wrap = Recorder()
    assert Stages(CFG, wrap=wrap).clan("analyst", "m", Analysis) is ANALYSIS_RESULT
    assert wrap.seen == ["analyst"]
    assert calls == ["analyst", "analyst"]


def test_stage_failed_passes_through_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_clan(monkeypatch, RuntimeError("down"))
    wrap = Recorder()
    with pytest.raises(StageFailed):
        Stages(CFG, wrap=wrap).clan("analyst", "m", Analysis)
    assert wrap.seen == ["analyst"]


@pytest.mark.parametrize("fn", [run_issue, run_review, run_ci_fix])
def test_pipelines_pass_stage_wrapper(fn: Callable[..., str]) -> None:
    param = inspect.signature(fn).parameters["stage_wrapper"]
    assert param.default is None
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_run_issue_uses_stage_wrapper(cfg: Config, remote: Path) -> None:
    wrap = Recorder()
    run_issue(
        cfg,
        GitHub(cfg, FakeSession(dict(ROUTES))),
        7,
        UNATTENDED,
        confirm=lambda _prompt: True,
        model=happy_models([]),
        remote_url=f"file://{remote}",
        stage_wrapper=wrap,
    )
    assert wrap.seen[:2] == ["triager", "classifier"]
    for stage in ("analyst", "implementer", "reviewer", "pr_writer"):
        assert stage in wrap.seen
