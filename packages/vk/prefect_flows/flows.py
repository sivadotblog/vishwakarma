"""Prefect flows that run VK on demand: `vk-issue` for an issue, `vk-review` for a PR.

The pull steps in `prefect.yaml` install the toolchain and sync the workspace; each run then
mints a GitHub App installation token and runs the `vk` CLI as a subprocess. This module runs
in the Prefect image's Python, so it imports only the stdlib, Prefect, httpx and cryptography
(via `github_app`), never `vk`. Secrets reach VK only through the subprocess environment and
are never logged.
"""

import logging
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import httpx
from prefect import flow, get_run_logger
from prefect.blocks.system import Secret
from prefect.runtime import flow_run
from prefect.variables import Variable

# Relative on purpose: Prefect loads this file as a script that supports relative imports, but
# `packages/vk` is not on its sys.path, so `prefect_flows.github_app` would not resolve there.
from .github_app import API, AppToken, installation_token

REPO = "sivadotblog/vishwakarma"
DEFAULT_MODEL = "google:gemini-3.5-flash"
REPO_ROOT = Path(__file__).resolve().parents[3]

Kind = Literal["issue", "review"]
Log = logging.Logger | logging.LoggerAdapter[logging.Logger]


@dataclass(frozen=True)
class Settings:
    app_id: str
    private_key: str
    gemini_api_key: str
    model: str


def secret(name: str) -> str:
    # `load` is typed as sync-or-async; called from sync code it returns the block.
    return str(cast(Secret[str], Secret.load(name)).get())


def load_settings() -> Settings:
    app_id = Variable.get("vk_app_id")
    if not app_id:
        raise RuntimeError("Prefect variable vk_app_id is not set")
    return Settings(
        app_id=str(app_id),
        private_key=secret("vk-app-private-key"),
        gemini_api_key=secret("vk-gemini-api-key"),
        model=str(Variable.get("vk_model", default=DEFAULT_MODEL)),
    )


def vk_command(kind: Kind, number: int) -> list[str]:
    return ["uv", "run", "--package", "vk", "vk", kind, str(number), "--unattended"]


def vk_env(
    base: Mapping[str, str], token: AppToken, settings: Settings, state_dir: Path
) -> dict[str, str]:
    local_bin = str(Path.home() / ".local/bin")
    path = os.pathsep.join(p for p in (local_bin, base.get("PATH", "")) if p)
    return {
        **base,
        "PATH": path,
        "GITHUB_TOKEN": token.token,
        "VK_BOT_LOGIN": token.bot_login,
        "GEMINI_API_KEY": settings.gemini_api_key,
        "VK_MODEL": settings.model,
        "VK_REPO": REPO,
        "VK_STATE_DIR": str(state_dir),
        "PYDANTIC_AI_NO_BANNER": "1",
    }


def failure_body(run_url: str | None) -> str:
    return f"The software factory run failed. Log: {run_url}"


def post_comment(token: str, number: int, body: str, client: httpx.Client | None = None) -> None:
    """Comment on an issue or PR (the issues endpoint serves both)."""
    owns_client = client is None
    http = client or httpx.Client()
    try:
        response = http.post(
            f"{API}/repos/{REPO}/issues/{number}/comments",
            json={"body": body},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        response.raise_for_status()
    finally:
        if owns_client:
            http.close()


def run_vk(kind: Kind, number: int, logger: Log, run_url: str | None) -> str:
    """Run VK on issue/PR `number` and return its stdout.

    Failures before a token exists propagate unchanged. A nonzero VK exit posts a failure
    comment (best effort) and then raises.
    """
    settings = load_settings()
    token = installation_token(settings.app_id, settings.private_key, REPO)
    state_dir = Path(tempfile.mkdtemp(prefix="vk-state-"))
    env = vk_env(os.environ, token, settings, state_dir)
    with tempfile.TemporaryFile("w+") as stdout:
        process = subprocess.Popen(
            vk_command(kind, number),
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stderr is not None
        for line in process.stderr:
            logger.info(line.rstrip("\n"))
        code = process.wait()
        stdout.seek(0)
        output = stdout.read().strip()
    if code != 0:
        try:
            post_comment(token.token, number, failure_body(run_url))
        except Exception as error:
            logger.error("Could not post the failure comment: %s", type(error).__name__)
        raise RuntimeError(f"vk {kind} {number} exited {code}")
    return output


@flow(name="vk-issue", timeout_seconds=3600)
def vk_issue(issue_number: int) -> str:
    return run_vk("issue", issue_number, get_run_logger(), flow_run.ui_url)


@flow(name="vk-review", timeout_seconds=3600)
def vk_review(pr_number: int) -> str:
    return run_vk("review", pr_number, get_run_logger(), flow_run.ui_url)
