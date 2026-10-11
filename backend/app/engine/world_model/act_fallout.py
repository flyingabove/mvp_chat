"""Fallout of a turned-down high-stakes act: who saw it thinks differently, and rivals see an opening (generic).

When a confession (or any act that needs a target) is not accepted in front of others:
- every witness the story's appraisal policy covers thinks a little less of the asker (a standing loss on the act's
  track, harsher for skeptical witnesses): social value drops "just like in real social situations";
- on a clear no, the person who refused cools toward the asker as well;
- witnesses who share the asker's gender and are free see an opening: they gain their own `pursue` aim on the
  person who refused (scaled by their strategy), so a rival may now move first.
A yes has no fallout and an act with no witnesses has none. People who were not there hear only through gossip,
which already exists; nothing here tells them. Effects go through the standing book and the agenda, never around them.
"""
from __future__ import annotations

from typing import Any, Iterable

from backend.app.engine.rules.personality import personalities, strategy_mods
from backend.app.engine.rules.tracks import social_rules
from backend.app.engine.world_model.agenda import INTENTION_DAYS, add_intention
from backend.app.engine.world_model.courtship import Courtship
from backend.app.engine.world_model.intent import Intention
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.standing import Impression

TAG = "failed_confession"


def _genders(state: Any, cfg: dict) -> dict[str, str]:
    genders = {str(c.get("key")): str(c.get("gender") or "").upper() for c in cfg.get("characters") or []}
    genders[PLAYER] = str(getattr(state, "gender", "") or "").upper()
    return genders


def apply_fallout(state: Any, track: str, kind: str, target: str, answer: str, witnesses: Iterable[str],
                  cause_event_id: str) -> None:
    """Apply the consequences of a declined act. Idempotent per cause event."""
    model: WorldModel = state.world_model
    cfg = getattr(state, "story_cfg", None) or {}
    rules = social_rules(cfg)
    if answer == "accept" or rules is None or rules.appraisal is None or not track:
        return
    watchers = sorted(w for w in set(witnesses) if w not in (PLAYER, target) and w in model.characters)
    if not watchers and answer != "reject":
        return
    genders, people = _genders(state, cfg), personalities(cfg)
    model.standing.bind(rules.tracks)
    policy, minute = rules.appraisal, model.world.minute
    courtship = Courtship.of(rules, genders)
    romance, rivalry, tuning = courtship.intensity.romance, courtship.intensity.rivalry, courtship.tuning
    day = model.world.day_index(minute)
    stamp = f"{cause_event_id}:{kind}"
    for watcher in watchers:
        if courtship.eligible(watcher, PLAYER):
            skepticism = people[watcher].temperament.skepticism if watcher in people else 0.5
            model.standing.apply(Impression(f"fallout:{stamp}:{watcher}", watcher, PLAYER, track, TAG,
                                            -tuning.witness_loss * romance * (0.6 + 0.8 * skepticism), cause_event_id, minute, day,
                                            "witnessed"))
        if rivalry > 0 and watcher not in {k for pair in model.npc_couples for k in pair.split("|")} \
                and courtship.competes(watcher, PLAYER, target):
            scale = strategy_mods(people[watcher].strategy).aim_scale if watcher in people else 1.0
            add_intention(model, watcher, Intention("pursue", target, min(1.0, tuning.rival_aim * rivalry * scale),
                                                    "saw an opening", day + INTENTION_DAYS))
    if answer == "reject" and courtship.eligible(target, PLAYER):
        model.standing.apply(Impression(f"fallout:{stamp}:{target}", target, PLAYER, track, TAG, -tuning.refuser_loss * romance,
                                        cause_event_id, minute, day, "participant"))
