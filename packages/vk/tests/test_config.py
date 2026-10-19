"""Tests for `vk.toml` settings, `load_config` and `build_model` model routing."""

from dataclasses import replace
from pathlib import Path

import pytest
from pydantic_ai.models.google import GoogleModel

from vk.config import (
    CLANS,
    DEFAULT_CONFIG,
    ClanOverride,
    Config,
    ConfigError,
    build_model,
    load_config,
    read_settings,
)

from .helpers import with_settings

ENV = {"GITHUB_TOKEN": "t", "VK_REPO": "o/r"}


def make_cfg(model: str, **clan_models: str) -> Config:
    cfg = with_settings(
        Config(repo="o/r", github_token="t", state_dir=Path("/tmp/vk-test")),
        defaults={"model": model},
    )
    clans = {name: ClanOverride(model=m) for name, m in clan_models.items()}
    return replace(cfg, settings=cfg.settings.model_copy(update={"clans": clans}))


def write_toml(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of the shipped `vk.toml` with one edit."""
    text = DEFAULT_CONFIG.read_text()
    assert old in text
    path = tmp_path / "vk.toml"
    path.write_text(text.replace(old, new, 1))
    return path


def test_native_string_passes_through() -> None:
    assert build_model(make_cfg("anthropic:claude-x"), "analyst", {}) == "anthropic:claude-x"


def test_clan_override_wins() -> None:
    cfg = make_cfg("anthropic:a", analyst="openai:b")
    assert build_model(cfg, "analyst", {}) == "openai:b"
    assert build_model(cfg, "reviewer", {}) == "anthropic:a"


def test_google_uses_gemini_api_key() -> None:
    model = build_model(make_cfg("google:gemini-x"), "analyst", {"GEMINI_API_KEY": "gem"})
    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-x"
    assert model.client._api_client.api_key == "gem"


def test_google_reads_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gem")
    model = build_model(make_cfg("google:gemini-x"), "analyst")
    assert isinstance(model, GoogleModel)


def test_google_without_gemini_key_defers_to_provider() -> None:
    assert build_model(make_cfg("google:gemini-x"), "analyst", {}) == "google:gemini-x"


def test_bot_login_is_optional() -> None:
    assert load_config(ENV).bot_login is None
    assert load_config({**ENV, "VK_BOT_LOGIN": "vk-app[bot]"}).bot_login == "vk-app[bot]"


def test_shipped_settings_load_and_list_every_clan() -> None:
    settings = read_settings()
    assert set(settings.clans) == set(CLANS)
    assert settings.defaults.max_input_tokens == 2_000_000
    assert settings.defaults.max_output_tokens == 100_000
    assert settings.defaults.max_total_tokens is None
    assert settings.defaults.max_requests is None
    assert settings.git.setup_command == ""
    assert settings.compaction.enabled is True


def test_clan_table_overrides_only_the_keys_it_sets(tmp_path: Path) -> None:
    path = write_toml(
        tmp_path,
        "\n[clans.reviewer]\n",
        '\n[clans.reviewer]\nmodel = "anthropic:x"\nmax_total_tokens = 500\n',
    )
    settings = read_settings(path)
    reviewer = settings.clan("reviewer")
    assert reviewer.model == "anthropic:x"
    assert reviewer.max_total_tokens == 500
    assert reviewer.max_output_tokens == settings.defaults.max_output_tokens
    assert settings.clan("classifier") == settings.defaults
    assert settings.clan("implementer").model == "google:gemini-3.1-pro-preview"


def test_vk_config_selects_another_file(tmp_path: Path) -> None:
    path = write_toml(tmp_path, "max_review_cycles = 2", "max_review_cycles = 5")
    cfg = load_config({**ENV, "VK_CONFIG": str(path)})
    assert cfg.settings.pipeline.max_review_cycles == 5
    assert load_config(ENV).settings.pipeline.max_review_cycles == 2


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        ("[clans.triager]", "[clans.triage]", "unknown clans"),
        ("max_review_cycles = 2", "max_review_cyles = 2", "max_review_cyles"),
        ('model = "google:', 'model = "gemini/', "provider:model"),
        ("[clans.pr_writer]", '[clans.pr_writer]\nmodel = "gemini-3.5-flash"', "provider:model"),
        ("max_output_tokens = 100_000", "max_output_tokens = 0", "greater than 0"),
        ("keep_pairs = 6", "keep_pairs = 0", "greater than 0"),
        ("enabled = true", 'enabled = "maybe"', "valid boolean"),
        ("max_output_tokens = 100_000", 'max_output_tokens = "abc"', "valid integer"),
        ("max_input_tokens = 2_000_000", "max_input_tokens = 12.3", "valid integer"),
        ("[prefect]", "[prefect", "not valid TOML"),
    ],
)
def test_invalid_settings_are_rejected(tmp_path: Path, old: str, new: str, error: str) -> None:
    with pytest.raises(ConfigError, match=error):
        load_config({**ENV, "VK_CONFIG": str(write_toml(tmp_path, old, new))})


def test_missing_settings_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Cannot read settings file"):
        load_config({**ENV, "VK_CONFIG": str(tmp_path / "nope.toml")})
