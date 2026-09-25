"""A fact spreads only when one person actually tells another: a `told_by`
memory pointing at the same event, with lower confidence. Private memories
(secrets, private concerns) are never passed on."""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING, Optional

from backend.app.engine.world_model.memory import Memory

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

SHAREABLE_KINDS = ("fact", "dialogue")
CONFIDENCE_DECAY = 0.8


def to_third_person(text: str, teller: str) -> str:
    """'I argued with @b' told by a -> '@a argued with @b'."""
    text = re.sub(r"\bI'm\b", f"@{teller} is", text)
    text = re.sub(r"\bI\b", f"@{teller}", text)
    text = re.sub(r"\bmy\b", f"@{teller}'s", text, flags=re.I)
    return re.sub(r"\bme\b", f"@{teller}", text, flags=re.I)


def shareable(model: "WorldModel", teller: str, listener: str) -> list[Memory]:
    return [m for m in model.memories.of(teller)
            if not m.private and m.kind in SHAREABLE_KINDS and listener not in m.mentions()
            and not model.memories.knows_event(listener, m.event_id)
            and not model.memories.has_text(listener, m.text)]


def share_memory(model: "WorldModel", teller: str, listener: str, minute: int,
                 rng: random.Random) -> Optional[Memory]:
    candidates = shareable(model, teller, listener)
    if not candidates:
        return None
    newest = max(m.minute for m in candidates)
    recent = sorted((m for m in candidates if m.minute == newest), key=lambda m: m.id)
    original = rng.choice(recent)
    return model.memories.add(listener, to_third_person(original.text, teller), f"told_by:{teller}", minute,
                              confidence=original.confidence * CONFIDENCE_DECAY, kind="fact",
                              event_id=original.event_id, refs=original.refs)
