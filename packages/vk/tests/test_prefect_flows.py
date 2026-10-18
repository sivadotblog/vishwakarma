"""Tests for the Prefect flows. No network and no Prefect server: collaborators are patched."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from prefect_flows import flows
from prefect_flows.flows import Settings, failure_body, post_comment, run_vk, vk_command, vk_env
from prefect_flows.github_app import AppToken

TOKEN = AppToken("ghs_secret", "vk-factory[bot]")
SETTINGS = Settings("1", "pem", "gk", "google:m")
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
    return recorder


def use_script(monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    monkeypatch.setattr(flows, "vk_command", lambda kind, number: [sys.executable, "-c", script])


def test_vk_command() -> None:
    assert vk_command("review", 9) == [
        "uv", "run", "--package", "vk", "vk", "review", "9", "--unattended",
    ]  # fmt: skip


def test_vk_env(tmp_path: Path) -> None:
    env = vk_env({"PATH": "/usr/bin", "KEEP": "me"}, TOKEN, SETTINGS, tmp_path)
    assert env["GITHUB_TOKEN"] == "ghs_secret"
    assert env["VK_BOT_LOGIN"] == "vk-factory[bot]"
    assert env["GEMINI_API_KEY"] == "gk"
    assert env["VK_MODEL"] == "google:m"
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


def test_run_vk_success_returns_stdout(
    monkeypatch: pytest.MonkeyPatch, comments: Comments, caplog: pytest.LogCaptureFixture
) -> None:
    use_script(monkeypatch, "import sys; print('done'); print('step 1', file=sys.stderr)")
    with caplog.at_level(logging.INFO):
        assert run_vk("issue", 5, LOGGER, "u") == "done"
    assert "step 1" in caplog.text
    assert comments.calls == []


def test_run_vk_failure_comments_and_raises(
    monkeypatch: pytest.MonkeyPatch, comments: Comments
) -> None:
    use_script(monkeypatch, "import sys; sys.exit(3)")
    with pytest.raises(RuntimeError, match="vk issue 5 exited 3"):
        run_vk("issue", 5, LOGGER, "u")
    assert comments.calls == [("ghs_secret", 5, "The software factory run failed. Log: u")]


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


def test_run_vk_comment_failure_still_raises_vk_error(
    monkeypatch: pytest.MonkeyPatch, comments: Comments
) -> None:
    def broken(token: str, number: int, body: str) -> None:
        raise httpx.ConnectError("x")

    monkeypatch.setattr(flows, "post_comment", broken)
    use_script(monkeypatch, "import sys; sys.exit(2)")
    with pytest.raises(RuntimeError, match="exited 2"):
        run_vk("issue", 5, LOGGER, "u")


def test_run_vk_does_not_log_token(
    monkeypatch: pytest.MonkeyPatch, comments: Comments, caplog: pytest.LogCaptureFixture
) -> None:
    use_script(monkeypatch, "import sys; sys.exit(1)")
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        run_vk("issue", 5, LOGGER, "u")
    assert "ghs_secret" not in caplog.text
    assert "pem" not in caplog.text


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
