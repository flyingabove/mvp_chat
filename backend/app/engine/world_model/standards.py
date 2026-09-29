"""Applying a person's standards to their standing: gates, caps and dealbreakers.

Judgement always uses the holder's own viewpoint. An unknown condition keeps
a gate closed but never closes a track: only a condition established false
triggers a dealbreaker.
"""
from __future__ import annotations

from typing import Any, Callable

from backend.app.engine.rules.conditions import Viewpoint
from backend.app.engine.rules.tracks import SocialRules, Tier
from backend.app.engine.world_model.standing import AppliedEffect, Impression


def viewpoint(model: Any, owner: str, target: str, graph: Any = None) -> Viewpoint:
    return Viewpoint(model=model, holder=owner, subject=target, graph=graph, standings=model.standing)


def gate_checker(rules: SocialRules, owner: str, track: str, vp: Viewpoint) -> Callable[[Tier], bool]:
    caps = [r for r in rules.requirements_for(owner, track) if r.on_fail == "cap"]

    def is_open(tier: Tier) -> bool:
        conditions = ([tier.gate] if tier.gate else []) + [r.condition for r in caps if r.tier == tier.id]
        return all(c.evaluate(vp) is True for c in conditions)
    return is_open


def failing_requirements(rules: SocialRules, owner: str, track: str, vp: Viewpoint) -> list:
    """Requirements whose condition is established false from the owner's view (for tells)."""
    return [r for r in rules.requirements_for(owner, track) if r.condition.evaluate(vp) is False]


def enforce_dealbreakers(model: Any, rules: SocialRules, owner: str, target: str, cause_event_id: str,
                         graph: Any = None) -> list[AppliedEffect]:
    model.standing.bind(rules.tracks)
    vp = viewpoint(model, owner, target, graph)
    closed = []
    minute = model.world.minute
    day = model.world.day_index(minute)
    for track in rules.tracks:
        for requirement in rules.requirements_for(owner, track):
            if requirement.on_fail == "dealbreaker" and requirement.condition.evaluate(vp) is False:
                effect = model.standing.close(owner, target, track, requirement.id, cause_event_id, minute, day)
                if effect is not None:
                    closed.append(effect)
    return closed


def apply_impression(model: Any, rules: SocialRules, impression: Impression, graph: Any = None) -> AppliedEffect:
    """The one path from an appraised impression to a standing change."""
    model.standing.bind(rules.tracks)
    vp = viewpoint(model, impression.owner, impression.target, graph)
    return model.standing.apply(impression, gate_checker(rules, impression.owner, impression.track, vp))
