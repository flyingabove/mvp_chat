"""Typed social acts with explicit consent: confess, ask to leave together, leave alone, withdraw.

The existing extraction call proposes which act the player's message makes.
The target decides from their own standing and standards (a documented local
policy; standing qualifies an ask, it never forces a yes). The verdict is
held for the turn, voiced by the storyteller from a directive, checked
against the generated reply before display, and committed with the reply.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.romance import (
    commit_mutual_departure, commit_relationship, commit_solo_departure, end_relationship,
)

KINDS = ("confess", "ask_leave_together", "leave_alone", "withdraw")
NEEDS_TARGET = frozenset({"confess", "ask_leave_together"})
LABELS = {"confess": "confession", "ask_leave_together": "asking to leave the house together"}
_ACCEPTANCE = re.compile(r"\b(yes|of course|absolutely|i'?d love (to|that)|let'?s (do it|go|leave)|"
                         r"i (love|like) you too|me too|i feel the same)\b", re.I)


@dataclass(frozen=True)
class ActSpec:
    kind: str
    track: str = ""
    requires_tier: str = ""
    min_standing: float = 0.0
    requires_relationship: bool = False
    cooldown_days: int = 0


@dataclass(frozen=True)
class SocialAct:
    kind: str
    target: str = ""


@dataclass(frozen=True)
class Verdict:
    act: SocialAct
    answer: str                # accept | not_yet | reject
    hint: str = ""             # disclosure-safe reason seed for narration


def act_specs(story_cfg: dict[str, Any]) -> dict[str, ActSpec]:
    specs: dict[str, ActSpec] = {}
    for raw in (story_cfg or {}).get("social_acts") or []:
        kind = str(raw.get("kind") or "")
        if kind not in KINDS or kind in specs:
            raise ValueError(f"unknown or duplicate social act {kind!r}")
        specs[kind] = ActSpec(kind, str(raw.get("track") or ""), str(raw.get("requires_tier") or ""),
                              float(raw.get("min_standing") or 0), bool(raw.get("requires_relationship")),
                              int(raw.get("cooldown_days") or 0))
        if kind in NEEDS_TARGET and not (specs[kind].track and specs[kind].requires_tier):
            raise ValueError(f"act {kind!r} needs a track and requires_tier")
    return specs


def decide(model: WorldModel, spec: ActSpec, act: SocialAct, eligible: set[str]) -> Optional[Verdict]:
    """The target's own decision, or None when the act cannot apply here (wrong/absent target)."""
    if act.kind == "leave_alone":
        return Verdict(act, "accept")
    if act.kind == "withdraw":
        return Verdict(act, "accept") if model.romance_relationship_partner else None
    if act.target not in eligible:
        return None
    day = model.world.day_index(model.world.minute)
    if model.act_cooldowns.get(f"{act.kind}:{act.target}", -1) >= day:
        return Verdict(act, "not_yet", "they need time after last time before hearing this again")
    standing = model.standing.get(act.target, PLAYER, spec.track)
    if standing is not None and standing.closed_by:
        return Verdict(act, "reject", "something has settled it for them; they are kind but clear")
    if spec.requires_relationship and model.romance_relationship_partner != act.target:
        return Verdict(act, "not_yet", "you are not together yet")
    reached = model.standing.tier_reached(act.target, PLAYER, spec.track, spec.requires_tier)
    value = standing.value if standing is not None else 0.0
    if reached is True and value >= spec.min_standing:
        return Verdict(act, "accept")
    return Verdict(act, "not_yet", "they want to know you better first")


def directive(verdict: Verdict, names: dict[str, str]) -> str:
    act = verdict.act
    if act.kind == "leave_alone":
        return ("The player has chosen to leave the house alone. Write their exit: goodbyes from whoever is "
                "here; nobody forces them to stay.")
    if act.kind == "withdraw":
        return "The player has ended their romantic relationship. Show the other person's reaction honestly."
    name = names.get(act.target, act.target)
    label = LABELS[act.kind]
    if verdict.answer == "accept":
        return f"{name} says yes to the player's {label}. Show a clear yes in their own voice."
    tone = "turns it down" if verdict.answer == "reject" else "does not say yes yet"
    return (f"{name} {tone} after the player's {label} ({verdict.hint}). They must not say yes. Voice it in "
            "character and do not state any hidden rule or score.")


def validate(verdict: Verdict, segments: list[dict], names: dict[str, str]) -> int:
    """Replace any displayed line that contradicts a non-acceptance. Returns repairs made."""
    if verdict.answer == "accept" or verdict.act.kind not in NEEDS_TARGET:
        return 0
    repairs = 0
    for segment in segments:
        if segment.get("kind") == "dialogue" and segment.get("speaker_id") == verdict.act.target \
                and _ACCEPTANCE.search(str(segment.get("text") or "")):
            segment.clear()
            segment.update({"kind": "narration",
                            "text": f"{names.get(verdict.act.target, verdict.act.target)} hesitates and does not "
                                    "say yes."})
            repairs += 1
    return repairs


def commit(state: Any, spec: ActSpec, verdict: Verdict, witnesses: tuple[str, ...]) -> None:
    model: WorldModel = state.world_model
    act = verdict.act
    day = model.world.day_index(model.world.minute)
    if act.kind == "leave_alone":
        commit_solo_departure(model)
        return
    if act.kind == "withdraw":
        partner = model.romance_relationship_partner
        end_relationship(model)
        model.world.add_event(model.world.minute, model.player_place(), (PLAYER, partner, *witnesses),
                              f"@{PLAYER} ended the relationship with @{partner}", kind="relationship_withdrawn",
                              visibility="public", operation_id=f"act:withdraw:{model.turn}")
        return
    kind = f"{act.kind}_{'accepted' if verdict.answer == 'accept' else 'declined'}"
    event = model.world.add_event(model.world.minute, model.player_place(), (PLAYER, act.target, *witnesses),
                                  f"@{act.target} {'accepted' if verdict.answer == 'accept' else 'declined'} "
                                  f"@{PLAYER}'s {LABELS[act.kind]}", kind=kind, visibility="public",
                                  operation_id=f"act:{act.kind}:{model.turn}:{act.target}",
                                  payload={"act": act.kind, "target": act.target, "answer": verdict.answer})
    if verdict.answer != "accept":
        if spec.cooldown_days:
            model.act_cooldowns[f"{act.kind}:{act.target}"] = day + spec.cooldown_days - 1
        return
    if act.kind == "confess":
        commit_relationship(model, act.target, (event.id,))
    elif act.kind == "ask_leave_together":
        commit_mutual_departure(state, act.target)
