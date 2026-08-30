"""Wiring: build the object graph from settings, then run.

Everything above this module takes its dependencies as arguments. This is the
one place that decides which concrete implementations get used, which is why it
is also the only place that needs an API key or a token.
"""

from __future__ import annotations

import logging

from ..analyzer.base import Analyzer
from ..analyzer.fallback import RuleBasedAnalyzer
from ..config import Settings
from ..service import ReflectionService
from ..storage.repository import EntryRepository
from .handlers import BotHandlers

__all__ = ["build_analyzer", "build_handlers", "run"]

logger = logging.getLogger(__name__)


def build_analyzer(settings: Settings) -> Analyzer:
    """Claude when a key is configured, rules otherwise.

    The fallback is not a degraded mode to apologise for — without a key it is
    the whole product, and it still answers.
    """
    fallback = RuleBasedAnalyzer()

    if not settings.has_llm:
        logger.info("ANTHROPIC_API_KEY not set — using the rule-based analyzer")
        return fallback

    # Imported here so the package stays importable (and testable) even if the
    # SDK is absent from a minimal environment.
    from anthropic import AsyncAnthropic

    from ..analyzer.claude import ClaudeAnalyzer

    return ClaudeAnalyzer(
        client=AsyncAnthropic(api_key=settings.anthropic_api_key),
        model=settings.model,
        timeout=settings.request_timeout,
        fallback=fallback,
    )


def build_handlers(settings: Settings) -> BotHandlers:
    repository = EntryRepository(settings.db_path)
    repository.initialize()

    return BotHandlers(
        service=ReflectionService(analyzer=build_analyzer(settings)),
        repository=repository,
    )


async def run(settings: Settings) -> None:
    """Start long polling. Blocks until interrupted."""
    from .telegram import build_bot, build_dispatcher

    handlers = build_handlers(settings)
    bot = build_bot(settings.telegram_token)
    dispatcher = build_dispatcher(handlers)

    logger.info(
        "starting long polling (model=%s, llm=%s)",
        settings.model,
        "on" if settings.has_llm else "off",
    )
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
