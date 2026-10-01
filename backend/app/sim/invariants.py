"""Pure invariant checks run after every simulated day (BL-86).

Each function takes read-only state and returns a list of violation strings (empty = no violation). None of
them mutate anything, so each is independently unit-testable without running a season at all.
"""
from __future__ import annotations

from typing import Optional

from backend.app.engine.cast_lifecycle import CastLifecycleState
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.social_acts import NEEDS_TARGET


def check_cast_size(lifecycle: CastLifecycleState, expected: int = 6) -> list[str]:
    """Terrace holds exactly `expected` residents at all times (the player occupies one slot)."""
    total = sum(len(lifecycle.active_ids(group)) for group in lifecycle.slot_capacities)
    total += 1 if lifecycle.player_slot_group else 0
    return [] if total == expected else [f"cast size is {total}, expected {expected}"]


def check_no_unperceived_knowledge(model: WorldModel) -> list[str]:
    """No character holds a memory of an event that was never recorded as perceived by them.

    A memory tied to a world event (`event_id` set) must have a matching `Observation` in the epistemic
    ledger for that same owner; otherwise the character "knows" something through fake omniscience rather
    than through something they witnessed, heard or were told.
    """
    violations = []
    for memory in model.memories.memories:
        if not memory.event_id:
            continue
        perceived = any(o.owner == memory.owner and o.event_id == memory.event_id
                        for o in model.epistemics.observations)
        if not perceived:
            violations.append(f"{memory.owner} knows event {memory.event_id} ({memory.text!r}) "
                              "with no recorded observation")
    return violations


def check_no_consent_bypass(model: WorldModel) -> list[str]:
    """Every committed "<act>_accepted" event for a target-requiring act has a logged accept verdict.

    `social_acts.assess()` (via `npc_decision.merge`) is the only gate that may turn a proposal into an
    accepted outcome for `confess` / `ask_leave_together`; a caller that commits such an event without that
    verdict being logged has routed around consent.
    """
    violations = []
    logged_accepts = {(rec.get("act"), rec.get("target")) for rec in model.decision_log
                      if rec.get("final") == "accept"}
    for event in model.world.events:
        if not event.kind.endswith("_accepted"):
            continue
        act_kind = event.kind[: -len("_accepted")]
        if act_kind not in NEEDS_TARGET:
            continue
        target = str((event.payload or {}).get("target") or "")
        if (act_kind, target) not in logged_accepts:
            violations.append(f"event {event.id} accepted {act_kind} for {target!r} with no logged consent verdict")
    return violations


def check_day(model: WorldModel, lifecycle: Optional[CastLifecycleState] = None,
             expected_cast_size: int = 6) -> list[str]:
    """All three invariants together, as the runner calls them after each simulated day."""
    violations = list(check_no_unperceived_knowledge(model))
    violations.extend(check_no_consent_bypass(model))
    if lifecycle is not None:
        violations.extend(check_cast_size(lifecycle, expected_cast_size))
    return violations
