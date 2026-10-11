"""How well a character knows the player, and how they should behave because of it (generic, any story).

Declared in story JSON under `acquaintance`::

    "acquaintance": {"levels": [
      {"id": "strangers", "min_days": 0, "min_turns": 0, "conduct": "Polite and a little stiff; no shared history."},
      {"id": "familiar", "min_days": 1, "min_turns": 30, "conduct": "First names and easy teasing."}
    ]}

A level is reached when BOTH thresholds hold (days since they met the player, and the turns they have spent in the
player's company); the highest level reached wins. The level is independent of any romance track: closeness is earned
by time together, so a character never acts like an old friend of someone they met a few turns ago. The conduct text
goes into that character's line of the scene contract every turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AcquaintanceLevel:
    id: str
    min_days: int
    min_turns: int
    conduct: str
    reminder: str = ""      # a short form for the per-turn header beside the player's message (default: the conduct)


def acquaintance_levels(story_cfg: dict[str, Any]) -> tuple[AcquaintanceLevel, ...]:
    """Parse and validate `acquaintance.levels`; empty when the story declares none."""
    raw = ((story_cfg or {}).get("acquaintance") or {}).get("levels") or []
    levels = tuple(AcquaintanceLevel(str(item["id"]).strip(), int(item["min_days"]), int(item["min_turns"]),
                                     str(item["conduct"]).strip(),
                                     str(item.get("reminder") or "").strip()) for item in raw)
    if not levels:
        return ()
    if len({level.id for level in levels}) != len(levels):
        raise ValueError("acquaintance levels need distinct ids")
    if levels[0].min_days != 0 or levels[0].min_turns != 0:
        raise ValueError("the first acquaintance level must start at 0 days and 0 turns")
    for before, after in zip(levels, levels[1:]):
        if after.min_days < before.min_days or after.min_turns < before.min_turns or \
                (after.min_days, after.min_turns) == (before.min_days, before.min_turns):
            raise ValueError(f"acquaintance level {after.id!r} must ask for more time than {before.id!r}")
    if any(not level.id or not level.conduct for level in levels):
        raise ValueError("every acquaintance level needs an id and conduct text")
    return levels


def level_for(levels: tuple[AcquaintanceLevel, ...], days_known: int, turns_together: int) -> Optional[AcquaintanceLevel]:
    """The highest level whose day and turn thresholds are both met (None when no levels are declared)."""
    reached = None
    for level in levels:
        if days_known >= level.min_days and turns_together >= level.min_turns:
            reached = level
    return reached
