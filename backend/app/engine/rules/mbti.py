"""The sixteen MBTI types, as short behavior glosses for engine consumers.

`rules/personality.py` already treats a character's four-letter type as a
DEFAULTS source for three temperament dials (sociability/candor/planfulness).
This module is the second, independent use of that same code: a plain-English
line of what the type tends to do under social pressure, handed to anything
that asks an LLM to behave as, or judge, that character (dialogue generation,
Jev's accept/reject verdicts, the finale panel). Four bare letters mean
nothing to a model without this.
"""
from __future__ import annotations

import re

_TYPE_RE = re.compile(r"^[EI][SN][TF][JP]$")

GLOSS: dict[str, str] = {
    "ISTJ": "dutiful and literal; keeps promises, distrusts spontaneity, slow to warm up",
    "ISFJ": "quietly caring and loyal; avoids conflict, notices what others need before they ask",
    "INFJ": "private and perceptive; reads people well, commits fully once convinced, withdraws when hurt",
    "INTJ": "strategic and self-contained; plans ahead, unsentimental, respects competence over charm",
    "ISTP": "cool and practical; acts rather than explains, dislikes being pinned down emotionally",
    "ISFP": "gentle and values-led; avoids confrontation, needs harmony, quietly stubborn about what matters to them",
    "INFP": "idealistic and conflict-averse; feels things deeply but says little, loyal once trust is earned",
    "INTP": "detached and analytical; questions everything, uncomfortable performing emotion on demand",
    "ESTP": "bold and impulsive; acts first, charms easily, gets bored of slow or indirect people",
    "ESFP": "warm and attention-loving; thrives on company and drama, says yes to the moment, forgets later",
    "ENFP": "enthusiastic and emotionally open; falls fast, overshares, loses interest if things feel flat",
    "ENTP": "argumentative and quick-witted; provokes to test people, respects a sharp comeback",
    "ESTJ": "direct and organized; leads, states opinions as fact, impatient with excuses",
    "ESFJ": "sociable and dutiful; keeps the group warm, seeks approval, takes personal slights hard",
    "ENFJ": "warm and persuasive; manages others' feelings, genuinely wants people to do well, overextends for them",
    "ENTJ": "commanding and decisive; controls the narrative, unshaken under pressure, impatient with weakness",
}


def normalize(code: str | None) -> str:
    """Uppercase a four-letter type if valid, else ''."""
    value = str(code or "").strip().upper()
    return value if _TYPE_RE.match(value) else ""


def gloss(code: str | None) -> str:
    """Short behavior line for a type, or '' if the code is unrecognized."""
    return GLOSS.get(normalize(code), "")
