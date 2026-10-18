"""Tests for `build_model` model routing."""

from pathlib import Path

import pytest
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel

from vk.config import Config, ConfigError, build_model


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


def test_gateway_url_builds_openai_chat_model() -> None:
    env = {"VK_LLM_BASE_URL": "http://gw.local/v1", "VK_LLM_API_KEY": "k"}
    model = build_model(make_cfg("whatever"), "analyst", env)
    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "whatever"
    assert str(model.client.base_url).startswith("http://gw.local/v1")


def test_google_uses_gemini_api_key() -> None:
    model = build_model(make_cfg("google:gemini-x"), "analyst", {"GEMINI_API_KEY": "gem"})
    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-x"
    assert model.client._api_client.api_key == "gem"


def test_google_reads_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VK_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gem")
    model = build_model(make_cfg("google:gemini-x"), "analyst")
    assert isinstance(model, GoogleModel)


def test_google_without_gemini_key_defers_to_provider() -> None:
    assert build_model(make_cfg("google:gemini-x"), "analyst", {}) == "google:gemini-x"
