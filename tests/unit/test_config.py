"""Unit tests for configuration loading."""

from __future__ import annotations

import pytest

from moodbot.config import ConfigError, Settings

TOKEN = "1234567890:TEST-not-a-real-token"


def test_loads_required_token_from_environment():
    settings = Settings.from_env({"TELEGRAM_BOT_TOKEN": TOKEN})
    assert settings.telegram_token == TOKEN


def test_missing_token_is_a_startup_error():
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        Settings.from_env({})


def test_blank_token_is_a_startup_error():
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        Settings.from_env({"TELEGRAM_BOT_TOKEN": "   "})


def test_anthropic_key_is_optional():
    settings = Settings.from_env({"TELEGRAM_BOT_TOKEN": TOKEN})
    assert settings.anthropic_api_key is None
    assert settings.has_llm is False


def test_anthropic_key_enables_the_llm_analyzer():
    settings = Settings.from_env(
        {"TELEGRAM_BOT_TOKEN": TOKEN, "ANTHROPIC_API_KEY": "sk-ant-test"}
    )
    assert settings.has_llm is True


def test_database_path_defaults_and_can_be_overridden():
    default = Settings.from_env({"TELEGRAM_BOT_TOKEN": TOKEN})
    assert default.db_path.name == "moodbot.sqlite3"

    custom = Settings.from_env(
        {"TELEGRAM_BOT_TOKEN": TOKEN, "MOODBOT_DB_PATH": "/tmp/other.sqlite3"}
    )
    assert str(custom.db_path).endswith("other.sqlite3")


def test_model_id_defaults_to_opus_5():
    settings = Settings.from_env({"TELEGRAM_BOT_TOKEN": TOKEN})
    assert settings.model == "claude-opus-5"


def test_model_id_can_be_overridden():
    settings = Settings.from_env(
        {"TELEGRAM_BOT_TOKEN": TOKEN, "MOODBOT_MODEL": "claude-sonnet-5"}
    )
    assert settings.model == "claude-sonnet-5"


def test_request_timeout_parses_as_float():
    settings = Settings.from_env(
        {"TELEGRAM_BOT_TOKEN": TOKEN, "MOODBOT_TIMEOUT_SECONDS": "12.5"}
    )
    assert settings.request_timeout == 12.5


def test_invalid_timeout_is_a_startup_error():
    with pytest.raises(ConfigError, match="MOODBOT_TIMEOUT_SECONDS"):
        Settings.from_env(
            {"TELEGRAM_BOT_TOKEN": TOKEN, "MOODBOT_TIMEOUT_SECONDS": "soon"}
        )


def test_non_positive_timeout_is_a_startup_error():
    with pytest.raises(ConfigError, match="MOODBOT_TIMEOUT_SECONDS"):
        Settings.from_env({"TELEGRAM_BOT_TOKEN": TOKEN, "MOODBOT_TIMEOUT_SECONDS": "0"})


def test_repr_does_not_leak_the_token():
    """Settings end up in logs and tracebacks; secrets must not ride along."""
    settings = Settings.from_env(
        {"TELEGRAM_BOT_TOKEN": TOKEN, "ANTHROPIC_API_KEY": "sk-ant-secret"}
    )
    text = repr(settings)

    assert TOKEN not in text
    assert "sk-ant-secret" not in text
    assert "***" in text
