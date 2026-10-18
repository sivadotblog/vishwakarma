import os
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded

from vk import cli
from vk.approval import Caller
from vk.config import Config, ConfigError

CFG = Config(repo="o/r", github_token="t", model="m", clan_models={}, state_dir=Path("/x"))


class Tty:
    def isatty(self) -> bool:
        return True


class NoTty:
    def isatty(self) -> bool:
        return False


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake(name: str) -> Any:
        def run(cfg: Config, gh: object, number: int, caller: Caller, **_kw: Any) -> str:
            seen.update(command=name, cfg=cfg, number=number, caller=caller)
            return "done"

        return run

    monkeypatch.setattr(cli, "load_config", lambda: CFG)
    monkeypatch.setattr(cli, "GitHub", lambda cfg: "gh")
    monkeypatch.setattr(cli, "run_issue", fake("issue"))
    monkeypatch.setattr(cli, "run_review", fake("review"))
    monkeypatch.setattr(cli, "run_ci_fix", fake("ci-fix"))
    return seen


def test_issue_attended_on_tty(
    captured: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", Tty())
    assert cli.main(["issue", "7"]) == 0
    assert captured["command"] == "issue" and captured["number"] == 7
    assert captured["cfg"] is CFG
    assert captured["caller"] == Caller(False, issue_number=7)
    assert capsys.readouterr().out.strip() == "done"


def test_unattended_forced_without_tty(
    captured: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", NoTty())
    assert cli.main(["review", "9"]) == 0
    assert captured["command"] == "review"
    assert captured["caller"] == Caller(True, pr_number=9)


def test_unattended_flag_and_ci_fix(
    captured: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", Tty())
    assert cli.main(["ci-fix", "9", "--unattended"]) == 0
    assert captured["command"] == "ci-fix"
    assert captured["caller"] == Caller(True, pr_number=9)


def test_banner_is_silenced_unless_the_caller_chose_otherwise(
    captured: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYDANTIC_AI_NO_BANNER", raising=False)
    cli.main(["issue", "1", "--unattended"])
    assert os.environ["PYDANTIC_AI_NO_BANNER"] == "1"
    monkeypatch.setenv("PYDANTIC_AI_NO_BANNER", "0")
    cli.main(["issue", "1", "--unattended"])
    assert os.environ["PYDANTIC_AI_NO_BANNER"] == "0"


@pytest.mark.parametrize(
    ("exc", "code"),
    [(ConfigError("GITHUB_TOKEN is required."), 2), (UsageLimitExceeded("big"), 3)],
)
def test_errors_exit_with_their_code(
    exc: Exception,
    code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(*_a: Any, **_kw: Any) -> str:
        raise exc

    monkeypatch.setattr(cli, "load_config", lambda: CFG)
    monkeypatch.setattr(cli, "GitHub", lambda cfg: "gh")
    monkeypatch.setattr(cli, "run_issue", boom)
    assert cli.main(["issue", "1"]) == code
    assert str(exc) in capsys.readouterr().err


def test_bad_args_exit() -> None:
    with pytest.raises(SystemExit):
        cli.main(["issue", "abc"])
