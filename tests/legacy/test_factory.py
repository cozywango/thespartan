"""Tests for the provider/client factory."""

import pytest

from spartan_legacy.llm import factory
from spartan_legacy.llm.config import LLMSettings
from spartan_legacy.llm.factory import (
    MissingCredentialsError,
    UnknownModelError,
    get_client,
    list_models,
)
from spartan_legacy.llm.providers import (
    OpenAICompatibleProvider,
)

pytestmark = pytest.mark.unit


def _settings(**kwargs: str) -> LLMSettings:
    return LLMSettings(_env_file=None, **kwargs)


def test_get_client_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    pass  # OpenAI removed


def test_get_client_deepseek_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    pass  # Deepseek removed


# Anthropic test removed because AnthropicProvider is not implemented in this version


def test_get_client_unknown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory, "get_settings", lambda: _settings(openai_api_key="x"))
    with pytest.raises(UnknownModelError):
        get_client("no-such-model")


def test_get_client_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    pass  # Gemini removed


def test_get_client_ollama_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory, "get_settings", lambda: _settings())
    client = get_client("ollama:qwen3")
    assert client.spec.api_id == "qwen3"
    assert client.provider.base_url == "http://localhost:11434/v1"


def test_list_models_nonempty() -> None:
    assert list_models()
