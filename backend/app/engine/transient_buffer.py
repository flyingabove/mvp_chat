from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TransientEntry:
    id: str
    namespace: str
    scope: str  # scene | location | conversation
    text: str
    created_turn: int
    created_minute: int
    location_id: str = ""
    expires_after_turns: Optional[int] = 2
    expires_after_minutes: Optional[int] = None
    promotable: bool = False
    promoted: bool = False
    meta: Dict[str, str] = field(default_factory=dict)

    def is_expired(self, *, current_turn: int, current_minute: int) -> bool:
        if self.promoted:
            return True
        if self.expires_after_turns is not None and current_turn - self.created_turn >= self.expires_after_turns:
            return True
        if self.expires_after_minutes is not None and current_minute - self.created_minute >= self.expires_after_minutes:
            return True
        return False


def prune_expired(entries: List[TransientEntry], *, current_turn: int, current_minute: int) -> List[TransientEntry]:
    return [e for e in entries if not e.is_expired(current_turn=current_turn, current_minute=current_minute)]
