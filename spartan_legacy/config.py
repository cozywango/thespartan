"""App-level configuration helpers for the modernized legacy Spartan.

Simplified to Ollama-only: always uses Ornith 1.0 as the default model.
"""

from __future__ import annotations

from spartan_legacy.llm.config import (
    LLMSettings,
    configured_providers,
    get_settings,
)
from spartan_legacy.llm.registry import (
    DEFAULT_PARSING_PREFERENCE,
    DEFAULT_REASONING_PREFERENCE,
    resolve,
)

__all__ = [
    "LLMSettings",
    "configured_providers",
    "default_parsing_model",
    "default_reasoning_model",
    "get_settings",
]


def _first_available(preference: tuple[str, ...]) -> str | None:
    ready = set(configured_providers())
    for model_id in preference:
        spec = resolve(model_id)
        if spec is not None and spec.provider in ready:
            return model_id
    return None


def default_reasoning_model() -> str | None:
    """Best available reasoning model given configured providers (or None)."""
    return _first_available(DEFAULT_REASONING_PREFERENCE)


def default_parsing_model() -> str | None:
    """Best available parsing model given configured providers (or None)."""
    return _first_available(DEFAULT_PARSING_PREFERENCE)
