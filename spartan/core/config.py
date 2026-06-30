"""Configuration management for Spartan using Pydantic."""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SpartanConfig(BaseSettings):
    """Main configuration for Spartan."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Configuration
    llm_model: str = Field(
        default="ornith:1.0", description="Ollama model tag to use for the agent"
    )

    llm_api_key: str | None = Field(
        default=None, description="Optional API key (Ollama does not require one)"
    )

    llm_api_base: str = Field(
        default="http://localhost:11434/v1",
        description="OpenAI-compatible API base URL (default: local Ollama)",
    )

    # Agent Configuration
    max_iterations: int = Field(default=300, description="Maximum iterations for the agent")

    working_directory: Path = Field(
        default_factory=lambda: Path.cwd() / "workspace",
        description="Working directory for agent operations",
    )

    # Target Configuration
    target: str = Field(
        ...,  # Required
        description="Target for penetration testing (URL, IP, domain, or path)",
    )

    custom_instruction: str | None = Field(
        default=None, description="Optional custom instructions for the agent"
    )

    mode: Literal["ctf", "pentest", "passive"] = Field(
        default="ctf",
        description="Pipeline mode: 'ctf', 'pentest', or 'passive'",
    )

    verbose: bool = Field(default=True, description="Enable verbose output")

    def __init__(self, **data: Any) -> None:
        """Initialize configuration."""
        super().__init__(**data)

        # Create working directory if it doesn't exist
        # Ignore permission errors if directory already exists
        try:
            self.working_directory.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            # Directory already exists or we don't have permission to create it
            # This is fine if the directory is already available
            if not self.working_directory.exists():
                raise

    @classmethod
    def from_env(cls, **overrides: object) -> "SpartanConfig":
        """Create config from environment variables with optional overrides."""
        return cls(**overrides)


def load_config(**overrides: object) -> SpartanConfig:
    """
    Load configuration from environment with optional overrides.

    Args:
        **overrides: Keyword arguments to override config values

    Returns:
        SpartanConfig instance

    Example:
        >>> config = load_config(target="example.com", verbose=True)
    """
    # Create config with overrides
    # Note: API key is optional - Claude Code manages its own configuration
    return SpartanConfig.from_env(**overrides)
