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

from backend.app.engine.world_model import bootstrap, choices, promise_judge
from backend.app.engine.world_model.companions import choose_companions
from backend.app.engine.world_model.commitments import (due_commitments, expire_commitments, record_commitment,
                                                         mark_reminded)
from backend.app.engine.world_model.contact import deliver, queue_contacts
from backend.app.engine.world_model.evidence import find_inspect_target, inspect
from backend.app.engine.world_model.memory import render
from backend.app.engine.world_model.model import PLAYER, TurnView, WorldModel
from backend.app.engine.world_model.offscreen import resolve_offscreen
from backend.app.engine.world_model.person import Cast
from backend.app.engine.world_model.appraisal import appraise_behaviors
from backend.app.engine.rules.acquaintance import acquaintance_levels, level_for
from backend.app.engine.world_model.stakes import stake_notes
from backend.app.engine.world_model.signals import Candidate, choose_signal, interest_of, signal_catalogue
from backend.app.engine.rules.personality import personalities
from backend.app.engine.world_model.goals import active_goal, agenda_scale, card_note
from backend.app.engine.rules.tracks import social_rules
from backend.app.engine.world_model.deception import DeceptionProfile, choose_cue
from backend.app.engine.world_model.persona import SelfClaim
from backend.app.engine.world_model.standards import enforce_dealbreakers, failing_requirements, viewpoint
from backend.app.engine.world_model.social_acts import (
    CONFIRMED, NEEDS_TARGET, SocialAct, Verdict, act_specs, assess, commit as commit_act, directive as verdict_directive,
    validate as validate_verdict,
)
from backend.app.engine.world_model.npc_decision import (
    append_record as append_decision_record, jev_decision, merge as merge_decision, target_view as npc_target_view,
)
from backend.app.engine.world_model.romance import _eligible_present as romance_eligible_present
from backend.app.engine.world_model.intentions import propose_agenda_invitations, propose_rival_invitations
from backend.app.engine.world_model.agenda import (
    SocialContext, couples_leaving, couples_ready, next_beat, refresh_agendas,
)
from backend.app.engine.state import PendingEvent
from backend.app.engine.rules.clocks import clocks_for, due_beats
from backend.app.engine.world_model.commentary import (
    commentary_for, dossier, fallback_panel, finale_directive, scrub_panel,
)
from backend.app.engine.world_calendar import day_number
from backend.app.engine.world_model.romance import record_departure_decisions, record_relationship_decisions
from backend.app.engine.world_model.epistemics import observe_event
from backend.app.engine.world_model.drama import choose_conflict, record_repair_dialogue
from backend.app.engine.world_model.projection import classify_ending, ending_hint
from backend.app.engine.world_model.speakers import addressed_ids, select_speakers
from backend.app.engine.world_model.stepper import step_world
from backend.app.engine.world_model.threads import advance_threads

# First-person or imperative intent only: "Did you go to bed late?" must not put the player to sleep.
SLEEP = re.compile(
    r"(?:^|[.!?]\s+|\bI(?:'m| am|'ll| will)?\s+|\blet me\s+)"
    r"(?:(?:going|gonna|about)\s+(?:to\s+)?)?"
    r"(?:go(?:ing)?|head(?:ing)?|turn(?:ing)? in|get(?:ting)?|off)\s+(?:off\s+)?(?:to\s+)?(?:sleep|bed)\b"
    r"|\btime (?:to|for) (?:sleep|bed)\b"
    r"|\bI(?:'m| am)?\s+(?:falling asleep|fall asleep|calling it a night|call it a night)\b",
    re.I)
WAKE_TIME = "07:00"
DIALOGUE_MEMORY_CAP = 80
MAX_PERSPECTIVE = 3
PRIVATE_ASIDE = re.compile(r"^\s*\[confessional\s*:[\s\S]*\]\s*$", re.I)


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
    """Each character's warmth toward the player, read from their own heart."""
    model = getattr(state, "world_model", None)
    if model is None:
        return lambda cid: 0.0
    cast = Cast(state)

    def warmth(cid: str) -> float:
        return cast.get(cid).warmth_toward(PLAYER) if cid in model.characters else 0.0
    return warmth


def rivalry_context(state: Any) -> Optional[dict]:
    """Project only the active, authored cast into an optional romance contest."""
    cfg = getattr(state, "story_cfg", {}) or {}
    goal = ((cfg.get("mode") or {}).get("romance_goal") or {}) if isinstance(cfg, dict) else {}
    if not goal.get("enabled") or goal.get("partner_gender") != "opposite_player" \
            or goal.get("rival_gender") != "same_as_player":
        return None
    gender = str(getattr(state, "gender", "") or "").upper()
    if gender not in ("M", "F"):
        return None
    eligible = set(bootstrap.eligible_ids(state))
    return {"enabled": True, "player_gender": gender, "genders": {
        str(char.get("key")): str(char.get("gender") or "").upper()
        for char in (cfg.get("characters") or []) if isinstance(char, dict) and char.get("key") in eligible
    }}


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
    bootstrap.seed_rival_aims_for_state(state, model)     # BL-34: newcomers and orphaned rivals get an aim


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
    model.conversation.lapse_stale(model.turn)
    lapsed = choices.refresh(model)
    if lapsed:
        model.pending_notes.append(lapsed)
    model.player_name = str(getattr(state, "player_name", "") or model.player_name)
    sync_membership(model, state)
    previous_place = model.player_place()
    protected = set(model.present_with_player())
    if getattr(state, "location_id", "") and state.location_id != previous_place:
        # Invited residents walk with the player instead of being left behind (and bid farewell).
        for cid in choose_companions(model, message, protected, warmth_fn(state)):
            model.world.move(cid, state.location_id)
            protected.discard(cid)
        model.world.move(PLAYER, state.location_id)
    now = int(getattr(state, "minute", 0) or 0)
    step = None
    if now > minute_before:
        model.player_availability = "asleep" if sleeping else "awake"
        step = step_world(model, minute_before, now, protected, player_asleep=sleeping)
        advance_threads(model, minute_before, now)
        resolve_offscreen(model, step, GraphRelationships(getattr(state, "character_graph", None)),
                          scorer, rivalry_context(state), social=social_context(state))
        expire_commitments(model, now)
        queue_contacts(model, minute_before, now, warmth_fn(state))
        model.player_availability = "awake"
    for cid in model.pending_meet:
        if cid in model.characters and model.player_place():
            model.world.move(cid, model.player_place())
    model.pending_meet = []
    model.world.minute = now
    mirror_locations(model, state)
    if model.turn == 1 and not model.last_with_player:
        # The authored welcome party already met the player in the opening.
        for cid in getattr(state, "opening_cast", None) or []:
            if cid in model.characters:
                model.last_with_player[cid] = 0
                model.first_met_day.setdefault(cid, 0)
    if message.strip() and not sleeping and not PRIVATE_ASIDE.fullmatch(message):
        present = model.present_with_player()
        model.hear_player_name(message, present)
        event = model.world.add_event(now, model.player_place(), (PLAYER, *present),
                                      f"@{PLAYER} said: {message.strip()[:300]}", kind="utterance",
                                      operation_id=f"utterance:{model.turn}:player" if model.turn else "",
                                      payload={"speaker": PLAYER, "text": message.strip()[:300]})
        observe_event(model.epistemics, PLAYER, event.id, "participant", event.truth, now)
        for cid in present:
            observe_event(model.epistemics, cid, event.id, "heard", event.truth, now)
            model.memories.add(cid, event.truth, f"told_by:{PLAYER}", now,
                               kind="dialogue", event_id=event.id)
        if len(present) == 1:
            model.world.add_event(now, model.player_place(), (PLAYER, present[0]),
                                  f"@{PLAYER} and @{present[0]} talked alone", kind="private_talk",
                                  operation_id=f"private_talk:{model.turn}")
    model.goals.apply_shifts(model, personalities(getattr(state, "story_cfg", None) or {}),
                             getattr(state, "character_graph", None), now)
    ctx = social_context(state)
    if ctx is not None and ctx.rules.couples is not None:
        advance_npc_life(state, model, ctx, now)
        propose_agenda_invitations(model, now)
    else:
        propose_rival_invitations(model, rivalry_context(state),
                                  GraphRelationships(getattr(state, "character_graph", None)), now)
    conflict_focus = choose_conflict(model.drama, set(model.present_with_player()), model.world.day_index(now))
    # A sleeping player saw nothing of the night: no "came in / left" beats.
    view = _build_view(model, state, message, None if sleeping else step, place_names,
                       None if sleeping else conflict_focus, farewell=protected)
    model.view = view
    return view


def _goal_note(model: WorldModel, people: dict[str, Any], cid: str, names: dict[str, str]) -> str:
    """`; private aim: ...` for the person's heaviest goal, or nothing for someone with no goals (P-07)."""
    goal = active_goal(model.goals, cid, people.get(cid))
    return f"; {card_note(goal, model.goals.weight(cid, goal), names)}" if goal is not None else ""


def _build_view(model: WorldModel, state: Any, message: str, step: Any, place_names: dict[str, str],
                conflict_focus: Any = None, farewell: Iterable[str] = ()) -> TurnView:
    """`farewell`: who was with the player when this turn began; on an exit turn they may still speak."""
    names = model.names()
    view = TurnView(names=names)
    here = model.player_place()
    present = model.present_with_player()
    asleep_here = [c for c in model.present_with_player(include_asleep=True) if c not in present]
    view.present = present
    view.time_text = model.world.datetime_at().strftime("%A %H:%M")
    if conflict_focus is not None:
        view.must_address.append("There is a visible tension in this scene: "
                                 + render(conflict_focus.surface, names)
                                 + ". Let the people involved respond if the player engages; "
                                   "do not reveal an unseen cause as fact.")
    today = model.world.day_index(model.world.minute)
    levels = acquaintance_levels(getattr(state, "story_cfg", None) or {})
    view.not_told_name = [cid for cid in present if cid not in model.knows_player_name]
    view.energy = _room_energy(getattr(state, "story_cfg", None) or {}, present)
    ritual = str(getattr(state, "opening_ritual_brief", "") or "").strip()
    if ritual:                                  # the story's one-time group question (opening_scene.group_ritual_brief)
        view.must_address.append(ritual)
    people = personalities(getattr(state, "story_cfg", None) or {})
    for cid in present:
        c = model.characters[cid]
        activity = c.activity or "here"
        view.cards.append(f"{c.name} ({c.descriptor}): {activity}; {c.availability}"
                          + (f"; mood: {c.mood}" if c.mood else "")
                          + f"; {_encounter_note(model, cid)}; {_name_note(model, cid)}"
                          + _conduct_note(model, levels, cid, today) + _goal_note(model, people, cid, names))
        level = _level_of(model, levels, cid, today)
        if level is not None:
            view.bearings.append(f"{c.name}: {level.reminder or level.conduct}")
    for cid in present:
        if model.last_with_player.get(cid) != model.turn:
            model.turns_together[cid] = model.turns_together.get(cid, 0) + 1
        model.last_with_player[cid] = model.turn
        model.first_met_day.setdefault(cid, today)
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
        if result.newly_noticed:
            view.must_address.append(f"The player inspects {target.name} and newly notices "
                                     f"{'; '.join(result.newly_noticed)}. "
                                     "Describe exactly this; invent no other clue.")
        elif result.noticed:
            view.must_address.append(f"The player re-inspects {target.name}. They already recorded "
                                     f"{'; '.join(result.noticed)}. There is no newly discovered evidence here. "
                                     "Answer a question about new evidence directly; do not stage the old clue as a discovery.")
        else:
            view.must_address.append(f"The player inspects {target.name} and notices nothing unusual"
                                     + (" at a glance" if result.missed else "") + ". Invent no clue.")
    now = model.world.minute
    for promise in due_commitments(model, now):
        if promise.owner in present_set and promise.counterpart == PLAYER:
            view.must_address.append(f"{names[promise.owner]} promised earlier: {render(promise.text, names)}. "
                                     f"It is due now; {names[promise.owner]} can act on it or bring it up. "
                                     "Do not describe it as completed unless the action actually occurs.")
            mark_reminded(model, promise)
        elif promise.owner == PLAYER and promise.counterpart in present_set:
            view.must_address.append(f"The player promised {names[promise.counterpart]}: {render(promise.text, names)}. "
                                     f"{names[promise.counterpart]} may remind them.")
            mark_reminded(model, promise)
    owes_answer = _question_directives(model, view, present_set, names)
    for note in model.pending_notes:
        view.must_address.append(note)
    model.pending_notes = []
    for verdict in model.pending_verdicts:
        view.must_address.append(verdict_directive(verdict, names, _place_name(place_names, here)))
        if verdict.act.target in present_set:
            owes_answer.add(verdict.act.target)
    addressed_now, _ = addressed_ids(model, message, present)
    day = model.world.day_index(model.world.minute)
    # A yes only opens the choice card; the finale plays on the turn the player confirms leaving (BL-46).
    ending_now = any(v.answer == "accept" and v.act.kind == "ask_leave_together" and v.hint == CONFIRMED
                     for v in model.pending_verdicts)
    for key, text in due_beats(clocks_for(getattr(state, "story_cfg", {}) or {}), model.counters):
        view.must_address.append(text)
        model.counters[key] = 1
        ending_now = ending_now or key.endswith(":trigger")
    commentary = commentary_for(getattr(state, "story_cfg", {}) or {})
    if ending_now and commentary is not None:
        view.must_address.append(finale_directive(commentary, dossier(model, commentary)))
        view.panel_speakers = {p.id: p.name for p in commentary.panelists}
    beat = None if owes_answer else next_beat(model, present_set, day)   # direct questions come first
    if beat is not None:
        cid, intention = beat
        view.must_address.append(BEAT_TEXT[intention.kind].format(
            name=names.get(cid, cid), target=names.get(intention.target, intention.target)))
        model.initiative_last_day[f"beat:{cid}"] = day
        if intention.kind == "test_loyalty":
            model.agendas[cid] = [i for i in model.agendas.get(cid, []) if i != intention]
    _tell_directives(model, state, view, message, present_set, owes_answer | addressed_now, names)
    _signal_directives(model, state, view, present_set, names)
    _, mentioned_now = addressed_ids(model, message, list(model.characters))
    view.must_address.extend(stake_notes(model, present_set, mentioned_now, personalities(getattr(state, "story_cfg", {}) or {}),
                                         names, model.world.day_index(model.world.minute)))
    _requirement_hints(model, state, view, present_set, names)
    candidates = present or [cid for cid in model.characters if not model.is_placed(cid)]
    view.plan = select_speakers(model, candidates, message, warmth_fn(state), owes_answer=owes_answer)
    _, mentioned = addressed_ids(model, message, list(model.characters))
    # Label the player explicitly so a speaker never treats the person in
    # front of them as an absent third party (O11).
    memory_names = {**names, PLAYER: f"the player ({names[PLAYER]})"}
    for cid in view.plan.speakers:
        # Residents' spoken lines are excluded (BL-47): the "@id" mention boost put a speaker's own latest refusal,
        # and lines their listeners heard, back on top whenever the player named them, and the storyteller then
        # repeated it. What the PLAYER told them is still recalled; the recent chat already carries what was said,
        # and the replay guard reads dialogue memories separately.
        found = [m for m in model.memories.search(cid, message, mentions=mentioned, k=MAX_PERSPECTIVE + 1,
                                                  exclude=_is_resident_speech)
                 if not (m.minute == now and m.source == f"told_by:{PLAYER}")][:MAX_PERSPECTIVE]
        rendered = [render(m.text, memory_names)
                    + (f" (heard from {memory_names.get(m.source[8:], 'someone')})"
                       if m.source.startswith("told_by:") and m.source != f"told_by:{PLAYER}" else "")
                    for m in found]
        if rendered:
            view.perspectives[cid] = rendered
    unplaced = [cid for cid in model.characters if not model.is_placed(cid)]
    # Someone on a phone call with the player can speak without being present.
    from backend.app.engine.active_characters import get_on_call_character_keys
    on_call = {k for k in get_on_call_character_keys(state) if k in model.characters}
    exit_voices = set(farewell) & set(model.characters) if view.panel_speakers else set()
    view.allowed_speakers = sorted(set(present) | set(unplaced) | set(view.plan.speakers) | on_call
                                   | set(view.panel_speakers) | exit_voices)
    view.ending_hint = ending_hint(model.endings)
    return view


def _encounter_note(model: WorldModel, cid: str) -> str:
    last = model.last_with_player.get(cid)
    if last is None:
        return "first time meeting the player"
    if last >= model.turn - 1:
        return "has been with the player; no greeting or 'welcome back'"
    return "apart from the player since earlier; a greeting fits"


def _room_energy(cfg: dict, present: list[str]) -> str:
    """The room's mood from who is in it (their sociability): lively when most are outgoing, quiet when most are not."""
    people = personalities(cfg)
    dials = [people[cid].temperament.sociability for cid in present if cid in people]
    if len(dials) < 2:
        return ""
    mean = sum(dials) / len(dials)
    if mean >= 0.65:
        return "lively: most people here are outgoing, so talk overlaps, jokes come easily and silences do not last"
    if mean <= 0.38:
        return "quiet: most people here are reserved, so silences are comfortable and nobody rushes to fill them"
    return ""


def _level_of(model: WorldModel, levels: tuple, cid: str, today: int):
    """The acquaintance level this person has reached with the player this turn (None without a ladder)."""
    if not levels:
        return None
    days = today - model.first_met_day.get(cid, today)
    turns = model.turns_together.get(cid, 0) + (0 if model.last_with_player.get(cid) == model.turn else 1)
    return level_for(levels, days, turns)


def _conduct_note(model: WorldModel, levels: tuple, cid: str, today: int) -> str:
    """How well this person knows the player, as the story's authored conduct for that level (empty if none)."""
    level = _level_of(model, levels, cid, today)
    return f"; how well they know the player: {level.id}. {level.conduct}" if level else ""


def _name_note(model: WorldModel, cid: str) -> str:
    if cid in model.knows_player_name:
        return "knows the player's name; never asks it again"
    return "has not learned the player's name"


MAX_QUESTION_DIRECTIVES = 3


def _question_directives(model: WorldModel, view: TurnView, present: set[str], names: dict[str, str]) -> set[str]:
    """Add open player questions to the scene contract; return who owes an answer here."""
    owes: set[str] = set()
    shown = 0
    for question in model.conversation.open_questions():
        name = names.get(question.addressee, question.addressee)
        if question.addressee in present:
            if shown >= MAX_QUESTION_DIRECTIVES:
                continue
            shown += 1
            owes.add(question.addressee)
            earlier = "" if question.asked_turn == model.turn else " earlier and it is still unanswered"
            view.must_address.append(
                f'The player asked {name}{earlier}: "{question.text}". {name} must respond to it directly: '
                "answer it, refuse, say they do not know, or say when they will answer. "
                f"Nobody else answers for {name}; do not replace the answer with atmosphere.")
        elif question.asked_turn == model.turn:
            view.must_address.append(
                f'The player asked {name}, who is not here: "{question.text}". Nobody else answers for {name}; '
                f"someone present may say {name} is not here.")
    return owes


def social_context(state: Any) -> Optional[SocialContext]:
    cfg = getattr(state, "story_cfg", {}) or {}
    rules = social_rules(cfg) if isinstance(cfg, dict) else None
    if rules is None or rules.appraisal is None:
        return None
    genders = {str(c.get("key")): str(c.get("gender") or "").upper() for c in cfg.get("characters") or []}
    genders[PLAYER] = str(getattr(state, "gender", "") or "").upper()
    return SocialContext(rules, genders)


def record_behaviors(state: Any, behaviors: Iterable[Any]) -> list:
    """Observed behavior this turn -> each present perceiver's impressions (story tracks only)."""
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state) or not behaviors:
        return []
    ctx = social_context(state)
    if ctx is None:
        return []
    witnesses = set(model.present_with_player()) if model.player_place() else set()
    applied = appraise_behaviors(model, ctx.rules, personalities(state.story_cfg), behaviors, witnesses,
                                 getattr(state, "character_graph", None), turn_key=str(model.turn + 1),
                                 genders=ctx.genders)
    model.pending_notes.extend(reaction_cues(model, state, behaviors, applied))
    return applied


MAX_REACTION_CUES = 2
CUE_TEXT = {
    "warm": "{name} responds warmly to what the player just did ({tag}): show it in their expression, tone or how "
            "they hold themself; do not explain why.",
    "cool": "{name} reacts coolly to what the player just did ({tag}): a small sign of discomfort or distance, "
            "shown, not explained.",
    "flat": "{name} is polite but unmoved by what the player just did ({tag}): a courteous, ordinary reaction "
            "with no warmth added.",
    "stale": "{name} liked that, but it has stopped landing today (the player has done much the same already): "
             "a friendly, ordinary reaction; do not say why.",
}


def reaction_cues(model: WorldModel, state: Any, behaviors: Iterable[Any], applied: Iterable[Any]) -> list[str]:
    """How each present resident took what the player just did, as storyteller cues (cause -> effect feedback).

    Grounded in the authored tastes and the standing book, never a number: warm (they like it), cool (they dislike
    it), flat (it does not move them) or stale (they like it, but the same gesture already landed today and the
    day's gain has shrunk). At most one cue per person and two per turn, strongest first. Without this the player
    saw nothing on most turns and could not learn what each resident values.
    """
    present = set(model.present_with_player())
    people = personalities(getattr(state, "story_cfg", {}) or {})
    names = model.names()
    effects = list(applied or [])
    best: dict[str, tuple[float, str, str]] = {}
    for item in behaviors or []:
        cid, tag = str(getattr(item, "to_id", "")), str(getattr(item, "tag", ""))
        if str(getattr(item, "from_id", "")) != PLAYER or cid not in present or not tag:
            continue
        weight = people[cid].taste(tag) if cid in people else 0.0
        mine = [e for e in effects if e.owner == cid and e.target == PLAYER and e.tag == tag]
        proposed, got = sum(e.proposed for e in mine), sum(e.applied for e in mine)
        if weight > 0 and proposed > 0 and got < 0.5 * proposed:
            kind = "stale"
        else:
            kind = "warm" if weight > 0 else "cool" if weight < 0 else "flat"
        strength = abs(weight) + (0.01 if kind == "stale" else 0.0)
        if cid not in best or strength > best[cid][0]:
            best[cid] = (strength, tag, kind)
    ordered = sorted(best.items(), key=lambda row: (-row[1][0], row[0]))[:MAX_REACTION_CUES]
    return [CUE_TEXT[kind].format(name=names.get(cid, cid), tag=tag.replace("_", " "))
            for cid, (_, tag, kind) in ordered]


def advance_npc_life(state: Any, model: WorldModel, ctx: SocialContext, now: int) -> None:
    """Agendas from each character's own standing; couples form and leave only by mutual qualification."""
    policy, track = ctx.rules.couples, ctx.rules.appraisal.track
    model.standing.bind(ctx.rules.tracks)
    day = model.world.day_index(now)
    people = personalities(getattr(state, "story_cfg", None) or {})
    refresh_agendas(model, track, policy.interested_tier, ctx.eligible, day,
                    scale=lambda cid: agenda_scale(model.goals, cid, people.get(cid)))
    place = model.player_place()
    for a, b in couples_ready(model, track, policy.dating_tier, ctx.eligible, day):
        key = f"{a}|{b}"
        model.npc_couples[key] = day
        model.world.add_event(now, model.world.place_of(a) or place, (a, b), f"@{a} and @{b} became a couple",
                              kind="npc_couple_formed", visibility="public", operation_id=f"couple:{key}")
        model.add_trace(now, model.world.place_of(a) or place, f"@{a} and @{b} seem to be together now",
                        involves=(a, b))
    lifecycle = getattr(state, "cast_lifecycle", None)
    for a, b in couples_leaving(model, track, policy.committed_tier, policy.days_together, day):
        key = f"{a}|{b}"
        model.departed_couples.append(key)
        model.counters["couples_left"] = model.counters.get("couples_left", 0) + 1
        model.world.add_event(now, model.world.place_of(a) or place, (a, b),
                              f"@{a} and @{b} left the house together as a couple", kind="couple_departure",
                              visibility="public", operation_id=f"couple_departure:{key}")
        model.add_trace(now, place, f"@{a} and @{b} have packed up and left the house together", involves=(a, b))
        if lifecycle is not None and getattr(lifecycle, "enabled", False):
            for cid in (a, b):
                if cid not in lifecycle.active_ids():
                    continue
                lifecycle.propose_departure(cid, minute=now, reason="left the house as a couple",
                                            event_id=f"couple_propose_{key}_{cid}")
                state.pending_events.append(PendingEvent(
                    event_id=f"couple_replace_{key}_{cid}", event_type="cast_departure_replacement",
                    scheduled_day=day_number(now), payload={"departing_id": cid, "reason": "left as a couple"},
                    created_minute=now))


BEAT_TEXT = {
    "test_loyalty": "{name} saw the player being flirtatious with someone else and wants to find out where "
                    "they stand; they may bring it up.",
    "pursue": "{name} is drawn to the player and may look for a moment with them.",
    "compete_for": "{name} is drawn to {target} and can see the player is too. {name} may make ONE small, visible "
                   "move toward {target} (an invitation, an interruption, a pointed compliment) but does not confess "
                   "or say what they privately feel.",
}


def _claim_grounded(key: str, value: str, message: str) -> bool:
    """The claim is in this message: its value words, or (for yes/no facts) the fact's own word."""
    words = set(_WORDS.findall(message.lower()))
    if any(w in words for w in _WORDS.findall(value.lower())):
        return True
    stems = [part.rstrip("s") for part in key.lower().split("_") if len(part) >= 4]
    return any(word.startswith(stem) for stem in stems for word in words)


def record_claims(state: Any, claims: Iterable[Any], *, message: str) -> list[tuple[str, str]]:
    """Self-claims in the player's message, heard by whoever is present. Returns new disputes."""
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state) or not claims:
        return []
    cfg = getattr(state, "story_cfg", {}) or {}
    keys = {str(k).lower() for k in cfg.get("player_fact_keys") or []}
    audience = tuple(model.present_with_player()) if model.player_place() else ()
    people = personalities(cfg)
    graph = getattr(state, "character_graph", None)
    now, disputes = model.world.minute, []
    for index, item in enumerate(claims):
        key, value = str(getattr(item, "key", "")).lower(), str(getattr(item, "value", ""))
        if key not in keys or not value or not _claim_grounded(key, value, message or ""):
            continue
        before = {cid: model.persona.belief(cid, PLAYER, key).status for cid in audience}
        event = model.world.add_event(now, model.player_place(), (PLAYER, *audience),
                                      f"@{PLAYER} said their {key} is {value}", kind="self_claim",
                                      operation_id=f"claim:{model.turn + 1}:{index}",
                                      payload={"key": key, "value": value})
        recorded = model.persona.claim(SelfClaim(PLAYER, key, value, audience, now, model.turn + 1, event.id,
                                                 bool(getattr(item, "correction", False))))
        if recorded is None:
            continue
        for cid in audience:
            model.memories.add(cid, f"@{PLAYER} said their {key} is {value}", f"told_by:{PLAYER}", now,
                               kind="claim", event_id=event.id)
            if before[cid] != "disputed" and model.persona.belief(cid, PLAYER, key).status == "disputed":
                disputes.append((cid, key))
                skepticism = people.get(cid).temperament.skepticism if cid in people else 0.5
                if graph is not None:
                    graph.update_edge(cid, PLAYER, suspicion_delta=round(0.1 * skepticism, 4))
                model.world.add_event(now, model.player_place(), (cid, PLAYER),
                                      f"@{cid} noticed @{PLAYER} said conflicting things about their {key}",
                                      kind="claim_dispute", operation_id=f"dispute:{event.id}:{cid}")
        rules = social_rules(cfg)
        if rules is not None:
            for cid in audience:
                enforce_dealbreakers(model, rules, cid, PLAYER, event.id, graph)
    return disputes


def _tell_directives(model: WorldModel, state: Any, view: TurnView, message: str, present: set[str],
                     questioned: set[str], names: dict[str, str]) -> None:
    """At most one seeded, perceivable tell per character this turn; behavior only, never a verdict."""
    from backend.app.engine.active_characters import get_on_call_character_keys
    on_call = {k for k in get_on_call_character_keys(state) if k in model.characters}
    people = personalities(getattr(state, "story_cfg", {}) or {})
    profiles = getattr(state, "characters", {}) or {}
    for cid in sorted(present | on_call):
        cues = list(getattr(profiles.get(cid), "tells", None) or [])
        if not cues:
            continue
        profile = people[cid].deception if cid in people else DeceptionProfile()
        cue = choose_cue(profile, cues, message, cid in questioned, f"{model.seed}:tell:{model.turn}:{cid}",
                         voice_only=cid in on_call and cid not in present)
        if cue:
            view.must_address.append(f"{names.get(cid, cid)} shows a small tell: {cue}. Show it only as "
                                     "behavior the player can notice; it proves nothing on its own.")


def _signal_directives(model: WorldModel, state: Any, view: TurnView, present: set[str], names: dict[str, str]) -> None:
    """At most one ambiguous affinity signal this turn (world_model/signals.py): behaviour only, never a feeling."""
    ctx = social_context(state)
    if ctx is None:
        return
    cfg = getattr(state, "story_cfg", {}) or {}
    spec = ctx.rules.tracks.get(ctx.rules.appraisal.track)
    people = personalities(cfg)
    candidates = []
    for cid in sorted(present):
        if not ctx.eligible(cid, PLAYER):
            continue
        standing = model.standing.get(cid, PLAYER, ctx.rules.appraisal.track)
        temperament = people[cid].temperament if cid in people else None
        candidates.append(Candidate(cid, interest_of(standing.value if standing else 0.0, spec),
                                    temperament.openness if temperament else 0.5,
                                    temperament.pride if temperament else 0.5,
                                    temperament.sociability if temperament else 0.5))
    pick = choose_signal(candidates, model.turn, model.seed, model.last_signal_turn, signal_catalogue(cfg))
    if pick:
        cid, behaviour = pick
        model.last_signal_turn[cid] = model.turn
        view.must_address.append(f"{names.get(cid, cid)} {behaviour}. Show it only as behaviour, never explain or label "
                                 "it: it could be politeness or interest.")


def _is_resident_speech(memory: Any) -> bool:
    return memory.kind == "dialogue" and memory.source != f"told_by:{PLAYER}"


def _requirement_hints(model: WorldModel, state: Any, view: TurnView, present: set[str],
                       names: dict[str, str]) -> None:
    rules = social_rules(getattr(state, "story_cfg", {}) or {})
    if rules is None:
        return
    graph = getattr(state, "character_graph", None)
    for cid in sorted(present):
        vp = viewpoint(model, cid, PLAYER, graph)
        for track in rules.tracks:
            for requirement in failing_requirements(rules, cid, track, vp):
                if requirement.disclosure in ("hint", "open") and requirement.tell:
                    reason = " They may say why if asked." if requirement.disclosure == "open" else \
                        " Do not state the reason."
                    view.must_address.append(f"{names.get(cid, cid)}: {requirement.tell}.{reason}")


def social_act_kinds(state: Any) -> list[str]:
    return sorted(act_specs(getattr(state, "story_cfg", {}) or {}))


def _act_context(state: Any, proposal: Any):
    """(model, spec, act, assessment) for a proposed act the rules can assess here, else None."""
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state) or proposal is None or model.romance_outcome:
        return None
    cfg = getattr(state, "story_cfg", {}) or {}
    spec = act_specs(cfg).get(str(getattr(proposal, "kind", "")))
    if spec is None:
        return None
    rules = social_rules(cfg)
    if rules is not None:
        model.standing.bind(rules.tracks)
    act = SocialAct(spec.kind, str(getattr(proposal, "target", "") or ""))
    assessment = assess(model, spec, act, romance_eligible_present(state))
    return None if assessment is None else (model, spec, act, assessment)


def npc_question(state: Any, proposal: Any):
    """What to ask Jev for this act: (Decision, target's own-view text), or None when no judgment is needed.

    Nothing to ask when the act is the player's own, a hard rule already settles it, or it doesn't apply here.
    """
    context = _act_context(state, proposal)
    if context is None:
        return None
    model, spec, act, assessment = context
    if assessment.hard or act.kind not in NEEDS_TARGET:
        return None
    view = npc_target_view(model, spec, act, state.story_cfg, model.names(), getattr(state, "character_graph", None),
                           ready=assessment.can_accept)
    return jev_decision(act.target, act), view


def leave_meaning_subject(state: Any, proposal: Any):
    """(target_id, target_name, already_a_couple) when this act is an "ask to leave together", else None.

    Only that act is ambiguous ("leave with me" may be a walk or the win), so it is the only one whose
    meaning is read before the target judges it (BL-46).
    """
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state) or proposal is None or model.romance_outcome:
        return None
    if str(getattr(proposal, "kind", "")) != "ask_leave_together":
        return None
    target = str(getattr(proposal, "target", "") or "")
    if target not in model.characters:
        return None
    return target, model.names().get(target, target), model.romance_relationship_partner == target


def apply_leave_meaning(state: Any, proposal: Any, meaning: str) -> Any:
    """The act to judge: the proposal when it means leaving as a couple, else None plus a storyteller note.

    An outing or an unclear ask is not a typed act: no verdict, no cooldown, nobody moves this turn.
    """
    subject = leave_meaning_subject(state, proposal)
    if subject is None or meaning == "couple":
        return proposal
    model, name = state.world_model, subject[1]
    if meaning == "outing":
        model.pending_notes.append(
            f"The player asked {name} to go somewhere together for a while, not to leave the house for good. "
            f"{name} answers the invitation in character. Nobody moves until the player does.")
    else:
        model.pending_notes.append(
            f"{name} is not sure whether the player means a short outing or leaving the house for good together "
            f"as a couple. {name} asks which they mean, in character, before answering. It is not a yes or a no yet.")
    return None


def answer_choice(state: Any, message: str) -> Optional[str]:
    """Handle a choice-card answer. Returns the storyteller cue that replaces the message, or None.

    `leave_now` queues the confirmed departure verdict (the finale plays on this turn). Anything else that
    names a card (keep talking, a stale or unknown option) continues the scene without ending it.
    """
    model = getattr(state, "world_model", None)
    text = (message or "").strip()
    if model is None or not enabled(state):
        return None
    is_choice_text = text.startswith(choices.CHOICE_PREFIX)
    if not is_choice_text and not choices.PLAY_ENDING.match(text):
        return None
    lapsed = choices.refresh(model)
    if lapsed:
        model.pending_notes.append(lapsed)
    picked = choices.answer(model, text)
    if picked in (choices.SKIP_TO_PLAN, choices.KEEP_PLAYING):
        choice, partner = model.pending_choice, str(model.pending_choice.get("partner") or "")
        name, when, what = model.names().get(partner, partner), choice.get("when"), choice.get("what")
        model.pending_choice = {}
        if picked == choices.KEEP_PLAYING:
            return "[The player keeps playing; the plan stays on their mind.]"
        if model.player_place():
            model.pending_meet.append(partner)      # they meet, wherever the player is (BL-35), after the world steps
        return (f"[The player skips ahead to {when} for their plan with {name}: {what}. "
                f"It is now {when} and they are together.]")
    if picked == choices.LEAVE_NOW:
        partner = str(model.pending_choice.get("partner") or "")
        name = model.names().get(partner, partner)
        if not choices.partner_here(model):
            model.pending_notes.append(f"{name} is not here, so the player cannot leave with them yet. "
                                       "They have to find them first.")
            return f"[The player wants to leave the house together with {name} now, but {name} is not here.]"
        model.pending_verdicts = [Verdict(SocialAct("ask_leave_together", partner), "accept", CONFIRMED)]
        return f"[The player chooses to leave the house together with {name} now.]"
    if picked == choices.KEEP_TALKING:
        return "[The player chooses to keep talking for now.]"
    return "[The player tried to answer an offer that no longer stands.]" if is_choice_text else None


def record_social_act(state: Any, proposal: Any, *, mode: str = "rules", judgment: Any = None) -> Optional[Verdict]:
    """Decide this turn's social act (rules, Jev within the rules, or both logged); held until end_turn validates it."""
    context = _act_context(state, proposal)
    if context is None:
        return None
    model, spec, act, assessment = context
    verdict, record = merge_decision(assessment, mode, judgment, turn=model.turn + 1)
    if act.kind in NEEDS_TARGET:
        append_decision_record(model, record)
    model.pending_verdicts = [verdict]
    return verdict


def open_questions(state: Any) -> list[dict[str, str]]:
    """Open player questions, in the shape the turn extractor lists them."""
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state):
        return []
    return [{"id": q.id, "addressee": q.addressee, "text": q.text} for q in model.conversation.open_questions()]


_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
QUESTION_GROUNDING = 0.6


def _grounded_in(question: str, message: str) -> bool:
    """True when the question is actually in this message, not copied from history."""
    q_norm, m_norm = " ".join(question.lower().split()), " ".join(message.lower().split())
    if q_norm and q_norm.rstrip("?？") in m_norm:
        return True
    q_words = set(_WORDS.findall(q_norm))
    return bool(q_words) and len(q_words & set(_WORDS.findall(m_norm))) / len(q_words) >= QUESTION_GROUNDING


def record_questions(state: Any, asked: Iterable[Any], statuses: Iterable[Any], *, message: str) -> None:
    """Apply the extractor's judgement of the previous reply, then the player's new questions.

    `statuses` items carry `question_id`/`status` about the reply the player just saw;
    `asked` items carry `addressee`/`question` and are kept only if grounded in `message`,
    the player's current message.
    """
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state):
        return
    convo = model.conversation
    for update in statuses or []:
        convo.resolve(str(getattr(update, "question_id", "")), str(getattr(update, "status", "")), model.turn)
    upcoming = model.turn + 1  # begin_turn increments model.turn next
    for item in asked or []:
        addressee = str(getattr(item, "addressee", ""))
        question = str(getattr(item, "question", ""))
        if addressee in model.characters and _grounded_in(question, message or ""):
            convo.ask(addressee, question, upcoming)


def end_turn(state: Any, message: str, segments: list[dict]) -> None:
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state):
        return
    now = model.world.minute
    present = set(model.present_with_player())
    replied: set[str] = set()
    for index, seg in enumerate(segments or []):
        speaker = seg.get("speaker_id")
        if seg.get("kind") != "dialogue" or speaker not in model.characters:
            continue
        text = str(seg.get("text") or "").strip()
        model.characters[speaker].record_spoke(model.turn)
        if speaker in present:
            replied.add(speaker)
        if speaker not in model.known_names:
            model.known_names.append(speaker)
        # A remote call is heard by its participants, not every resident
        # standing next to the player's phone.
        listeners = present | {speaker} if speaker in present else {speaker}
        model.hear_player_name(text, listeners)
        listeners.add(PLAYER)
        event = model.world.add_event(now, model.world.place_of(speaker) or "",
                                      tuple(sorted(listeners)), f"@{speaker} said: {text[:240]}",
                                      kind="utterance", visibility="private",
                                      operation_id=f"utterance:{model.turn}:{index}:{speaker}" if model.turn else "",
                                      payload={"speaker": speaker, "text": text[:240]})
        for cid in listeners:
            observe_event(model.epistemics, cid, event.id, "participant" if cid == speaker else "heard",
                          event.truth, now)
            if cid != PLAYER:
                model.memories.add(cid, event.truth, "witnessed", now, kind="dialogue", event_id=event.id)
    for speaker in sorted(replied):    # once per turn, however many lines they spoke
        model.conversation.note_reply(speaker, model.turn)
    specs = act_specs(getattr(state, "story_cfg", {}) or {})
    names = model.names()
    commentary = commentary_for(getattr(state, "story_cfg", {}) or {})
    if commentary is not None and model.view.panel_speakers:
        scrub_panel(segments, commentary)
        if not any(s.get("speaker_id") in model.view.panel_speakers for s in segments):
            segments.extend(fallback_panel(commentary, dossier(model, commentary)))
            model.view.panel_fallbacks += 1
    for verdict in model.pending_verdicts:
        model.view.verdict_repairs += validate_verdict(verdict, segments, names)
        witnesses = tuple(c for c in present if c != verdict.act.target)
        commit_act(state, specs[verdict.act.kind], verdict, witnesses)
    model.pending_verdicts = []
    # A yes that this turn's events invalidated (relationship ended, partner gone) leaves the response now, and the
    # storyteller hears about it next turn.
    lapsed = choices.refresh(model)
    if lapsed:
        model.pending_notes.append(lapsed)
    prior_relationship_partner = model.romance_relationship_partner
    record_relationship_decisions(state, message, segments)
    record_departure_decisions(state, message, segments, prior_relationship_partner)
    repaired = record_repair_dialogue(model, message, segments)
    relationships = GraphRelationships(getattr(state, "character_graph", None))
    for thread_id in repaired:
        thread = model.drama.get(thread_id)
        a, b = thread.participants[:2]
        relationships.adjust(a, b, trust_delta=0.03, narrative=f"Reconciled after {thread.cause_event_id}")
        relationships.adjust(b, a, trust_delta=0.03, narrative=f"Reconciled after {thread.cause_event_id}")
    last = next((s for s in reversed(segments or []) if str(s.get("text") or "").strip()), None)
    if last is not None:
        model.endings = (model.endings + [classify_ending(str(last.get("text")))])[-6:]
    _prune(model)


async def review_promises(state: Any, prior_user: str, prior_reply: str, message: str, resolver: Any = None) -> list:
    """Ask Jev whether the open promises between people who are here have been carried out.

    Runs before the scene is built, so a promise kept in the last exchange is closed before it can be raised.
    """
    from backend.app.config import settings
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state) or not getattr(settings, "PROMISE_JUDGE_ENABLED", False):
        return []
    now = int(getattr(state, "minute", 0) or model.world.minute)
    return await promise_judge.review(model, prior_user, prior_reply, message, now,
                                      GraphRelationships(getattr(state, "character_graph", None)), resolver)


def own_spoken_lines(state: Any) -> dict[str, list[str]]:
    """What each character has already said in this game, oldest first (BL-47 replay check).

    Read from the dialogue memories the world model keeps of every spoken line; the player's words, narration and
    other people's lines are not anyone's own history.
    """
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state):
        return {}
    lines: dict[str, list[str]] = {}
    for memory in model.memories.memories:
        if memory.kind != "dialogue" or memory.owner not in model.characters:
            continue
        prefix = f"@{memory.owner} said: "
        if memory.text.startswith(prefix):
            lines.setdefault(memory.owner, []).append(memory.text[len(prefix):])
    return lines


def record_commitments(state: Any, updates: Iterable[Any]) -> list:
    """Promises the turn extractor found in the previous exchange (CommitmentUpdate)."""
    model = getattr(state, "world_model", None)
    if model is None or not enabled(state):
        return []
    now = int(getattr(state, "minute", 0) or model.world.minute)
    recorded = []
    for update in updates or []:
        memory = record_commitment(model, str(getattr(update, "owner", "")), str(getattr(update, "counterpart", "")),
                                   str(getattr(update, "what", "")), str(getattr(update, "when", "later")), now)
        if memory is not None:
            recorded.append(memory)
            _offer_skip_to_plan(model, memory, now)
    return recorded


def _offer_skip_to_plan(model: WorldModel, memory: Any, now: int) -> None:
    """A plan the player and a resident agreed for later can be skipped to (BL-46); never forced."""
    if memory.due is None or memory.due - now < choices.MIN_SKIP_MINUTES:
        return
    people = {memory.owner, memory.counterpart}
    partner = next(iter(people - {PLAYER}), "") if PLAYER in people and len(people) == 2 else ""
    if partner in model.characters:
        choices.offer_plan_skip(model, partner, _plan_text(model, memory), memory.due)


def _plan_text(model: WorldModel, memory: Any) -> str:
    """The plan in plain words ("meet at the cafe"), without the memory's own framing."""
    agreement = next((a for a in model.agreements.items if a.id == memory.agreement_id), None)
    return str(agreement.activity if agreement is not None else memory.text).strip().rstrip(".")


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
