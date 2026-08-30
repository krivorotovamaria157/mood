"""Entry point: ``python -m moodbot`` (or ``python -m moodbot --check``)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

from .config import ConfigError, Settings

__all__ = ["main"]


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    # aiogram logs full update payloads at DEBUG — that is user message content.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="moodbot",
        description="Telegram bot that reflects back a structured reading of "
        "what you describe. It does not diagnose.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate configuration and exit without touching the network",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _configure_logging(args.verbose)
    load_dotenv()

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.check:
        print("Configuration OK")
        print(f"  model            : {settings.model}")
        print(f"  analyzer         : {'claude' if settings.has_llm else 'rule-based'}")
        print(f"  database         : {settings.db_path}")
        print(f"  request timeout  : {settings.request_timeout}s")
        if not settings.has_llm:
            print(
                "  note             : ANTHROPIC_API_KEY is not set, "
                "replies will use the rule-based analyzer"
            )
        return 0

    from .bot.app import run

    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
