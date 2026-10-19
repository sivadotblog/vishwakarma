"""Tests for the Prefect flows. No network and no Prefect server: collaborators are patched."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from prefect_flows import flows
from prefect_flows.flows import Settings, failure_body, post_comment, run_vk, vk_env
from prefect_flows.github_app import AppToken
from prefect_flows.stage_tasks import prefect_stage
from pydantic_ai.exceptions import UsageLimitExceeded

from vk.approval import Caller
from vk.config import ConfigError

TOKEN = AppToken("ghs_secret", "vk-factory[bot]")
SETTINGS = Settings("1", "pem", "gk")
LOGGER = logging.getLogger("test-vk")


class Comments:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    def __call__(self, token: str, number: int, body: str) -> None:
        self.calls.append((token, number, body))


@pytest.fixture
def comments(monkeypatch: pytest.MonkeyPatch) -> Comments:
    recorder = Comments()
    monkeypatch.setattr(flows, "load_settings", lambda: SETTINGS)
    monkeypatch.setattr(flows, "installation_token", lambda *args, **kwargs: TOKEN)
    monkeypatch.setattr(flows, "post_comment", recorder)
    monkeypatch.setattr(flows, "GitHub", StubGitHub)
    monkeypatch.setattr(flows, "with_bot_identity", lambda cfg, gh: cfg)
    # run_vk updates os.environ; register every key so monkeypatch restores it afterwards.
    for key in vk_env({}, TOKEN, SETTINGS, Path()):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    return recorder


class StubGitHub:
    def __init__(self, cfg: object) -> None:
        self.cfg = cfg


class Pipeline:
    """Stands in for run_issue / run_review: records the call, then returns or raises."""

    def __init__(self, result: str = "PR opened", error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.args: tuple[Any, ...] = ()
        self.kwargs: dict[str, Any] = {}

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        self.args, self.kwargs = args, kwargs
        if self.error:
            raise self.error
        return self.result


def stub_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    name: str = "run_issue",
    result: str = "PR opened",
    error: Exception | None = None,
) -> Pipeline:
    pipeline = Pipeline(result, error)
    monkeypatch.setattr(flows, name, pipeline)
    return pipeline


def test_vk_env(tmp_path: Path) -> None:
    env = vk_env({"PATH": "/usr/bin", "KEEP": "me"}, TOKEN, SETTINGS, tmp_path)
    assert env["GITHUB_TOKEN"] == "ghs_secret"
    assert env["VK_BOT_LOGIN"] == "vk-factory[bot]"
    assert env["GEMINI_API_KEY"] == "gk"
    assert "VK_MODEL" not in env  # models come from vk.toml
    assert env["VK_REPO"] == "sivadotblog/vishwakarma"
    assert env["PYDANTIC_AI_NO_BANNER"] == "1"
    assert env["VK_STATE_DIR"] == str(tmp_path)
    assert env["PATH"].startswith(str(Path.home() / ".local/bin"))
    assert env["KEEP"] == "me"


def test_failure_body() -> None:
    assert (
        failure_body("https://app.prefect.cloud/x")
        == "The software factory run failed. Log: https://app.prefect.cloud/x"
    )


def test_run_vk_issue_calls_pipeline(monkeypatch: pytest.MonkeyPatch, comments: Comments) -> None:
    pipeline = stub_pipeline(monkeypatch, "run_issue")
    assert run_vk("issue", 5, LOGGER, "u") == "PR opened"
    cfg, _gh, number, caller = pipeline.args
    assert number == 5
    assert caller == Caller(True, issue_number=5)
    assert cfg.repo == "sivadotblog/vishwakarma"
    assert cfg.github_token == "ghs_secret"
    assert cfg.settings == flows.VK
    assert cfg.bot_login == "vk-factory[bot]"
    assert pipeline.kwargs == {"stage_wrapper": prefect_stage}
    assert comments.calls == []


def test_run_vk_review_calls_pipeline(monkeypatch: pytest.MonkeyPatch, comments: Comments) -> None:
    pipeline = stub_pipeline(monkeypatch, "run_review")
    assert run_vk("review", 7, LOGGER, "u") == "PR opened"
    cfg, _gh, number, caller = pipeline.args
    assert number == 7
    assert caller == Caller(True, pr_number=7)
    assert cfg.github_token == "ghs_secret"
    assert pipeline.kwargs == {"stage_wrapper": prefect_stage}
    assert comments.calls == []


def test_run_vk_sets_process_env(monkeypatch: pytest.MonkeyPatch, comments: Comments) -> None:
    stub_pipeline(monkeypatch)
    run_vk("issue", 5, LOGGER, "u")
    assert os.environ["GEMINI_API_KEY"] == "gk"
    assert os.environ["PATH"].startswith(str(Path.home() / ".local/bin"))


def test_run_vk_stopped_summary_completes(
    monkeypatch: pytest.MonkeyPatch, comments: Comments
) -> None:
    summary = "Stopped: the analyst step failed (x)."
    stub_pipeline(monkeypatch, result=summary)
    assert run_vk("issue", 5, LOGGER, "u") == summary
    assert comments.calls == []


@pytest.mark.parametrize("error", [UsageLimitExceeded("budget"), ConfigError("bad")])
def test_run_vk_escaped_error_comments_and_reraises(
    monkeypatch: pytest.MonkeyPatch, comments: Comments, error: Exception
) -> None:
    stub_pipeline(monkeypatch, error=error)
    with pytest.raises(type(error)) as raised:
        run_vk("issue", 5, LOGGER, "u")
    assert raised.value is error
    assert comments.calls == [("ghs_secret", 5, "The software factory run failed. Log: u")]


def test_run_vk_comment_failure_still_raises_original(
    monkeypatch: pytest.MonkeyPatch, comments: Comments
) -> None:
    def broken(token: str, number: int, body: str) -> None:
        raise httpx.ConnectError("x")

    monkeypatch.setattr(flows, "post_comment", broken)
    stub_pipeline(monkeypatch, error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        run_vk("issue", 5, LOGGER, "u")


def test_run_vk_does_not_log_token(
    monkeypatch: pytest.MonkeyPatch, comments: Comments, caplog: pytest.LogCaptureFixture
) -> None:
    stub_pipeline(monkeypatch, error=RuntimeError("boom"))
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        run_vk("issue", 5, LOGGER, "u")
    assert "ghs_secret" not in caplog.text
    assert "gk" not in caplog.text
    assert "pem" not in caplog.text


def test_run_vk_settings_failure_skips_comment(
    monkeypatch: pytest.MonkeyPatch, comments: Comments
) -> None:
    error = RuntimeError("Prefect variable vk_app_id is not set")

    def fail() -> flows.Settings:
        raise error

    monkeypatch.setattr(flows, "load_settings", fail)
    with pytest.raises(RuntimeError) as raised:
        run_vk("issue", 5, LOGGER, "u")
    assert raised.value is error
    assert comments.calls == []


def test_post_comment_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={})

    post_comment("ghs_x", 5, "b", client=httpx.Client(transport=httpx.MockTransport(handler)))
    (request,) = seen
    assert request.method == "POST"
    assert (
        str(request.url) == "https://api.github.com/repos/sivadotblog/vishwakarma/issues/5/comments"
    )
    assert json.loads(request.content) == {"body": "b"}
    assert request.headers["Authorization"] == "Bearer ghs_x"


def test_flows_loads_as_prefect_script() -> None:
    # The managed worker loads the entrypoint by path from the repo root, without `packages/vk`
    # on sys.path; run that loader in a fresh interpreter so pytest's pythonpath can't help.
    script = (
        "from prefect.utilities.importtools import load_script_as_module as load;"
        "print(load('packages/vk/prefect_flows/flows.py').vk_issue.name)"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=flows.REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "vk-issue"


def test_activate_venv_adds_site_packages_and_pth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "path", list(sys.path))
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site_dir = tmp_path / ".venv" / "lib" / version / "site-packages"
    src = tmp_path / "src"
    site_dir.mkdir(parents=True)
    src.mkdir()
    (site_dir / "_editable.pth").write_text(f"{src}\n")  # how uv installs workspace members
    flows.activate_venv(tmp_path)
    assert str(site_dir) in sys.path
    assert str(src) in sys.path
