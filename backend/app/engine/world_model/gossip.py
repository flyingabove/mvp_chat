"""A fact spreads only when one person actually tells another: a `told_by`
memory pointing at the same event, with lower confidence. Private memories
(secrets, private concerns) are never passed on."""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING, Optional

from backend.app.engine.world_model.memory import Memory
from backend.app.engine.world_model.epistemics import assert_claim, transmit

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

SHAREABLE_KINDS = ("fact", "dialogue", "claim")
CONFIDENCE_DECAY = 0.8


def to_third_person(text: str, teller: str) -> str:
    """'I argued with @b' told by a -> '@a argued with @b'."""
    text = re.sub(r"\bI'm\b", f"@{teller} is", text)
    text = re.sub(r"\bI\b", f"@{teller}", text)
    text = re.sub(r"\bmy\b", f"@{teller}'s", text, flags=re.I)
    return re.sub(r"\bme\b", f"@{teller}", text, flags=re.I)


def shareable(model: "WorldModel", teller: str, listener: str) -> list[Memory]:
    heard_roots = {m.root_source_id or m.id for m in model.memories.of(listener)}
    return [m for m in model.memories.of(teller)
            if not m.private and m.kind in SHAREABLE_KINDS and listener not in m.mentions()
            and (m.root_source_id or m.id) not in heard_roots]


def share_memory(model: "WorldModel", teller: str, listener: str, minute: int,
                 rng: random.Random) -> Optional[Memory]:
    candidates = shareable(model, teller, listener)
    if not candidates:
        return None
    newest = max(m.minute for m in candidates)
    recent = sorted((m for m in candidates if m.minute == newest), key=lambda m: m.id)
    original = rng.choice(recent)
    if original.assertion_id:
        assertion_id, parent_id = original.assertion_id, original.transmission_id
    else:
        assertion_id = assert_claim(model.epistemics, teller, original.text, minute).id
        parent_id = ""
    delivery = transmit(model.epistemics, assertion_id, teller, listener, minute, parent_id=parent_id)
    # Transmission changes the listener's source, not the underlying root.
    # Repetition of a rumor must not mint a new independent witness or keep
    # multiplying a fictional probability by 0.8 on every hop.
    confidence = original.confidence if original.root_source_id else original.confidence * CONFIDENCE_DECAY
    return model.memories.add(listener, to_third_person(original.text, teller), f"told_by:{teller}", minute,
                              confidence=confidence, kind="claim", event_id=original.event_id,
                              refs=original.refs, root_source_id=original.root_source_id or original.id,
                              parent_memory_id=original.id, assertion_id=assertion_id,
                              transmission_id=delivery.id)
