"""Provider credentials and per-provider base-URL resolution.

Simplified to Ollama only — no cloud API keys required.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from spartan_legacy.llm.registry import PROVIDERS, ProviderInfo

# provider key -> the settings attribute holding its API key (None => no key)
_KEY_FIELD: dict[str, str | None] = {
    "ollama": None,
}


class LLMSettings(BaseSettings):
    """Environment-backed settings. Ollama needs no API key."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Optional base-URL override (default comes from the registry).
    ollama_base_url: str | None = None

    def api_key_for(self, provider: ProviderInfo) -> str | None:
        """Return the configured API key for ``provider`` (or ``None``)."""
        field = _KEY_FIELD.get(provider.key)
        if field is None:
            return None
        value = getattr(self, field, None)
        return str(value) if value else None

    def base_url_for(self, provider: ProviderInfo) -> str | None:
        """Return the base URL: explicit override, else the registry default."""
        override = getattr(self, f"{provider.key}_base_url", None)
        if override:
            return str(override)
        return provider.base_url


_settings: LLMSettings | None = None


def get_settings() -> LLMSettings:
    """Process-wide singleton settings (reads ``.env`` + environment once)."""
    global _settings
    if _settings is None:
        _settings = LLMSettings()
    return _settings


def configured_providers() -> list[str]:
    """Provider keys that currently have a usable key (or need none, e.g. Ollama)."""
    settings = get_settings()
    return [
        key
        for key, info in PROVIDERS.items()
        if not info.requires_key or settings.api_key_for(info)
    ]
