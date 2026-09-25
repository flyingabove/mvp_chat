"""Turn orchestration: the only module the API layer calls.

begin_turn(state, msg, minute_before)  — after the clock/travel for this turn is
    settled and before the prompt is built: step the world through the elapsed
    interval (routines -> threads -> off-screen -> contact), mirror locations
    into state.character_locations, record what present people heard, resolve
    inspections and due promises, plan speakers, and build the TurnView.
end_turn(state, msg, segments)        — after the reply: memories of what was
    said, promises detected, speaker recency and ending kind.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Optional

from backend.app.engine.world_model import bootstrap
from backend.app.engine.world_model.commitments import (detect_promises, due_commitments, expire_commitments,
                                                         resolve_commitment)
from backend.app.engine.world_model.contact import deliver, queue_contacts
from backend.app.engine.world_model.evidence import find_inspect_target, inspect
from backend.app.engine.world_model.memory import render
from backend.app.engine.world_model.model import PLAYER, TurnView, WorldModel
from backend.app.engine.world_model.offscreen import resolve_offscreen
from backend.app.engine.world_model.projection import classify_ending, ending_hint
from backend.app.engine.world_model.speakers import addressed_ids, select_speakers
from backend.app.engine.world_model.stepper import step_world
from backend.app.engine.world_model.threads import advance_threads

# First-person or imperative intent only: "Did you go to bed late?" must not put the player to sleep.
SLEEP = re.compile(
    r"(?:^|[.!?]\s+|\bI(?:'m| am|'ll| will)?\s+(?:(?:going|gonna|about)\s+(?:to\s+)?)?|\blet me\s+|\btime to\s+)"
    r"(?:go|head|turn in|get)\s+(?:off\s+)?(?:to\s+)?(?:sleep|bed)\b"
    r"|\bI(?:'m| am)?\s+(?:falling asleep|fall asleep|off to bed|calling it a night|call it a night)\b",
    re.I)
WAKE_TIME = "07:00"
DIALOGUE_MEMORY_CAP = 80
MAX_PERSPECTIVE = 3


class GraphRelationships:
    """Adapter from the existing CharacterGraph to the off-screen resolver."""

    def __init__(self, graph: Any) -> None:
        self.graph = graph

    def feelings(self, a: str, b: str) -> dict[str, float]:
        edge = self.graph.get_edge(a, b) if self.graph is not None else None
        if edge is None:
            return {}
        s = edge.state
        return {"trust": s.trust, "affection": s.affection, "suspicion": s.suspicion, "fear": s.fear}

    def adjust(self, a: str, b: str, narrative: str = "", **deltas: float) -> None:
        if self.graph is not None:
            self.graph.update_edge(a, b, narrative=narrative, **deltas)


def warmth_fn(state: Any) -> Callable[[str], float]:
    relationships = GraphRelationships(getattr(state, "character_graph", None))

    def warmth(cid: str) -> float:
        f = relationships.feelings(cid, PLAYER)
        return (f.get("trust", 0.0) + f.get("affection", 0.0)) / 2 if f else 0.0
    return warmth


def enabled(state: Any) -> bool:
    from backend.app.config import settings
    return bool(getattr(settings, "WORLD_MODEL_ENABLED", True)) and bootstrap.enabled_for(state)


def ensure_model(state: Any, lore: Optional[Iterable[dict]] = None) -> Optional[WorldModel]:
    if not enabled(state):
        return None
    if getattr(state, "world_model", None) is None:
        state.world_model = bootstrap.build_world_model(state, lore=lore)
    return state.world_model


def sync_membership(model: WorldModel, state: Any) -> None:
    """Arrivals join (at their tracked location), departures leave the world."""
    eligible = set(bootstrap.eligible_ids(state))
    locations = getattr(state, "character_locations", {}) or {}
    for cid in sorted(eligible - set(model.characters)):
        model.characters[cid] = bootstrap.make_character(state, cid)
        if locations.get(cid):
            model.world.move(cid, locations[cid])
        bootstrap.settle_into_current_block(model, cid)
    for cid in sorted(set(model.characters) - eligible):
        model.characters.pop(cid)
        model.world.remove(cid)


def mirror_locations(model: WorldModel, state: Any) -> None:
    """state.character_locations becomes a projection of the world index."""
    locations = dict(getattr(state, "character_locations", {}) or {})
    for cid in model.characters:
        place = model.world.place_of(cid)
        if place:
            locations[cid] = place
    state.character_locations = locations


def sleep_minutes(state: Any, message: str) -> int:
    """Minutes until the next wake time when the player says they go to sleep (0 otherwise)."""
    model = getattr(state, "world_model", None)
    if model is None or not SLEEP.search(message or ""):
        return 0
    now = int(getattr(state, "minute", 0) or 0)
    return model.world.next_minute_at(WAKE_TIME, now) - now


def _place_name(place_names: dict[str, str], place: str) -> str:
    return place_names.get(place) or place.replace("_", " ")


def begin_turn(state: Any, message: str, minute_before: int, place_names: Optional[dict[str, str]] = None,
               sleeping: bool = False, scorer: Optional[Callable] = None) -> Optional[TurnView]:
    model = ensure_model(state)
    if model is None:
        return None
    place_names = place_names or {}
    model.turn += 1
    model.player_name = str(getattr(state, "player_name", "") or model.player_name)
    sync_membership(model, state)
    previous_place = model.player_place()
    protected = set(model.present_with_player())
    if getattr(state, "location_id", "") and state.location_id != previous_place:
        model.world.move(PLAYER, state.location_id)
    now = int(getattr(state, "minute", 0) or 0)
    step = None
    if now > minute_before:
        model.player_availability = "asleep" if sleeping else "awake"
        step = step_world(model, minute_before, now, protected, player_asleep=sleeping)
        advance_threads(model, minute_before, now)
        resolve_offscreen(model, step, GraphRelationships(getattr(state, "character_graph", None)), scorer)
        expire_commitments(model, now)
        queue_contacts(model, minute_before, now, warmth_fn(state))
        model.player_availability = "awake"
    model.world.minute = now
    mirror_locations(model, state)
    view = _build_view(model, state, message, step, place_names)
    model.view = view
    return view


def _build_view(model: WorldModel, state: Any, message: str, step: Any, place_names: dict[str, str]) -> TurnView:
    names = model.names()
    view = TurnView(names=names)
    here = model.player_place()
    present = model.present_with_player()
    asleep_here = [c for c in model.present_with_player(include_asleep=True) if c not in present]
    view.present = present
    view.time_text = model.world.datetime_at().strftime("%A %H:%M")
    for cid in present:
        c = model.characters[cid]
        activity = c.activity or "here"
        view.cards.append(f"{c.name} ({c.descriptor}): {activity}; {c.availability}"
                          + (f"; mood: {c.mood}" if c.mood else ""))
    for cid in asleep_here:
        view.cards.append(f"{names[cid]} is asleep here and cannot talk unless woken")
    lifecycle = getattr(state, "cast_lifecycle", None)
    if not (lifecycle is not None and getattr(lifecycle, "enabled", False)):
        for cid in sorted(model.characters):
            place = model.world.place_of(cid)
            if place and cid not in present and cid not in asleep_here:
                c = model.characters[cid]
                view.elsewhere.append(f"{c.name}: {_place_name(place_names, place)}"
                                      + (" (asleep)" if c.availability == "asleep" else ""))
    if step is not None:
        for t in step.transitions:
            if t.destination == here and t.origin != here:
                view.transitions.append(f"{names[t.character]} came in" + (f" ({t.activity})" if t.activity else ""))
            elif t.origin == here and t.destination != here:
                view.transitions.append(f"{names[t.character]} left for {_place_name(place_names, t.destination or '')}")
    present_set = set(present)
    for trace in model.traces:
        if trace.visible(model.world.minute, here, present_set):
            view.traces.append(render(trace.text, names))
            trace.shown = True
    for contact in deliver(model):
        kind = "called" if contact.kind == "call" else "texted"
        view.must_address.append(f"While apart, {names.get(contact.sender, contact.sender)} {kind} the player "
                                 f"({contact.intent}). Mention the phone buzzing naturally; the player has not replied yet.")
    target = find_inspect_target(model, message)
    if target is not None:
        result = inspect(model, target, message, witnesses=tuple(present))
        if result.noticed:
            view.must_address.append(f"The player inspects {target.name}: they notice {'; '.join(result.noticed)}. "
                                     "Describe exactly this; invent no other clue.")
        else:
            view.must_address.append(f"The player inspects {target.name} and notices nothing unusual"
                                     + (" at a glance" if result.missed else "") + ". Invent no clue.")
    now = model.world.minute
    for promise in due_commitments(model, now):
        if promise.owner in present_set and promise.counterpart == PLAYER:
            view.must_address.append(f"{names[promise.owner]} promised earlier: {render(promise.text, names)}. "
                                     f"It is due now; {names[promise.owner]} acts on it or brings it up.")
            resolve_commitment(promise, kept=True)
        elif promise.owner == PLAYER and promise.counterpart in present_set:
            view.must_address.append(f"The player promised {names[promise.counterpart]}: {render(promise.text, names)}. "
                                     f"{names[promise.counterpart]} may remind them.")
    if message.strip():
        for cid in present:
            model.memories.add(cid, f"@{PLAYER} said: {message.strip()[:300]}", f"told_by:{PLAYER}", now,
                               kind="dialogue")
    candidates = present or [cid for cid in model.characters if not model.is_placed(cid)]
    view.plan = select_speakers(model, candidates, message, warmth_fn(state))
    _, mentioned = addressed_ids(model, message, list(model.characters))
    for cid in view.plan.speakers:
        found = [m for m in model.memories.search(cid, message, mentions=mentioned, k=MAX_PERSPECTIVE + 1)
                 if not (m.minute == now and m.source == f"told_by:{PLAYER}")][:MAX_PERSPECTIVE]
        rendered = [render(m.text, names) + (f" (heard from {names.get(m.source[8:], 'someone')})"
                                             if m.source.startswith("told_by:") else "") for m in found]
        if rendered:
            view.perspectives[cid] = rendered
    unplaced = [cid for cid in model.characters if not model.is_placed(cid)]
    # Someone on a phone call with the player can speak without being present.
    from backend.app.engine.active_characters import get_on_call_character_keys
    on_call = {k for k in get_on_call_character_keys(state) if k in model.characters}
    view.allowed_speakers = sorted(set(present) | set(unplaced) | set(view.plan.speakers) | on_call)
    view.ending_hint = ending_hint(model.endings)
    return view


def end_turn(state: Any, message: str, segments: list[dict]) -> None:
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state):
        return
    now = model.world.minute
    present = set(model.present_with_player())
    listener = model.view.plan.primary or PLAYER
    for seg in segments or []:
        speaker = seg.get("speaker_id")
        if seg.get("kind") != "dialogue" or speaker not in model.characters:
            continue
        text = str(seg.get("text") or "").strip()
        model.characters[speaker].record_spoke(model.turn)
        if speaker not in model.known_names:
            model.known_names.append(speaker)
        for cid in present | {speaker}:
            model.memories.add(cid, f"@{speaker} said: {text[:240]}", "witnessed", now, kind="dialogue")
        detect_promises(model, speaker, PLAYER, text, now)
    detect_promises(model, PLAYER, listener, message, now)
    last = next((s for s in reversed(segments or []) if str(s.get("text") or "").strip()), None)
    if last is not None:
        model.endings = (model.endings + [classify_ending(str(last.get("text")))])[-6:]
    _prune(model)


def _prune(model: WorldModel) -> None:
    by_owner: dict[str, int] = {}
    kept = []
    for memory in reversed(model.memories.memories):
        if memory.kind == "dialogue":
            by_owner[memory.owner] = by_owner.get(memory.owner, 0) + 1
            if by_owner[memory.owner] > DIALOGUE_MEMORY_CAP:
                continue
        kept.append(memory)
    model.memories.memories = list(reversed(kept))
