"""Who walks with the player when the player moves.

Live beta bug (2026-09-29): "Riko, come with me to the Neighborhood Cafe" moved only the
player, so the date happened in an empty room. A resident comes along only when the
player explicitly invites them to travel together (named, or the only one present) and
they are awake and not cold toward the player. Nobody is dragged along by proximity.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, Iterable

from backend.app.engine.world_model.speakers import addressed_ids

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

# "come with me", "walk you there", "let's go/head/walk to", "I'll take you", "together".
INVITE = re.compile(
    r"\b(?:come|walk|go|head|join)(?:ing)?\s+(?:along\s+)?with\s+me\b"
    r"|\bcome\s+along\b"
    r"|\b(?:walk|escort|accompany|bring|take)\s+(?:you|her|him|them)\b"
    r"|\blet'?s\s+(?:go|head|walk|leave)\b"
    r"|\bshall\s+we\s+(?:go|head|walk)\b"
    r"|\bjust\s+the\s+two\s+of\s+us\b"
    r"|\b(?:go|head|walk)\w*\s+\w+(?:\s+\w+)?\s+together\b", re.I)
# A future or conditional invitation ("if she wants to come with me later") is not a move.
HYPOTHETICAL = re.compile(r"\b(?:if|whether|when|later|tomorrow|tonight|maybe|ask(?:ed|ing)?)\b", re.I)
MIN_WARMTH = 0.0


def choose_companions(model: "WorldModel", message: str, present: Iterable[str],
                      warmth: Callable[[str], float] = lambda cid: 0.0) -> list[str]:
    """Ids of the present residents who travel with the player on this move."""
    if not INVITE.search(message or ""):
        return []
    awake = [cid for cid in present if cid in model.characters and model.characters[cid].availability != "asleep"]
    invite_text = " ".join(part for part in re.split(r"(?<=[.!?])\s+", message) if INVITE.search(part))
    if HYPOTHETICAL.search(invite_text):
        return []
    _, named = addressed_ids(model, message, awake)
    _, named_anyone = addressed_ids(model, message, model.characters)
    # An unnamed "come with me" means the one person here; naming someone else means not them.
    invited = named or (set(awake) if len(awake) == 1 and not named_anyone else set())
    return sorted(cid for cid in invited if warmth(cid) >= MIN_WARMTH)
