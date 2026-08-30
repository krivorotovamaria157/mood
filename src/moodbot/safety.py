"""Deterministic crisis screening.

This runs *before* any language model sees the text, and its verdict cannot be
argued with by the message being screened. That is the whole point: whether a
user gets pointed at emergency help must not depend on an API being reachable,
on a model's judgement, or on how the message is phrased around the request.

The cost of that guarantee is that this layer is blunt. It errs toward showing
help resources, but idioms ("умираю от смеха", "this deadline is killing me")
are stripped first, because a bot that cries crisis at every joke gets muted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

__all__ = ["CrisisCategory", "CrisisSignal", "detect_crisis", "normalize"]


class CrisisCategory(StrEnum):
    SUICIDE = "suicide"
    SELF_HARM = "self_harm"
    VIOLENCE = "violence"
    MEDICAL = "medical"


@dataclass(frozen=True, slots=True)
class CrisisSignal:
    category: CrisisCategory
    matched: str


# Latin characters that render identically to Cyrillic ones. Mixed-script text
# is common by accident (keyboard layout) and occasionally on purpose.
_HOMOGLYPHS = str.maketrans(
    {
        "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у",
        "k": "к", "m": "м", "t": "т", "b": "в", "h": "н", "3": "з",
    }
)

_LATIN_WORD = re.compile(r"[a-z]{2,}")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """Fold text to a stable form for phrase matching.

    Lowercases, normalises Unicode, folds ``ё`` to ``е``, drops punctuation and
    collapses whitespace. Homoglyph mapping is applied only to runs that are not
    genuine Latin words, so English input survives intact.
    """
    if not text:
        return ""

    folded = unicodedata.normalize("NFKC", text).lower().replace("ё", "е")
    folded = _PUNCT.sub(" ", folded)
    folded = _SPACES.sub(" ", folded).strip()

    # Only de-homoglyph tokens that mix scripts; leave pure-Latin words alone.
    def _fix(token: str) -> str:
        has_cyrillic = any("Ѐ" <= ch <= "ӿ" for ch in token)
        if has_cyrillic:
            return token.translate(_HOMOGLYPHS)
        return token

    return " ".join(_fix(tok) for tok in folded.split(" ") if tok)


# Idioms that contain crisis-shaped words but are not crisis statements. These
# spans are removed before the patterns run.
_IDIOMS = [
    r"умира\w*\s+(?:от|со)\s+(?:смеха|скуки|голода|стыда|усталости)",
    r"умереть\s+(?:от|со)\s+(?:смеха|скуки|стыда|голода)",
    r"до\s+смерти\s+(?:устал\w*|надоел\w*|напуган\w*|голоден|хочется)",
    r"устал\w*\s+до\s+смерти",
    r"уби(?:л|ла|ть|вает)\w*\s+(?:весь\s+)?(?:время|день|вечер|час\w*|выходные)",
    r"(?:меня|нас)\s+убива\w+",  # "работа меня убивает"
    r"убива\w+\s+меня",
    r"killing\s+me",
    r"kill(?:ing)?\s+time",
    r"dead\s+tired",
    r"dying\s+(?:of|from)\s+(?:laughter|boredom|hunger)",
    r"scared\s+to\s+death",
]
_IDIOM_RE = re.compile("|".join(_IDIOMS))


# Ordered by precedence: the first category with a match wins.
_PATTERNS: list[tuple[CrisisCategory, re.Pattern[str]]] = [
    (
        CrisisCategory.SUICIDE,
        re.compile(
            r"не\s+хоч(?:у|ется)\s+(?:больше\s+)?жить"
            r"|жить\s+не\s+хоч(?:у|ется)"
            r"|хоч(?:у|ется)\s+(?:у|с)мереть"
            r"|хоч(?:у|ется)\s+сдохнуть"
            r"|поконч(?:ить|у|ил\w*)\s+с\s+собой"
            r"|свести\s+сч[её]ты\s+с\s+жизнью"
            r"|уйти\s+из\s+жизни"
            r"|самоубийств\w*|суицид\w*"
            r"|уби(?:ть|ю)\s+себя"
            r"|не\s+(?:вижу|видно)\s+смысла\s+жить"
            r"|нет\s+смысла\s+жить"
            r"|лучше\s+бы\s+я\s+не\s+родил\w*"
            r"|kill\s+myself"
            r"|end(?:ing)?\s+my\s+life"
            r"|want\s+to\s+die"
            r"|(?:don'?t|do\s+not)\s+want\s+to\s+live"
            r"|no\s+reason\s+to\s+live"
            r"|suicid\w*"
        ),
    ),
    (
        CrisisCategory.SELF_HARM,
        re.compile(
            r"реж(?:у|ешь|ет)\s+себя"
            r"|поре(?:зать|зал\w*)\s+себя"
            r"|причин(?:ить|яю|ял\w*)\s+себе\s+вред"
            r"|селф\s?харм|self[\s-]?harm"
            r"|бью\s+себя"
            r"|cut\s+myself"
            r"|hurt(?:ing)?\s+myself"
        ),
    ),
    (
        CrisisCategory.VIOLENCE,
        re.compile(
            r"меня\s+бьют|меня\s+бь[её]т"
            r"|он\w*\s+меня\s+бь[её]т"
            r"|меня\s+насилу\w*|изнасилов\w*"
            r"|угрожа\w+\s+уби\w+"
            r"|бо(?:юсь|ится)\s+за\s+(?:свою|его|е[её])\s+жизнь"
            r"|hits\s+me|beats\s+me"
            r"|being\s+abused|threaten\w*\s+to\s+kill"
        ),
    ),
    (
        CrisisCategory.MEDICAL,
        re.compile(
            r"не\s+могу\s+дышать"
            r"|бол[ьи]\s+в\s+груди|болит\s+в\s+груди"
            r"|теря(?:ю|л\w*)\s+сознание"
            r"|передозировк\w*"
            r"|выпил\w*\s+(?:все\s+)?таблетки"
            r"|can'?t\s+breathe|cannot\s+breathe"
            r"|chest\s+pain"
            r"|overdos\w*"
        ),
    ),
]


def detect_crisis(text: str | None) -> CrisisSignal | None:
    """Return the crisis signal found in ``text``, or ``None``.

    Categories are checked in a fixed precedence order, so a message containing
    both violence and suicidal statements reports the latter.
    """
    normalized = normalize(text)
    if not normalized:
        return None

    # Blank out idiomatic spans so they cannot satisfy a pattern.
    screened = _IDIOM_RE.sub(" ", normalized)

    for category, pattern in _PATTERNS:
        match = pattern.search(screened)
        if match:
            return CrisisSignal(category=category, matched=match.group(0).strip())

    return None
