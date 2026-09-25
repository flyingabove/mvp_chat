"""People reach out when apart: a due promise, or (rarely) warmth. Messages are
delivered on the player's next turn, because time only moves on turns, and they
surface only in prose (no inbox UI)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from backend.app.engine.world_model.commitments import due_commitments
from backend.app.engine.world_model.model import PLAYER, ContactMessage
from backend.app.engine.world_model.memory import render

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

WARM_CONTACT_THRESHOLD = 0.6
WARM_CONTACT_CHANCE = 0.25


def queue_contacts(model: "WorldModel", start: int, end: int,
                   warmth: Callable[[str], float] = lambda cid: 0.0) -> list[ContactMessage]:
    """Queue at most one message per sender per interval, for senders apart from the player and awake."""
    if end <= start:
        return []
    player_place = model.player_place()
    day = model.world.day_index(end)
    pending = {c.sender for c in model.contacts if not c.delivered}
    queued = []
    for cid, character in sorted(model.characters.items()):
        if cid in pending or not character.can_hear:
            continue
        place = model.world.place_of(cid)
        if not place or place == player_place:
            continue
        intent = ""
        for promise in due_commitments(model, end, owner=cid):
            if promise.counterpart == PLAYER:
                intent = f"about their promise: {render(promise.text, model.names())}"
                break
        if not intent and character.last_contact_day != day and warmth(cid) >= WARM_CONTACT_THRESHOLD \
                and model.rng(f"contact:{cid}", end).random() < WARM_CONTACT_CHANCE:
            intent = "just checking in"
        if not intent:
            continue
        message = ContactMessage(sender=cid, minute=end, intent=intent)
        model.contacts.append(message)
        model.memories.add(cid, f"I texted @{PLAYER} {intent}", "witnessed", end, kind="contact")
        character.last_contact_day = day
        queued.append(message)
    return queued


def deliver(model: "WorldModel") -> list[ContactMessage]:
    """Hand pending messages to this turn; an asleep player receives them on waking."""
    if model.player_availability == "asleep":
        return []
    ready = [c for c in model.contacts if not c.delivered]
    for message in ready:
        message.delivered = True
    model.contacts = model.contacts[-20:]
    return ready
