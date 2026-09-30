"""In-chat choice cards (BL-46): an accepted "leave together" ask waits for the player's own say-so.

A yes from the partner never ends the game by itself. It records a persisted `pending_choice` that the chat
shows as a card ("Leave together now?" / "Keep talking"). The card is answered by a normal chat message
(`__choice__:<id>:<option>`), so humans, the player agent and the arena all use the same path, and it lives
in the saved world model so a reload or resume shows it again. The yes lapses at the end of that in-game day,
or as soon as the relationship ends or the partner is gone.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

LEAVE_TOGETHER = "leave_together"
LEAVE_NOW = "leave_now"
KEEP_TALKING = "keep_talking"
PLAN_SKIP = "plan_skip"          # an agreed future plan: skip ahead to it, or keep playing
SKIP_TO_PLAN = "skip_to_plan"
KEEP_PLAYING = "keep_playing"
MIN_SKIP_MINUTES = 181           # vague "later"/"soon" plans (about 3 hours) never offer a skip
CHOICE_PREFIX = "__choice__:"
# "[play ending]", "(play credits)": the text way to answer the card once the player chose to keep talking.
PLAY_ENDING = re.compile(r"^\s*[\[(]\s*play\s+(?:the\s+)?(?:ending|credits|finale)\s*[\])]\s*$", re.I)


def offer_leave_together(model: "WorldModel", partner: str) -> dict:
    name = model.names().get(partner, partner)
    model.pending_choice = {
        "id": LEAVE_TOGETHER, "kind": LEAVE_TOGETHER, "partner": partner, "chip": "Play ending",
        "day": model.world.day_index(model.world.minute),
        "prompt": f"{name} said yes. Leave the house together now? This ends your story with the judges' verdict.",
        "options": [{"id": LEAVE_NOW, "label": "Leave together now: play the judges' ending"},
                    {"id": KEEP_TALKING, "label": "Keep talking"}],
    }
    return model.pending_choice


def offer_plan_skip(model: "WorldModel", partner: str, what: str, due: int) -> Optional[dict]:
    """Offer to skip ahead to an agreed plan. One card at a time: an open offer is never replaced."""
    if model.pending_choice or model.romance_outcome:
        return None
    when = model.world.datetime_at(due).strftime("%A %H:%M")
    name = model.names().get(partner, partner)
    model.pending_choice = {
        "id": PLAN_SKIP, "kind": PLAN_SKIP, "partner": partner, "due": int(due), "what": what, "when": when,
        "day": model.world.day_index(model.world.minute), "chip": f"Skip to {when}",
        "prompt": (f"You and {name} agreed to {what} ({when}). Skip ahead to then, or keep playing? "
                   "Everything in between happens without you."),
        "options": [{"id": SKIP_TO_PLAN, "label": f"Skip to {when}"}, {"id": KEEP_PLAYING, "label": "Keep playing"}],
    }
    return model.pending_choice


def refresh(model: "WorldModel") -> Optional[str]:
    """Drop a stale offer. Returns a storyteller note when the yes has just lapsed, else None."""
    choice = model.pending_choice
    if not choice:
        return None
    if choice.get("kind") == PLAN_SKIP:            # the plan's time has passed: the card just goes away
        if model.world.minute > int(choice.get("due") or 0) or model.world.where_is(str(choice.get("partner"))) is None:
            model.pending_choice = {}
        return None
    partner = str(choice.get("partner") or "")
    today = model.world.day_index(model.world.minute)
    if (model.romance_outcome or model.romance_relationship_partner != partner
            or model.world.where_is(partner) is None or today > int(choice.get("day") or 0)):
        model.pending_choice = {}
        if model.romance_outcome:
            return None
        return (f"{model.names().get(partner, partner)}'s earlier yes to leaving together no longer stands "
                "(time has passed or things changed). Do not treat it as agreed.")
    return None


def answer(model: "WorldModel", message: str) -> Optional[str]:
    """The option the message picks from the open card (`leave_now`/`keep_talking`), or None."""
    choice = model.pending_choice
    if not choice:
        return None
    text = (message or "").strip().split("\n", 1)[0].strip()
    if text.startswith(CHOICE_PREFIX):
        _, _, rest = text[len(CHOICE_PREFIX):].partition(":")
        picked = next((o["id"] for o in choice.get("options") or [] if o["id"] == rest.strip()), None)
        return picked
    if choice.get("kind") == LEAVE_TOGETHER and PLAY_ENDING.match(text):
        return LEAVE_NOW
    return None


def payload(model: "WorldModel") -> Optional[dict]:
    """The card the player sees (no internal ids beyond the choice and option ids)."""
    return card_from_saved(model.pending_choice)


def card_from_saved(choice: Optional[dict]) -> Optional[dict]:
    """The player-facing card for a saved `pending_choice` dict (also used to resume a session)."""
    if not choice:
        return None
    return {"id": choice["id"], "kind": choice["kind"], "prompt": choice["prompt"],
            "chip": str(choice.get("chip") or ""), "options": [dict(o) for o in choice.get("options") or []]}


def partner_here(model: "WorldModel") -> bool:
    partner = str((model.pending_choice or {}).get("partner") or "")
    return bool(partner) and model.world.place_of(partner) == model.player_place() and model.player_place() != ""

