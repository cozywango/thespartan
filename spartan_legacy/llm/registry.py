"""Curated model registry — Ornith 1.0 via Ollama only.

This is the single source of truth for supported models. The previous
multi-provider registry (OpenAI, Anthropic, Gemini, DeepSeek, xAI, Qwen,
Moonshot) has been replaced by a focused Ollama-only configuration for the
Ornith 1.0 local model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    """Connection metadata for one provider."""

    key: str
    label: str
    kind: str  # "openai" (all Ollama-compatible providers use this)
    env: str | None = None
    env_alt: tuple[str, ...] = ()
    base_url: str | None = None
    requires_key: bool = True


@dataclass(frozen=True)
class ModelSpec:
    """One supported model."""

    id: str
    provider: str
    context_window: int
    tier: str  # "flagship" | "balanced" | "fast" | "local"
    api_id: str = ""
    legacy: bool = False
    reasoning: bool = False
    max_tokens_param: str = "max_tokens"
    responses_api: bool = False
    aliases: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.api_id:
            object.__setattr__(self, "api_id", self.id)


# --------------------------------------------------------------------------- #
# Providers — Ollama only
# --------------------------------------------------------------------------- #

PROVIDERS: dict[str, ProviderInfo] = {
    "ollama": ProviderInfo(
        key="ollama",
        label="Ollama (local)",
        kind="openai",
        env=None,
        base_url="http://localhost:11434/v1",
        requires_key=False,
    ),
}

OLLAMA_PREFIX = "ollama:"

# --------------------------------------------------------------------------- #
# Models — Ornith 1.0
# --------------------------------------------------------------------------- #

_MODEL_LIST: list[ModelSpec] = [
    ModelSpec(
        "ollama:ornith",
        "ollama",
        128_000,
        "flagship",
        api_id="ornith:1.0",
        notes="Ornith 1.0 — primary local pentesting model",
    ),
]

# Registry keyed by canonical id (and by alias) for O(1) lookup.
MODELS: dict[str, ModelSpec] = {}
_ALIASES: dict[str, str] = {}
for _spec in _MODEL_LIST:
    MODELS[_spec.id] = _spec
    for _alias in _spec.aliases:
        _ALIASES[_alias] = _spec.id


def all_model_ids() -> list[str]:
    """All canonical, user-selectable model ids (registry order)."""
    return [spec.id for spec in _MODEL_LIST]


def resolve(name: str) -> ModelSpec | None:
    """Resolve a model id or alias to a :class:`ModelSpec`.

    Supports the dynamic ``ollama:<model>`` form for arbitrary local models.
    Returns ``None`` if unknown.
    """
    if name.startswith(OLLAMA_PREFIX):
        local = name[len(OLLAMA_PREFIX) :].strip()
        if not local:
            return None
        # Check if it's a known registered model first.
        if name in MODELS:
            return MODELS[name]
        # Dynamic Ollama model — create a spec on the fly.
        return ModelSpec(
            id=name,
            provider="ollama",
            api_id=local,
            context_window=128_000,
            tier="local",
            notes="User-configured local Ollama model",
        )
    if name in MODELS:
        return MODELS[name]
    if name in _ALIASES:
        return MODELS[_ALIASES[name]]
    return None


def models_by_provider() -> dict[str, list[ModelSpec]]:
    """Group registry models by provider key (registry order preserved)."""
    grouped: dict[str, list[ModelSpec]] = {}
    for spec in _MODEL_LIST:
        grouped.setdefault(spec.provider, []).append(spec)
    return grouped


# Defaults for the three sessions — all point to Ornith via Ollama.
DEFAULT_REASONING_PREFERENCE: tuple[str, ...] = ("ollama:ornith",)
DEFAULT_PARSING_PREFERENCE: tuple[str, ...] = ("ollama:ornith",)

ALL_SPECS: tuple[ModelSpec, ...] = tuple(_MODEL_LIST)
