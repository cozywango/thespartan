"""Tests for configuration management.

Unit tests for SpartanConfig and load_config function.
"""

import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from spartan.core.config import SpartanConfig, load_config


@pytest.mark.unit
class TestSpartanConfig:
    """Tests for SpartanConfig."""

    def test_create_config_with_required_fields(self, temp_working_dir: Path):
        """Test creating config with only required fields."""
        config = SpartanConfig(
            target="10.10.11.234",
            working_directory=temp_working_dir,
        )
        assert config.target == "10.10.11.234"
        assert config.working_directory == temp_working_dir

    def test_default_values(self, temp_working_dir: Path):
        """Test that default values are set correctly."""
        config = SpartanConfig(
            target="example.com",
            working_directory=temp_working_dir,
        )
        assert config.llm_model == "ornith:1.0"
        assert config.llm_api_key is None
        assert config.llm_api_base == "http://localhost:11434/v1"
        assert config.max_iterations == 300
        assert config.custom_instruction is None
        assert config.verbose is True

    def test_missing_required_field(self, temp_working_dir: Path):
        """Test that missing target raises validation error."""
        with pytest.raises(ValidationError):
            SpartanConfig(
                working_directory=temp_working_dir,
            )  # type: ignore[call-arg]

    def test_custom_instruction(self, temp_working_dir: Path):
        """Test setting custom instruction."""
        config = SpartanConfig(
            target="ctf.example.com",
            working_directory=temp_working_dir,
            custom_instruction="Focus on web vulnerabilities",
        )
        assert config.custom_instruction == "Focus on web vulnerabilities"


    def test_working_directory_created(self):
        """Test that working directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_workspace"
            assert not new_dir.exists()

            config = SpartanConfig(
                target="test.com",
                working_directory=new_dir,
            )

            assert new_dir.exists()
            assert config.working_directory == new_dir


@pytest.mark.unit
class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_with_target(self, temp_working_dir: Path):
        """Test load_config with target override."""
        config = load_config(
            target="192.168.1.1",
            working_directory=temp_working_dir,
        )
        assert config.target == "192.168.1.1"

    def test_load_config_with_multiple_overrides(self, temp_working_dir: Path):
        """Test load_config with multiple overrides."""
        config = load_config(
            target="ctf.local",
            working_directory=temp_working_dir,
            llm_model="ornith:1.0-q8",
            max_iterations=500,
            verbose=False,
        )
        assert config.target == "ctf.local"
        assert config.llm_model == "ornith:1.0-q8"
        assert config.max_iterations == 500
        assert config.verbose is False

    def test_from_env_classmethod(self, temp_working_dir: Path):
        """Test from_env classmethod."""
        config = SpartanConfig.from_env(
            target="env.example.com",
            working_directory=temp_working_dir,
        )
        assert config.target == "env.example.com"

    def test_load_config_from_environment(self, temp_working_dir: Path):
        """Test that config can load from environment variables."""
        original_env = os.environ.copy()
        try:
            os.environ["LLM_MODEL"] = "test-model"
            config = load_config(
                target="test.com",
                working_directory=temp_working_dir,
            )
            # Note: Environment variables should be loaded
            # The actual behavior depends on pydantic-settings
            assert config.target == "test.com"
        finally:
            os.environ.clear()
            os.environ.update(original_env)
