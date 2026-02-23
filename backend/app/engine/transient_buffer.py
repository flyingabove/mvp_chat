from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from backend.app.config.settings import TRANSIENT_KNOWLEDGE_TURNS


@dataclass
class TransientKnowledge:
    text: str
    turns_remaining: int = TRANSIENT_KNOWLEDGE_TURNS

    def decay_one_turn(self) -> bool:
        self.turns_remaining = int(self.turns_remaining) - 1
        if self.turns_remaining <= 0:
            return True
        return False


@dataclass
class SceneKnowledge:
    """Per-turn scene knowledge object stored in FIFO order.

    This object intentionally does not track turn counters internally.
    Retention is controlled by queue size and refresh/upsert behavior.
    """

    key: str
    location_id: str
    speakers: List[str]
    people_present: List[str]
    payload: Dict[str, Any]


def prune_expired(
    entries: List[TransientKnowledge],
    *,
    current_turn: int | None = None,
    current_minute: int | None = None,
) -> List[TransientKnowledge]:
    kept: List[TransientKnowledge] = []
    for e in entries:
        if not e.decay_one_turn():
            kept.append(e)
    return kept


def upsert_scene_knowledge_fifo(
    entries: List[SceneKnowledge],
    *,
    item: SceneKnowledge,
    max_items: int,
) -> List[SceneKnowledge]:
    """Upsert by key, then enforce FIFO max length.

    - If the key already exists, the old entry is removed and replaced at tail
      (refresh semantics).
    - If queue exceeds max_items, oldest entries are dropped from the head.
    """
    refreshed = [e for e in entries if str(getattr(e, "key", "")) != item.key]
    refreshed.append(item)
    if max_items <= 0:
        return []
    if len(refreshed) > max_items:
        return refreshed[-max_items:]
    return refreshed


def latest_scene_knowledge(entries: List[SceneKnowledge]) -> SceneKnowledge | None:
    if not entries:
        return None
    return entries[-1]
