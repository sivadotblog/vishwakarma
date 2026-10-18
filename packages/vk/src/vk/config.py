"""Environment-driven configuration shared by every module."""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

# Every agent that can take a `VK_MODEL_<NAME>` override: the clans, then the judgment agents.
CLANS = (
    "classifier",
    "researcher",
    "analyst",
    "implementer",
    "reviewer",
    "triager",
    "pr_writer",
    "ci_diagnoser",
)
MODEL_FORMAT = "a native 'provider:model' string, e.g. 'google:gemini-3.5-flash'"


class ConfigError(RuntimeError):
    """Missing or invalid configuration."""


@dataclass(frozen=True)
class Config:
    repo: str  # "owner/name"
    github_token: str
    model: str
    clan_models: dict[str, str]
    state_dir: Path
    branch_prefix: str = "vk/"
    setup_command: str | None = None
    max_output_tokens: int = 100_000
    max_input_tokens: int = 2_000_000
    bot_login: str | None = None
    bot_name: str | None = None  # git author name; set from `bot_login` by `with_bot_identity`
    bot_email: str | None = None

    def model_for(self, clan: str) -> str:
        return self.clan_models.get(clan, self.model)


_REMOTE = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")


def detect_repo(cwd: Path | None = None) -> str:
    """Return `owner/name` from the `origin` remote of the checkout at `cwd`."""
    out = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    match = _REMOTE.search(out.stdout.strip())
    if out.returncode != 0 or not match:
        raise ConfigError("Cannot detect a github.com repo from the `origin` remote.")
    return match.group(1)


def load_config(env: dict[str, str] | None = None, cwd: Path | None = None) -> Config:
    e = dict(os.environ) if env is None else env
    token = e.get("GITHUB_TOKEN")
    model = e.get("VK_MODEL")
    if not token:
        raise ConfigError("GITHUB_TOKEN is required.")
    if not model:
        raise ConfigError(f"VK_MODEL is required: {MODEL_FORMAT}.")
    clan_models = {s: e[f"VK_MODEL_{s.upper()}"] for s in CLANS if e.get(f"VK_MODEL_{s.upper()}")}
    for var, name in (
        ("VK_MODEL", model),
        *((f"VK_MODEL_{s.upper()}", m) for s, m in clan_models.items()),
    ):
        if ":" not in name:
            raise ConfigError(f"{var}={name!r} must be {MODEL_FORMAT}.")
    repo = e.get("VK_REPO") or detect_repo(cwd)
    return Config(
        repo=repo,
        github_token=token,
        model=model,
        clan_models=clan_models,
        state_dir=Path(e.get("VK_STATE_DIR", "~/.vk")).expanduser(),
        branch_prefix=e.get("VK_BRANCH_PREFIX", "vk/"),
        setup_command=e.get("VK_SETUP_COMMAND") or None,
        max_output_tokens=int(e.get("VK_MAX_OUTPUT_TOKENS", "100000")),
        max_input_tokens=int(e.get("VK_MAX_INPUT_TOKENS", "2000000")),
        bot_login=e.get("VK_BOT_LOGIN") or None,
    )


def build_model(cfg: Config, clan: str, env: dict[str, str] | None = None) -> Model | str:
    """Return the PydanticAI model for `clan`: a native `provider:model` string.

    `google:` models read `GEMINI_API_KEY` first (the existing CI secret), then fall back to the
    provider's own default (`GOOGLE_API_KEY`).
    """
    e = dict(os.environ) if env is None else env
    name = cfg.model_for(clan)
    # A gateway (e.g. Kong) can be added here when one exists: return a model pointed at it.
    if ":" not in name:
        raise ConfigError(f"Model {name!r} for {clan!r} must be {MODEL_FORMAT}.")
    kind, _, model_name = name.partition(":")
    if kind == "google" and (key := e.get("GEMINI_API_KEY")):
        return GoogleModel(model_name, provider=GoogleProvider(api_key=key))
    return name
