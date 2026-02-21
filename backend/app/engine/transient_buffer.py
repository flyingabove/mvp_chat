from __future__ import annotations

from dataclasses import dataclass
from typing import List

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
