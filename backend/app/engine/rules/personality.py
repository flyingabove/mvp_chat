"""Who a character is when they judge others: temperament dials and tastes.

Declared per character in story JSON (`personality`) on top of the story's
`default_personality`. Sparse characters get neutral defaults: no invented
dealbreakers, no invented dislikes beyond the story defaults.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.app.engine.world_model.deception import DeceptionProfile

DIALS = ("patience", "jealousy", "forgiveness", "skepticism", "openness", "pride",
         "sociability", "planfulness", "candor")
NEUTRAL = 0.5
MAX_TASTE = 3.0


@dataclass(frozen=True)
class Temperament:
    patience: float = NEUTRAL
    jealousy: float = NEUTRAL
    forgiveness: float = NEUTRAL
    skepticism: float = NEUTRAL
    openness: float = NEUTRAL
    pride: float = NEUTRAL
    sociability: float = NEUTRAL      # outgoing and talkative (1) vs reserved (0): room energy, how often they signal
    planfulness: float = NEUTRAL      # plans ahead and commits to plans (1) vs spontaneous (0)
    candor: float = NEUTRAL           # says things plainly (1) vs softens or hints (0)


# A four-letter type (e.g. "ENFP") supplies DEFAULTS for three social dials; an author's explicit dials always win.
_TYPE_RE = re.compile(r"^[EI][SN][TF][JP]$")
_TYPE_DIALS = (("sociability", 0, {"E": 0.8, "I": 0.25}), ("candor", 2, {"T": 0.7, "F": 0.4}),
               ("planfulness", 3, {"J": 0.75, "P": 0.3}))

# How someone pursues what they want. `aim_scale` multiplies the priority of their own romantic/relational aims;
# the other strategies' extra behaviour (scheming, safe picks) is added by the intrigue mechanisms (BL-81..83).
STRATEGIES = {"open": 1.0, "fast_mover": 1.35, "patient": 0.7, "scheming": 1.0, "safe_pick": 0.9, "career_first": 0.5}


@dataclass(frozen=True)
class StrategyMods:
    aim_scale: float = 1.0


def strategy_mods(name: str) -> StrategyMods:
    return StrategyMods(STRATEGIES.get(name, 1.0))


@dataclass(frozen=True)
class Personality:
    temperament: Temperament = field(default_factory=Temperament)
    tastes: dict[str, float] = field(default_factory=dict)
    deception: DeceptionProfile = field(default_factory=DeceptionProfile)
    type: str = ""                    # optional four-letter type; "" = none
    strategy: str = "open"            # one of STRATEGIES

    def taste(self, tag: str) -> float:
        return self.tastes.get(tag, 0.0)


def _temperament(raw: dict[str, Any], base: Temperament) -> Temperament:
    values = {dial: getattr(base, dial) for dial in DIALS}
    for dial, value in (raw or {}).items():
        if dial not in DIALS:
            raise ValueError(f"unknown temperament dial {dial!r}")
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"temperament {dial} must be within 0..1")
        values[dial] = value
    return Temperament(**values)


def _type(raw: Any) -> str:
    if raw in (None, ""):
        return ""
    code = str(raw).strip().upper() if isinstance(raw, str) else ""
    if not _TYPE_RE.match(code):
        raise ValueError(f"personality type must be four letters like 'ENFP', got {raw!r}")
    return code


def _with_type(base: Temperament, code: str) -> Temperament:
    if not code:
        return base
    values = {dial: getattr(base, dial) for dial in DIALS}
    for dial, index, table in _TYPE_DIALS:
        values[dial] = table[code[index]]
    return Temperament(**values)


def _strategy(raw: Any) -> str:
    name = str(raw or "open").strip().lower()
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy {name!r}; choose from {sorted(STRATEGIES)}")
    return name


def _tastes(raw: dict[str, Any], base: dict[str, float], vocabulary: Optional[set[str]]) -> dict[str, float]:
    tastes = dict(base)
    for tag, weight in (raw or {}).items():
        if vocabulary is not None and tag not in vocabulary:
            raise ValueError(f"taste {tag!r} is not in the behavior vocabulary")
        weight = float(weight)
        if abs(weight) > MAX_TASTE:
            raise ValueError(f"taste {tag!r} must be within +-{MAX_TASTE}")
        tastes[tag] = weight
    return tastes


def personality_for(story_cfg: dict[str, Any], character: Optional[dict[str, Any]]) -> Personality:
    cfg = story_cfg or {}
    vocabulary = set(cfg.get("behavior_tag_vocabulary") or []) or None
    default_raw = cfg.get("default_personality") or {}
    default = Personality(_temperament(default_raw.get("temperament"), Temperament()),
                          _tastes(default_raw.get("tastes"), {}, vocabulary))
    character = character or {}
    own = character.get("personality") or (cfg.get("personalities") or {}).get(str(character.get("key"))) or {}
    code = _type(own.get("type"))
    return Personality(_temperament(own.get("temperament"), _with_type(default.temperament, code)),
                       _tastes(own.get("tastes"), default.tastes, vocabulary),
                       _deception(own.get("deception") or default_raw.get("deception") or {}),
                       code, _strategy(own.get("strategy")))


def _deception(raw: dict[str, Any]) -> DeceptionProfile:
    values = {}
    for dial, value in raw.items():
        if dial not in ("skill", "composure"):
            raise ValueError(f"unknown deception dial {dial!r}")
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"deception {dial} must be within 0..1")
        values[dial] = value
    return DeceptionProfile(**values)


def personalities(story_cfg: dict[str, Any]) -> dict[str, Personality]:
    """Every authored character's personality, validated (raises on bad content)."""
    cfg = story_cfg or {}
    keys = {str(c.get("key")) for c in cfg.get("characters") or []}
    unknown = set(cfg.get("personalities") or {}) - keys
    if unknown:
        raise ValueError(f"personalities for unknown characters: {sorted(unknown)}")
    return {str(c.get("key")): personality_for(cfg, c) for c in cfg.get("characters") or []}
