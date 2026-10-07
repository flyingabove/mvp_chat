"""What each character wants to do next, from their own view, and NPC couples.

Intentions come from a character's OWN standings and reactions (never from
anyone else's hidden feelings): pursue someone they are drawn to, compete
for someone a rival also wants, test a partner's loyalty after seeing them
flirt elsewhere. Off-screen encounters consult both people's agendas; NPC
couples form and leave only when both independently qualify.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from backend.app.engine.world_model.intent import Intention
from backend.app.engine.world_model.model import PLAYER, WorldModel

MAX_INTENTIONS = 4
INTENTION_DAYS = 3
AIM_DAYS = 9999          # a rival's own aim lasts until they couple or the target does (BL-34)
OFFSCREEN_GAIN = {"affection": 1.0, "activity": 0.5, "chat": 0.3, "conflict": -1.0}


@dataclass(frozen=True)
class SocialContext:
    """What off-screen life needs to judge pairs by the story's own rules."""
    rules: Any
    genders: dict[str, str]

    def eligible(self, a: str, b: str) -> bool:
        policy = self.rules.appraisal
        return policy is not None and policy.covers(self.genders.get(a, ""), self.genders.get(b, ""))


def add_intention(model: WorldModel, owner: str, intention: Intention) -> None:
    current = [i for i in model.agendas.get(owner, [])
               if not (i.kind == intention.kind and i.target == intention.target)]
    current.append(intention)
    model.agendas[owner] = sorted(current, key=lambda i: (-i.priority, i.kind, i.target))[:MAX_INTENTIONS]


def intentions(model: WorldModel, owner: str, day: int) -> list[Intention]:
    return [i for i in model.agendas.get(owner, []) if i.expires_day >= day]


def refresh_agendas(model: WorldModel, track: str, day: int, scale: Optional[Callable[[str], float]] = None,
                    intensity: Any = None) -> None:
    """Derive pursue/compete_for from each holder's own `crush` stances (P-08), which already encode the holder's
    own standing, the story's eligibility and the track tier. Refresh the stances first.

    `scale(owner)` multiplies the priority of that owner's aims (their goals, P-07); None means 1.0 for everyone.
    `intensity` (the story's `Intensity`) scales pursuit by `romance` and competition by `rivalry`; None means full."""
    scale = scale or (lambda owner: 1.0)
    romance, rivalry = getattr(intensity, "romance", 1.0), getattr(intensity, "rivalry", 1.0)
    partner = {}
    for key in model.npc_couples:
        if key not in model.departed_couples:
            a, b = key.split("|")
            partner[a], partner[b] = b, a
    # Someone in a couple pursues only their partner.
    model.agendas = {cid: [i for i in items if i.expires_day >= day
                           and (cid not in partner or i.kind not in ("pursue", "compete_for") or i.target == partner[cid])]
                     for cid, items in model.agendas.items()}
    drawn: dict[str, list[tuple[float, str]]] = {}
    for owner in sorted(model.characters):
        for crush in model.stances.of(owner, "crush"):
            target = crush.target
            if owner in partner and target != partner[owner]:
                continue
            standing = model.standing.get(owner, target, track)
            value = standing.value if standing is not None else 0.0
            drawn.setdefault(target, []).append((value, owner))
            add_intention(model, owner, Intention("pursue", target, value / 100 * scale(owner) * romance,
                                                  "drawn to them", day + INTENTION_DAYS))
    # Someone holding a live aim on a person (a rival's own aim, BL-34) is drawn to them as well.
    for owner, items in sorted(model.agendas.items()):
        for aim in items:
            if aim.kind == "pursue" and aim.target != PLAYER and aim.expires_day >= day \
                    and owner in model.characters and not any(o == owner for _, o in drawn.get(aim.target, [])):
                drawn.setdefault(aim.target, []).append((aim.priority * 100, owner))
    # The player counts as an admirer of anyone who has warmed to them and is free: a rival then competes.
    courted = set()
    for owner in sorted(model.characters):
        standing = model.standing.get(owner, PLAYER, track)
        if (owner not in partner and standing is not None and not standing.closed_by
                and model.stances.has(owner, "crush", PLAYER)):
            courted.add(owner)
    for target, admirers in drawn.items():
        if rivalry <= 0 or len(admirers) + (1 if target in courted else 0) < 2:
            continue
        for value, owner in admirers:
            add_intention(model, owner, Intention("compete_for", target, (value / 100 * scale(owner) + 0.1) * rivalry,
                                                  "someone else wants them too", day + INTENTION_DAYS))


def agenda_weight(model: WorldModel, a: str, b: str, day: int) -> float:
    """Multiplier for closeness/plan outcomes when either person is pursuing the other."""
    wants = [i.priority for owner, other in ((a, b), (b, a)) for i in intentions(model, owner, day)
             if i.target == other and i.kind in ("pursue", "compete_for")]
    return 1.0 + max(wants, default=0.0)


def mutual_pursuit(model: WorldModel, a: str, b: str, day: int) -> bool:
    def wants(x: str, y: str) -> bool:
        return any(i.target == y and i.kind in ("pursue", "compete_for") for i in intentions(model, x, day))
    return wants(a, b) and wants(b, a)


def couples_ready(model: WorldModel, track: str, dating_tier: str, eligible: Any, day: int) -> list[tuple[str, str]]:
    """NPC pairs where BOTH independently reached the dating tier toward each other and pursue each other."""
    pairs = []
    ids = sorted(c for c in model.characters if model.is_placed(c))
    taken = {cid for key in model.npc_couples for cid in key.split("|")}   # current or departed couples
    for index, a in enumerate(ids):
        for b in ids[index + 1:]:
            if a in taken or b in taken or not eligible(a, b):
                continue
            both = all(model.standing.tier_reached(x, y, track, dating_tier) is True for x, y in ((a, b), (b, a)))
            if both and mutual_pursuit(model, a, b, day):
                pairs.append((a, b))
                taken |= {a, b}
    return pairs


def couples_leaving(model: WorldModel, track: str, committed_tier: str, days_together: int,
                    day: int) -> list[tuple[str, str]]:
    leaving = []
    for key, formed_day in sorted(model.npc_couples.items()):
        a, b = key.split("|")
        if key in model.departed_couples or day - formed_day < days_together:
            continue
        if not (model.is_placed(a) and model.is_placed(b)):
            continue
        if all(model.standing.tier_reached(x, y, track, committed_tier) is True for x, y in ((a, b), (b, a))):
            leaving.append((a, b))
    return leaving


def next_beat(model: WorldModel, present: set[str], day: int) -> Optional[tuple[str, Intention]]:
    """At most one unsolicited beat: the present character with an intention toward the player, or a rival
    competing for someone who is in the scene, who has waited longest for initiative (ties by priority, then id)."""
    options = []
    for cid in sorted(present):
        for intention in intentions(model, cid, day):
            visible = (intention.target == PLAYER and intention.kind in ("test_loyalty", "pursue")) or (
                intention.kind == "compete_for" and intention.target in present - {cid}
                and model.initiative_last_day.get(f"beat:{cid}") != day)   # BL-34: a visible rival, once a day
            if visible:
                options.append((model.initiative_last_day.get(f"beat:{cid}", -1), -intention.priority, cid,
                                intention))
    if not options:
        return None
    _, _, cid, intention = min(options, key=lambda option: option[:3])
    return cid, intention
