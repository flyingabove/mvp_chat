"""Small, deterministic NPC initiative library for social stories."""
from __future__ import annotations

from typing import Mapping, Optional, Protocol

from backend.app.engine.world_model.agreements import Agreement, propose
from backend.app.engine.world_model.model import WorldModel


class Relationships(Protocol):
    def feelings(self, a: str, b: str) -> dict[str, float]: ...


def propose_rival_invitations(model: WorldModel, context: Optional[Mapping], relationships: Relationships,
                              minute: int) -> Optional[Agreement]:
    """Let one interested rival invite one partner, at most once each day.

    The partner's decision is deliberately left pending. The invitation can
    only occur in an awake, shared scene the player can actually witness.
    """
    if not context or not context.get("enabled") or context.get("player_gender") not in {"M", "F"}:
        return None
    genders = context.get("genders") or {}
    player_gender = context["player_gender"]
    present = set(model.present_with_player())
    today = model.world.day_index(minute)
    candidates: list[tuple[float, str, str]] = []
    for rival in sorted(present):
        if genders.get(rival) != player_gender or model.initiative_last_day.get(rival) == today:
            continue
        for partner in sorted(present - {rival}):
            if genders.get(partner) not in {"M", "F"} or genders[partner] == player_gender:
                continue
            player_affection = relationships.feelings("player", partner).get("affection", 0.0)
            rival_affection = relationships.feelings(rival, partner).get("affection", 0.0)
            partner_feelings = relationships.feelings(partner, rival)
            if (player_affection < 0.25 or rival_affection < 0.1
                    or partner_feelings.get("fear", 0) >= 0.4
                    or partner_feelings.get("trust", 0) <= -0.4):
                continue
            candidates.append((rival_affection + partner_feelings.get("affection", 0.0), rival, partner))
    if not candidates:
        return None
    _, rival, partner = sorted(candidates, key=lambda row: (-row[0], row[1], row[2]))[0]
    return _invite(model, rival, partner, minute, today)


def propose_agenda_invitations(model: WorldModel, minute: int) -> Optional[Agreement]:
    """A present character acting on their own compete_for/pursue intention invites its present target.

    One invitation per character per day, in a scene the player witnesses; the
    target's answer stays pending (only they can decide).
    """
    from backend.app.engine.world_model.agenda import intentions
    present = set(model.present_with_player())
    today = model.world.day_index(minute)
    candidates = []
    for rival in sorted(present):
        if model.initiative_last_day.get(rival) == today:
            continue
        for intention in intentions(model, rival, today):
            if intention.kind in ("compete_for", "pursue") and intention.target in present - {rival}:
                candidates.append((intention.priority + (0.5 if intention.kind == "compete_for" else 0), rival,
                                   intention.target))
    if not candidates:
        return None
    _, rival, partner = sorted(candidates, key=lambda row: (-row[0], row[1], row[2]))[0]
    return _invite(model, rival, partner, minute, today)


def _invite(model: WorldModel, rival: str, partner: str, minute: int, today: int) -> Agreement:
    place = model.player_place()
    event = model.world.add_event(minute, place, (rival, partner),
                                  f"@{rival} invited @{partner} to spend time together tomorrow evening",
                                  kind="scene", visibility="public")
    due = model.world.absolute_minute(today + 1, "19:00")
    invitation = propose(model.agreements, rival, partner, "spend time together", due, minute,
                         source_event_id=event.id)
    model.initiative_last_day[rival] = today
    for owner in (rival, partner):
        model.memories.add(owner, event.truth, "witnessed", minute, event_id=event.id)
    model.add_trace(minute, place,
                    f"@{rival} invited @{partner} to spend time together tomorrow evening. "
                    f"@{partner} has not answered yet.", involves=(rival, partner))
    return invitation
