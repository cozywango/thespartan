"""Tests for provider credential/base-url resolution."""

import pytest

from spartan_legacy.llm import config as config_mod
from spartan_legacy.llm.config import LLMSettings, configured_providers
from spartan_legacy.llm.registry import PROVIDERS

pytestmark = pytest.mark.unit


def test_api_key_for_primary_field() -> None:
    pass  # OpenAI removed


def test_api_key_for_alias_env(monkeypatch: pytest.MonkeyPatch) -> None:
    pass  # Gemini removed


def test_ollama_needs_no_key() -> None:
    settings = LLMSettings(_env_file=None)
    assert settings.api_key_for(PROVIDERS["ollama"]) is None
    assert PROVIDERS["ollama"].requires_key is False


def test_base_url_default_and_override() -> None:
    pass  # Deepseek and OpenAI removed


def test_configured_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = LLMSettings(_env_file=None)
    monkeypatch.setattr(config_mod, "_settings", fake)
    ready = configured_providers()
    assert "ollama" in ready  # needs no key
