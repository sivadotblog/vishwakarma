"""Tests for `build_model` model routing."""

from pathlib import Path

import pytest
from pydantic_ai.models.google import GoogleModel

from vk.config import Config, ConfigError, build_model, load_config


def make_cfg(model: str, **clan_models: str) -> Config:
    return Config(
        repo="o/r",
        github_token="t",
        model=model,
        clan_models=clan_models,
        state_dir=Path("/tmp/vk-test"),
    )


def test_native_string_passes_through() -> None:
    assert build_model(make_cfg("anthropic:claude-x"), "analyst", {}) == "anthropic:claude-x"


def test_clan_override_wins() -> None:
    cfg = make_cfg("anthropic:a", analyst="openai:b")
    assert build_model(cfg, "analyst", {}) == "openai:b"


def test_legacy_litellm_string_is_rejected() -> None:
    with pytest.raises(ConfigError, match="provider:model"):
        build_model(make_cfg("gemini/gemini-3.5-flash"), "analyst", {})


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
    base = {"GITHUB_TOKEN": "t", "VK_MODEL": "m", "VK_REPO": "o/r"}
    assert load_config(base).bot_login is None
    assert load_config({**base, "VK_BOT_LOGIN": "vk-app[bot]"}).bot_login == "vk-app[bot]"
