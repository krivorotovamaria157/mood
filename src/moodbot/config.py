"""Configuration, read explicitly from a mapping rather than at import time.

`Settings.from_env` takes the environment as an argument so tests can hand it a
dict instead of mutating `os.environ`. The real entry point passes `os.environ`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

__all__ = ["ConfigError", "Settings"]

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_DB_FILENAME = "moodbot.sqlite3"
DEFAULT_TIMEOUT_SECONDS = 45.0


class ConfigError(RuntimeError):
    """Configuration is missing or unusable — the process should not start."""


def _redact(value: str | None) -> str:
    return "***" if value else "unset"


@dataclass(frozen=True, slots=True, repr=False)
class Settings:
    telegram_token: str
    anthropic_api_key: str | None
    db_path: Path
    model: str
    request_timeout: float

    @property
    def has_llm(self) -> bool:
        """Whether the Claude-backed analyzer can be built at all."""
        return bool(self.anthropic_api_key)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env

        token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise ConfigError(
                "TELEGRAM_BOT_TOKEN is not set. Put it in the environment or in a "
                "local .env file — never in source."
            )

        api_key = (env.get("ANTHROPIC_API_KEY") or "").strip() or None

        raw_timeout = (env.get("MOODBOT_TIMEOUT_SECONDS") or "").strip()
        if raw_timeout:
            try:
                timeout = float(raw_timeout)
            except ValueError as exc:
                raise ConfigError(
                    f"MOODBOT_TIMEOUT_SECONDS must be a number, got {raw_timeout!r}"
                ) from exc
            if timeout <= 0:
                raise ConfigError(
                    f"MOODBOT_TIMEOUT_SECONDS must be positive, got {timeout}"
                )
        else:
            timeout = DEFAULT_TIMEOUT_SECONDS

        db_raw = (env.get("MOODBOT_DB_PATH") or "").strip()
        db_path = Path(db_raw) if db_raw else Path(DEFAULT_DB_FILENAME)

        return cls(
            telegram_token=token,
            anthropic_api_key=api_key,
            db_path=db_path,
            model=(env.get("MOODBOT_MODEL") or "").strip() or DEFAULT_MODEL,
            request_timeout=timeout,
        )

    def __repr__(self) -> str:  # pragma: no cover - exercised via test_repr
        return (
            "Settings("
            f"telegram_token={_redact(self.telegram_token)}, "
            f"anthropic_api_key={_redact(self.anthropic_api_key)}, "
            f"db_path={self.db_path!s}, "
            f"model={self.model!r}, "
            f"request_timeout={self.request_timeout})"
        )
