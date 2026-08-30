"""Bot logic, free of any Telegram framework.

Handlers take plain values and return a list of ready-to-send message strings.
That keeps every branch — including the failure branches, which are the ones
that matter — testable without constructing framework objects or a network.

The adapter in :mod:`moodbot.bot.telegram` is the only place that knows aiogram
exists.
"""

from __future__ import annotations

import logging
from html import escape
from typing import Protocol, Sequence

from ..models import Analysis, Entry
from ..safety_texts import DISCLAIMER
from ..service import ReflectionService
from .formatting import render_analysis, split_message

__all__ = ["MAX_INPUT_CHARS", "BotHandlers"]

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 4000
HISTORY_FOR_ANALYSIS = 5
HISTORY_TO_SHOW = 10

_GREETING = (
    "<b>Дневник состояния</b>\n\n"
    "Опиши своими словами, что происходит: что ты чувствуешь, что этому "
    "предшествовало, как это отзывается в теле. Можно без структуры — "
    "одним потоком.\n\n"
    "В ответ я разберу описание: что в нём видно, насколько это требует "
    "внимания и что можно сделать.\n\n"
    "/help — команды"
)

_HELP = (
    "<b>Команды</b>\n\n"
    "/start — как этим пользоваться\n"
    "/help — этот список\n"
    "/history — последние записи\n"
    "/delete_me — удалить все мои данные\n\n"
    "Всё остальное я читаю как описание состояния."
)

_ASK_FOR_TEXT = (
    "Напиши пару предложений о том, что происходит — что чувствуешь и что "
    "этому предшествовало. По пустому сообщению разбирать нечего."
)

_TRUNCATED_NOTE = (
    f"<i>Сообщение длинное, я взял первые {MAX_INPUT_CHARS} символов.</i>"
)

_ANALYSIS_FAILED = (
    "Разобрать описание не получилось — что-то сломалось на моей стороне. "
    "Попробуй ещё раз через минуту; запись при этом не потерялась."
)

_NOT_SAVED_NOTE = "<i>Разбор готов, но сохранить запись не удалось.</i>"

_NO_HISTORY = "Записей пока нет. Напиши, что происходит, — и появится первая."

_HISTORY_UNAVAILABLE = "Не получилось прочитать историю — попробуй чуть позже."

_DELETE_FAILED = "Не получилось удалить данные — попробуй ещё раз чуть позже."


class Repository(Protocol):
    """The slice of the repository the handlers actually use."""

    async def add(self, entry: Entry, analysis: Analysis) -> int: ...
    async def recent_texts(self, user_id: int, limit: int = ...) -> list[str]: ...
    async def history(self, user_id: int, limit: int = ...) -> Sequence: ...
    async def delete_user(self, user_id: int) -> int: ...


class BotHandlers:
    def __init__(self, service: ReflectionService, repository: Repository) -> None:
        self._service = service
        self._repo = repository

    # -- commands ----------------------------------------------------------

    async def start(self) -> list[str]:
        return split_message(f"{_GREETING}\n\n<i>{DISCLAIMER}</i>")

    async def help(self) -> list[str]:
        return split_message(_HELP)

    async def history(self, user_id: int) -> list[str]:
        try:
            records = await self._repo.history(user_id, HISTORY_TO_SHOW)
        except Exception as exc:
            logger.warning("history read failed (%s)", type(exc).__name__)
            return split_message(_HISTORY_UNAVAILABLE)

        if not records:
            return split_message(_NO_HISTORY)

        lines = ["<b>Последние записи</b>", ""]
        for record in records:
            date = str(record.created_at)[:10]
            lines.append(f"<b>{date}</b> — {escape(record.text)}")
            if record.summary:
                lines.append(f"<i>{escape(record.summary)}</i>")
            lines.append("")

        return split_message("\n".join(lines).strip())

    async def delete_me(self, user_id: int) -> list[str]:
        try:
            removed = await self._repo.delete_user(user_id)
        except Exception as exc:
            logger.warning("delete failed (%s)", type(exc).__name__)
            return split_message(_DELETE_FAILED)

        return split_message(
            f"Удалено записей: {removed}. Больше о тебе ничего не хранится."
        )

    # -- free text ---------------------------------------------------------

    async def on_text(self, user_id: int, text: str | None) -> list[str]:
        cleaned = (text or "").strip()
        if not cleaned:
            return split_message(_ASK_FOR_TEXT)

        truncated = len(cleaned) > MAX_INPUT_CHARS
        cleaned = cleaned[:MAX_INPUT_CHARS]

        history = await self._safe_history(user_id)

        try:
            analysis = await self._service.analyze(cleaned, history)
        except Exception as exc:
            # The analyzer is supposed to degrade internally; if it still threw,
            # the user gets an apology rather than silence.
            logger.warning("analysis failed (%s)", type(exc).__name__)
            return split_message(_ANALYSIS_FAILED)

        saved = await self._safe_store(user_id, cleaned, analysis)

        chunks = render_analysis(analysis)
        notes = [note for note in (_TRUNCATED_NOTE if truncated else None,
                                   None if saved else _NOT_SAVED_NOTE) if note]
        if notes:
            chunks += split_message("\n".join(notes))

        return chunks

    # -- resilience helpers ------------------------------------------------

    async def _safe_history(self, user_id: int) -> list[str]:
        """History is a nice-to-have; losing it must not lose the reply."""
        try:
            return await self._repo.recent_texts(user_id, HISTORY_FOR_ANALYSIS)
        except Exception as exc:
            logger.warning("history read failed (%s)", type(exc).__name__)
            return []

    async def _safe_store(self, user_id: int, text: str, analysis: Analysis) -> bool:
        try:
            await self._repo.add(Entry(user_id=user_id, text=text), analysis)
            return True
        except Exception as exc:
            logger.warning("store failed (%s)", type(exc).__name__)
            return False
