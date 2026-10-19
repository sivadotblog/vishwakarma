"""Prefect flows that run VK on demand: `vk-issue` for an issue, `vk-review` for a PR.

The pull steps in `prefect.yaml` install the toolchain and `uv sync` the clone; this module
activates that venv in-process before it imports VK. Each run mints a GitHub App installation
token and calls VK's pipeline in-process, with each stage as a Prefect task. Secrets are never
logged.
"""

import site
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def activate_venv(root: Path) -> None:
    """Make the `.venv` that `uv sync` built in `root` importable in this process.

    The worker runs flows in its own Python, so this is the in-process form of activating the
    venv. Its site-packages go after the worker's, so the worker's Prefect still wins.
    """
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site.addsitedir(str(root / ".venv" / "lib" / version / "site-packages"))


activate_venv(REPO_ROOT)

import logging
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

import httpx
from prefect import flow, get_run_logger
from prefect.blocks.system import Secret
from prefect.runtime import flow_run
from prefect.variables import Variable
from pydantic_ai.exceptions import UsageLimitExceeded

from vk.approval import Caller
from vk.config import ConfigError, config_path, load_config, read_settings
from vk.github import GitHub, with_bot_identity
from vk.pipeline import run_issue
from vk.pr_review import run_review

# Relative on purpose: Prefect loads this file as a script that supports relative imports, but
# `packages/vk` is not on its sys.path, so `prefect_flows.github_app` would not resolve there.
from .github_app import API, AppToken, installation_token
from .stage_tasks import prefect_stage

VK = read_settings(config_path(os.environ))
REPO = VK.prefect.repo
Kind = Literal["issue", "review"]
Log = logging.Logger | logging.LoggerAdapter[logging.Logger]


@dataclass(frozen=True)
class Settings:
    app_id: str
    private_key: str
    gemini_api_key: str


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
    )


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
    """Run VK on issue/PR `number` in this process and return its summary.

    Failures before a token exists propagate unchanged. An error that escapes VK posts a
    failure comment (best effort) and is re-raised; a handled "Stopped: ..." summary is returned.
    """
    settings = load_settings()
    token = installation_token(settings.app_id, settings.private_key, REPO)
    state_dir = Path(tempfile.mkdtemp(prefix="vk-state-"))
    env = vk_env(os.environ, token, settings, state_dir)
    # VK's build_model and its git/make/uv subprocesses read the process environment.
    os.environ.update(env)
    logging.getLogger("vk").setLevel(logging.INFO)
    try:
        cfg = load_config(env)
        gh = GitHub(cfg)
        cfg = with_bot_identity(cfg, gh)
        if kind == "issue":
            return run_issue(
                cfg, gh, number, Caller(True, issue_number=number), stage_wrapper=prefect_stage
            )
        return run_review(
            cfg, gh, number, Caller(True, pr_number=number), stage_wrapper=prefect_stage
        )
    except Exception as error:
        if isinstance(error, ConfigError):
            logger.error("Configuration error: %s", error)
        elif isinstance(error, UsageLimitExceeded):
            logger.error("Token budget exceeded: %s", error)
        try:
            post_comment(token.token, number, failure_body(run_url))
        except Exception as comment_error:
            logger.error("Could not post the failure comment: %s", type(comment_error).__name__)
        raise


@flow(name="vk-issue", timeout_seconds=VK.prefect.flow_timeout_s)
def vk_issue(issue_number: int) -> str:
    return run_vk("issue", issue_number, get_run_logger(), flow_run.ui_url)


@flow(name="vk-review", timeout_seconds=VK.prefect.flow_timeout_s)
def vk_review(pr_number: int) -> str:
    return run_vk("review", pr_number, get_run_logger(), flow_run.ui_url)
