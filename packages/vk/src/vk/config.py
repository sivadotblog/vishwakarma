"""Configuration shared by every module: settings from `vk.toml`, secrets from the environment."""

import os
import re
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, PositiveInt, ValidationError, field_validator
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

# Every agent that can have a `[clans.<name>]` table: the clans, then the judgment agents.
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
DEFAULT_CONFIG = Path(__file__).parent / "vk.toml"


class ConfigError(RuntimeError):
    """Missing or invalid configuration."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _native_model(name: str | None) -> str | None:
    if name is not None and ":" not in name:
        raise ValueError(f"{name!r} must be {MODEL_FORMAT}")
    return name


class ClanSettings(_Section):
    """One agent's model and per-run budgets: `[defaults]`, or a clan's resolved settings."""

    model: str
    max_input_tokens: PositiveInt | None = None
    max_output_tokens: PositiveInt | None = None
    max_total_tokens: PositiveInt | None = None
    max_requests: PositiveInt | None = None
    output_retries: int

    _check_model = field_validator("model")(_native_model)


class ClanOverride(_Section):
    """A `[clans.<name>]` table: any key it sets replaces the `[defaults]` value."""

    model: str | None = None
    max_input_tokens: PositiveInt | None = None
    max_output_tokens: PositiveInt | None = None
    max_total_tokens: PositiveInt | None = None
    max_requests: PositiveInt | None = None
    output_retries: int | None = None

    _check_model = field_validator("model")(_native_model)


class PipelineSettings(_Section):
    max_review_cycles: int
    max_ci_fix_attempts: int


class PromptSettings(_Section):
    max_repo_instruction_chars: PositiveInt
    purpose_chars: PositiveInt


class ToolSettings(_Section):
    bash_timeout_s: PositiveInt
    max_output_chars: PositiveInt
    max_read_lines: PositiveInt
    max_glob_results: PositiveInt
    max_grep_matches: PositiveInt
    max_web_bytes: PositiveInt
    max_web_chars: PositiveInt
    web_timeout_s: PositiveInt
    max_artifact_chars: PositiveInt
    max_artifact_title_chars: PositiveInt


class GitSettings(_Section):
    timeout_s: PositiveInt
    setup_command: str


class GitHubSettings(_Section):
    timeout_s: PositiveInt
    log_tail_chars: PositiveInt


class CompactionSettings(_Section):
    enabled: bool
    clear_after_tokens: PositiveInt
    keep_pairs: PositiveInt
    min_clear_tokens: PositiveInt


class PrefectSettings(_Section):
    repo: str
    flow_timeout_s: PositiveInt


class Settings(_Section):
    """The whole `vk.toml`."""

    defaults: ClanSettings
    clans: dict[str, ClanOverride]
    pipeline: PipelineSettings
    prompts: PromptSettings
    tools: ToolSettings
    git: GitSettings
    github: GitHubSettings
    prefect: PrefectSettings
    compaction: CompactionSettings

    @field_validator("clans")
    @classmethod
    def _known_clans(cls, clans: dict[str, ClanOverride]) -> dict[str, ClanOverride]:
        if unknown := sorted(set(clans) - set(CLANS)):
            raise ValueError(f"unknown clans {unknown}; known: {list(CLANS)}")
        return clans

    def clan(self, name: str) -> ClanSettings:
        """`[defaults]` with the clan's own table laid over it."""
        override = self.clans.get(name)
        if override is None:
            return self.defaults
        return self.defaults.model_copy(update=override.model_dump(exclude_none=True))


def config_path(env: Mapping[str, str]) -> Path:
    """`VK_CONFIG` when set, else the `vk.toml` shipped with the package."""
    return Path(env["VK_CONFIG"]).expanduser() if env.get("VK_CONFIG") else DEFAULT_CONFIG


def read_settings(path: Path = DEFAULT_CONFIG) -> Settings:
    try:
        with path.open("rb") as handle:
            return Settings.model_validate(tomllib.load(handle))
    except OSError as exc:
        raise ConfigError(f"Cannot read settings file {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    except ValidationError as exc:
        raise ConfigError(f"{path} is invalid:\n{exc}") from exc


@dataclass(frozen=True)
class Config:
    repo: str  # "owner/name"
    github_token: str
    state_dir: Path
    settings: Settings = field(default_factory=read_settings)
    bot_login: str | None = None
    bot_name: str | None = None  # git author name; set from `bot_login` by `with_bot_identity`
    bot_email: str | None = None

    def model_for(self, clan: str) -> str:
        return self.settings.clan(clan).model


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
    if not token:
        raise ConfigError("GITHUB_TOKEN is required.")
    settings = read_settings(config_path(e))
    repo = e.get("VK_REPO") or detect_repo(cwd)
    return Config(
        repo=repo,
        github_token=token,
        state_dir=Path(e.get("VK_STATE_DIR", "~/.vk")).expanduser(),
        settings=settings,
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
