"""What happens between people while the player is not watching.

Runs over the stepped timeline of an interval: pairs who shared a place, both
awake, away from the player, for at least ENCOUNTER_MIN minutes may do nothing,
talk, share an activity, argue, grow closer, make a plan or pass on gossip.
Weights come from their relationship edges; an optional `scorer` (e.g. Jev) may
reweight; a seeded draw decides. Results are committed as private events,
memories for the two participants only, edge deltas and visible traces.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, Protocol, Mapping

from backend.app.engine.world_model.agreements import propose, decide
from backend.app.engine.world_model.gossip import share_memory, shareable
from backend.app.engine.world_model.drama import register_conflict
from backend.app.engine.world_model.memory import render
from backend.app.engine.world_model.stepper import StepResult

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

ENCOUNTER_MIN = 30
MAX_ENCOUNTERS = 6
OUTCOMES = ("nothing", "chat", "activity", "conflict", "affection", "plan", "gossip")
BASE_WEIGHTS = {"nothing": 3.0, "chat": 4.0, "activity": 2.0, "conflict": 1.0,
                "affection": 1.0, "plan": 1.0, "gossip": 2.0}
ACTIVITIES = ("shared a meal", "watched something together", "went for a walk", "worked side by side",
              "cleaned up the kitchen together")


class Relationships(Protocol):
    def feelings(self, a: str, b: str) -> dict[str, float]: ...
    def adjust(self, a: str, b: str, narrative: str = "", **deltas: float) -> None: ...


@dataclass
class Encounter:
    a: str
    b: str
    place: str
    minute: int
    duration: int


@dataclass
class Outcome:
    encounter: Encounter
    kind: str
    event_id: str = ""


def find_encounters(result: StepResult) -> list[Encounter]:
    """Pairs co-located and awake, not in the player's view, for >= ENCOUNTER_MIN minutes."""
    totals: dict[tuple[str, str, str], list[int]] = {}
    previous: Optional[set[tuple[str, str, str]]] = None
    previous_minute = None
    for minute, snapshot, player_place, player_awake in result.timeline:
        by_place: dict[str, list[str]] = {}
        for cid, (place, availability) in snapshot.items():
            if place and availability in ("awake", "busy") and not (player_awake and place == player_place):
                by_place.setdefault(place, []).append(cid)
        current = {(a, b, place) for place, people in by_place.items()
                   for i, a in enumerate(sorted(people)) for b in sorted(people)[i + 1:]}
        if previous is not None:
            for key in current & previous:
                totals.setdefault(key, [minute, 0])[1] += minute - previous_minute
        previous, previous_minute = current, minute
    encounters = [Encounter(a, b, place, first, duration)
                  for (a, b, place), (first, duration) in totals.items() if duration >= ENCOUNTER_MIN]
    encounters.sort(key=lambda e: (-e.duration, e.a, e.b))
    return encounters[:MAX_ENCOUNTERS]


def outcome_weights(model: "WorldModel", enc: Encounter, relationships: Relationships,
                    scorer: Optional[Callable[[Encounter, dict[str, float]], dict[str, float]]] = None,
                    rivalry: Optional[Mapping] = None) -> dict[str, float]:
    ab, ba = relationships.feelings(enc.a, enc.b), relationships.feelings(enc.b, enc.a)
    warmth = (ab.get("trust", 0) + ab.get("affection", 0) + ba.get("trust", 0) + ba.get("affection", 0)) / 2
    affection = (ab.get("affection", 0) + ba.get("affection", 0)) / 2
    suspicion = (ab.get("suspicion", 0) + ba.get("suspicion", 0)) / 2
    weights = dict(BASE_WEIGHTS)
    weights["chat"] *= 1 + max(0.0, warmth)
    weights["affection"] *= 1 + 2 * max(0.0, affection)
    weights["conflict"] *= 1 + 2 * suspicion + 2 * max(0.0, -warmth)
    weights["nothing"] *= 1 + max(0.0, -warmth)
    if not (shareable(model, enc.a, enc.b) or shareable(model, enc.b, enc.a)):
        weights["gossip"] = 0.0
    # A story-authored competition only changes the odds of a feasible
    # off-screen encounter. It cannot assign the partner's feelings, create
    # an encounter, or make every same-gender resident a rival by default.
    if rivalry and rivalry.get("enabled") and rivalry.get("player_gender") in ("M", "F"):
        player_gender = rivalry["player_gender"]
        genders = rivalry.get("genders") or {}
        for rival_id, partner_id in ((enc.a, enc.b), (enc.b, enc.a)):
            if genders.get(rival_id) != player_gender or genders.get(partner_id) == player_gender:
                continue
            if genders.get(partner_id) not in ("M", "F"):
                continue
            player_interest = relationships.feelings("player", partner_id).get("affection", 0)
            rival_interest = relationships.feelings(rival_id, partner_id).get("affection", 0)
            if player_interest >= 0.25 and rival_interest >= 0.1:
                weights["plan"] *= 2.0
                weights["affection"] *= 1.5
                break
    if scorer is not None:
        for kind, factor in (scorer(enc, dict(weights)) or {}).items():
            if kind in weights:
                weights[kind] *= max(0.0, float(factor))
    return weights


def _commit(model: "WorldModel", enc: Encounter, kind: str, relationships: Relationships) -> str:
    a, b, minute, place = enc.a, enc.b, enc.minute, enc.place
    rng = model.rng(f"offscreen-detail:{a}:{b}", minute)
    if kind == "chat":
        truth, deltas, trace = f"@{a} and @{b} talked for a while", {"affection_delta": 0.05, "trust_delta": 0.03}, ""
    elif kind == "activity":
        truth = f"@{a} and @{b} {rng.choice(ACTIVITIES)}"
        deltas, trace = {"affection_delta": 0.05}, ""
    elif kind == "conflict":
        truth = f"@{a} and @{b} argued"
        deltas = {"trust_delta": -0.05, "affection_delta": -0.05, "suspicion_delta": 0.05}
        trace = f"@{a} and @{b} seem to be avoiding each other"
    elif kind == "affection":
        truth, deltas = f"@{a} and @{b} grew closer", {"affection_delta": 0.1, "trust_delta": 0.05}
        trace = f"@{a} and @{b} seem easier with each other"
    elif kind == "plan":
        truth, deltas, trace = f"@{a} and @{b} made plans to hang out", {"affection_delta": 0.03}, ""
    else:  # gossip
        truth, deltas, trace = f"@{a} and @{b} traded news", {"trust_delta": 0.02}, ""
    event = model.world.add_event(minute, place, (a, b), truth, kind="offscreen",
                                  visibility="public" if trace else "private")
    note = render(truth, model.names())
    for owner, other in ((a, b), (b, a)):
        model.memories.add(owner, truth, "witnessed", minute, event_id=event.id)
        relationships.adjust(owner, other, narrative=note, **deltas)
    if kind == "plan":
        agreement = propose(model.agreements, a, b, "hang out tomorrow evening",
                            model.world.absolute_minute(model.world.day_index(minute) + 1, "19:00"),
                            minute, source_event_id=event.id)
        decide(model.agreements, agreement.id, b, "accepted", minute)
    if kind == "conflict":
        register_conflict(model.drama, (a, b), event.id, minute, trace)
    if kind == "gossip":
        share_memory(model, a, b, minute, rng)
        share_memory(model, b, a, minute, rng)
    if trace:
        model.add_trace(minute, place, trace, involves=(a, b))
    return event.id


def resolve_offscreen(model: "WorldModel", result: StepResult, relationships: Relationships,
                      scorer: Optional[Callable] = None, rivalry: Optional[Mapping] = None) -> list[Outcome]:
    outcomes = []
    for enc in find_encounters(result):
        weights = outcome_weights(model, enc, relationships, scorer, rivalry)
        total = sum(weights.values())
        if total <= 0:
            continue
        roll = model.rng(f"offscreen:{enc.a}:{enc.b}", enc.minute).random() * total
        kind = OUTCOMES[-1]
        for candidate in OUTCOMES:
            roll -= weights[candidate]
            if roll < 0:
                kind = candidate
                break
        event_id = "" if kind == "nothing" else _commit(model, enc, kind, relationships)
        outcomes.append(Outcome(enc, kind, event_id))
    return outcomes
