"""Who a character is when they judge others: temperament dials and tastes.

Declared per character in story JSON (`personality`) on top of the story's
`default_personality`. Sparse characters get neutral defaults: no invented
dealbreakers, no invented dislikes beyond the story defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backend.app.engine.world_model.deception import DeceptionProfile

DIALS = ("patience", "jealousy", "forgiveness", "skepticism", "openness", "pride")
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


@dataclass(frozen=True)
class Personality:
    temperament: Temperament = field(default_factory=Temperament)
    tastes: dict[str, float] = field(default_factory=dict)
    deception: DeceptionProfile = field(default_factory=DeceptionProfile)

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
    return Personality(_temperament(own.get("temperament"), default.temperament),
                       _tastes(own.get("tastes"), default.tastes, vocabulary),
                       _deception(own.get("deception") or default_raw.get("deception") or {}))


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
