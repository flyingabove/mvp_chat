"""Perceive -> appraise -> feel: one event, a different reaction from each person.

Behavior is proposed by the existing extraction call (actor, target, tag from
a closed story vocabulary). The engine commits it as a world event; every
character who perceived it appraises it with their own tastes and
temperament. Standing changes go through StandingBook (apply_impression);
feelings through the character graph, the single feelings writer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from backend.app.engine.rules.personality import Personality
from backend.app.engine.rules.tracks import SocialRules
from backend.app.engine.world_model.agenda import add_intention
from backend.app.engine.world_model.events import Event
from backend.app.engine.world_model.intent import Intention
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.standards import apply_impression, enforce_dealbreakers
from backend.app.engine.world_model.standing import AppliedEffect, Impression


APPRAISED_KEEP = 500
REACTION_DAYS = 2


@dataclass
class Appraisal:
    perceiver: str
    impressions: list[Impression] = field(default_factory=list)
    feelings: dict[str, dict[str, float]] = field(default_factory=dict)   # toward -> dimension deltas
    reactions: list[tuple[str, str]] = field(default_factory=list)        # (intention kind, target)


def record_behavior(model: WorldModel, actor: str, target: str, tag: str, witnesses: Iterable[str],
                    operation_id: str) -> Event:
    participants = tuple(sorted({actor, target, *witnesses}))
    return model.world.add_event(model.world.minute, model.world.place_of(actor) or model.player_place(),
                                 participants, f"@{actor} was {tag} toward @{target}", kind="behavior",
                                 operation_id=operation_id,
                                 payload={"actor": actor, "target": target, "tag": tag})


def appraise(model: WorldModel, rules: SocialRules, personality: Personality, perceiver: str,
             event: Event, genders: dict[str, str] | None = None) -> Appraisal:
    """How `perceiver` reacts to a behavior event, judged only by their own tastes and standing."""
    policy = rules.appraisal
    actor, target, tag = event.payload["actor"], event.payload["target"], event.payload["tag"]
    result = Appraisal(perceiver)
    if policy is None or perceiver == actor or perceiver == PLAYER:
        return result
    genders = genders or {}
    if not policy.covers(genders.get(perceiver, ""), genders.get(actor, "")):
        return result
    day = model.world.day_index(event.minute)
    weight = personality.taste(tag)
    temper = personality.temperament
    if perceiver == target:
        delta = weight * policy.gain_scale
        channel, affection = "target", weight * policy.feeling_scale
    else:
        tier = model.standing.tier_reached(perceiver, actor, policy.track, policy.jealousy_tier) \
            if policy.jealousy_tier else None
        if tag in policy.romantic_tags and tier is True:
            jealousy = round(0.1 * temper.jealousy, 4)
            result.feelings[actor] = {"jealousy_delta": jealousy, "trust_delta": -round(0.05 * temper.jealousy, 4)}
            result.impressions.append(_impression(event, perceiver, actor, policy.track, f"{tag}_elsewhere",
                                                  -policy.gain_scale * temper.jealousy, day, "witnessed"))
            if temper.jealousy >= 0.5:
                result.reactions.append(("test_loyalty", actor))
            return result
        delta = weight * policy.gain_scale * policy.witness_scale
        channel, affection = "witnessed", weight * policy.feeling_scale * policy.witness_scale
    if delta < 0:
        delta *= 1.5 - temper.forgiveness   # the unforgiving feel slights harder
    if delta:
        result.impressions.append(_impression(event, perceiver, actor, policy.track, tag, delta, day, channel))
    if affection:
        result.feelings[actor] = {"affection_delta": round(affection, 4)}
    return result


def _impression(event: Event, owner: str, target: str, track: str, tag: str, delta: float, day: int,
                channel: str) -> Impression:
    return Impression(f"{event.id}:{owner}:{track}", owner, target, track, tag, round(delta, 4), event.id,
                      event.minute, day, channel)


def appraise_behaviors(model: WorldModel, rules: SocialRules, personalities: dict[str, Personality],
                       behaviors: Iterable[Any], witnesses: Iterable[str], graph: Any = None,
                       turn_key: str = "", genders: dict[str, str] | None = None) -> list[AppliedEffect]:
    """Commit this turn's observed behaviors and let every perceiver react. Idempotent per turn key."""
    model.standing.bind(rules.tracks)
    known = set(model.characters) | {PLAYER}
    seen = [w for w in witnesses if w in model.characters]
    applied: list[AppliedEffect] = []
    for index, item in enumerate(behaviors or []):
        actor, target, tag = str(item.from_id), str(item.to_id), str(item.tag)
        if actor not in known or target not in known or actor == target or not tag:
            continue
        event = record_behavior(model, actor, target, tag, seen, f"behavior:{turn_key}:{index}")
        if event.id in model.appraised_events:
            continue
        model.appraised_events = (model.appraised_events + [event.id])[-APPRAISED_KEEP:]
        for perceiver in sorted(set(event.participants) & set(model.characters)):
            appraisal = appraise(model, rules, personalities.get(perceiver, Personality()), perceiver, event,
                                 genders)
            for impression in appraisal.impressions:
                applied.append(apply_impression(model, rules, impression, graph))
            if graph is not None:
                for toward, deltas in appraisal.feelings.items():
                    graph.update_edge(perceiver, toward, narrative="", **deltas)
            day = model.world.day_index(event.minute)
            for kind, toward in appraisal.reactions:
                add_intention(model, perceiver, Intention(kind, toward, 0.8, f"reacting to {event.id}",
                                                          day + REACTION_DAYS))
            enforce_dealbreakers(model, rules, perceiver, actor, event.id, graph)
    return applied
