"""User-facing safety copy.

Kept apart from the detection logic so the wording can be reviewed on its own —
this is the text a person reads at the worst moment they will use this bot.

Tone rules applied here: name what was noticed without dramatising it, say
plainly that a bot is the wrong helper for this, and give one concrete thing to
do next. No diagnosis, no reassurance that the feeling will pass, no advice that
substitutes for a person.
"""

from __future__ import annotations

from .models import Analysis, Recommendation, RiskLevel, Urgency
from .safety import CrisisCategory

__all__ = ["DISCLAIMER", "crisis_analysis"]

DISCLAIMER = (
    "Я не ставлю диагнозов и не заменяю врача или психолога. "
    "Это заметки для самонаблюдения, а не медицинское заключение."
)

_EMERGENCY = "112"
_AMBULANCE = "103"

_SUMMARIES: dict[CrisisCategory, str] = {
    CrisisCategory.SUICIDE: (
        "В твоём сообщении есть слова о том, что жить не хочется. "
        f"Я бот и не смогу здесь помочь — с этим нужен живой человек. "
        f"Позвони по номеру {_EMERGENCY}: это бесплатно, круглосуточно и с любого телефона."
    ),
    CrisisCategory.SELF_HARM: (
        "Похоже, речь о том, что ты причиняешь себе вред. "
        f"Это то, с чем не стоит оставаться один на один. Единый номер экстренных "
        f"служб — {_EMERGENCY}, звонок бесплатный и круглосуточный."
    ),
    CrisisCategory.VIOLENCE: (
        "Из сообщения похоже, что тебе угрожает опасность от другого человека. "
        f"Твоя безопасность сейчас важнее всего остального. Экстренный номер — {_EMERGENCY}."
    ),
    CrisisCategory.MEDICAL: (
        "То, что ты описываешь, может быть острым состоянием, а не только реакцией "
        f"на стресс. Не жди, пока пройдёт: скорая — {_AMBULANCE}, "
        f"единый экстренный номер — {_EMERGENCY}."
    ),
}

_STEPS: dict[CrisisCategory, tuple[tuple[str, str], ...]] = {
    CrisisCategory.SUICIDE: (
        (
            f"Позвони на {_EMERGENCY} или в местную кризисную линию",
            "там отвечают люди, обученные именно таким разговорам",
        ),
        (
            "Скажи о своём состоянии тому, кто рядом",
            "вслух и другому человеку — это уже снимает часть груза",
        ),
        (
            "Если есть чем себе навредить — отдай это кому-то или убери подальше",
            "решения, принятые в таком состоянии, не отражают тебя обычного",
        ),
    ),
    CrisisCategory.SELF_HARM: (
        (
            f"Позвони на {_EMERGENCY} или обратись к врачу",
            "если есть рана, ей нужна помощь прямо сейчас",
        ),
        (
            "Напиши или позвони человеку, которому доверяешь",
            "быть в этом одному тяжелее, чем кажется",
        ),
    ),
    CrisisCategory.VIOLENCE: (
        (
            f"Если опасность прямо сейчас — звони {_EMERGENCY}",
            "это приоритет выше любого разбора эмоций",
        ),
        (
            "Подумай, где можно переночевать в безопасном месте",
            "у друзей, родственников, в кризисном центре",
        ),
    ),
    CrisisCategory.MEDICAL: (
        (
            f"Вызови скорую — {_AMBULANCE} или {_EMERGENCY}",
            "боль в груди и нехватка воздуха требуют осмотра, а не ожидания",
        ),
        (
            "Не оставайся один, пока не приедет помощь",
            "рядом должен быть кто-то, кто сможет открыть дверь и рассказать врачу",
        ),
    ),
}


def crisis_analysis(category: CrisisCategory) -> Analysis:
    """Build the reply that replaces the normal analysis for a crisis message."""
    summary = _SUMMARIES[category]
    steps = _STEPS[category]

    return Analysis(
        summary=summary,
        risk_level=RiskLevel.CRISIS,
        urgency=Urgency.NOW,
        observations=(),
        recommendations=tuple(
            Recommendation(action=action, rationale=rationale)
            for action, rationale in steps
        ),
        needs_professional_help=True,
        source="safety",
    )
