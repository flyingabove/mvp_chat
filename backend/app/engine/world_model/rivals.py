"""Independent aims for the player's rivals (BL-34).

In an ensemble romance the housemates who share the player's gender have "their own romantic plans", yet with
no aim of their own they showed nothing for days: NPC-to-NPC feelings only grow off-screen, slowly. When a story
opts in (`social_tracks.couples.rival_aim`, a priority between 0 and 1) each such resident starts with one
long-lived `pursue` aim on a resident they could be drawn to, chosen by the house seed (so the same house always
gives the same aims). Aims may overlap on purpose: when the player wins the same person, `agenda.refresh_agendas`
turns the overlap into `compete_for` and the rival becomes visible.

Run again whenever the house changes (a newcomer, a target who moved out or coupled up): only rivals without a live
aim get one, so it is idempotent and never disturbs an aim that still stands.

No feelings are invented: an aim is an intention to seek someone out, not a standing. Whether it becomes anything
still depends on what the two people do and on the target's own preferences.
"""
from __future__ import annotations

import random
from typing import Any

from backend.app.engine.world_model.agenda import AIM_DAYS, add_intention, intentions
from backend.app.engine.world_model.intent import Intention
from backend.app.engine.world_model.model import WorldModel


def _in_couple(model: WorldModel, cid: str) -> bool:
    return any(cid in key.split("|") for key in model.npc_couples)


def seed_rival_aims(model: WorldModel, rules: Any, genders: dict[str, str], player_gender: str) -> list[tuple[str, str]]:
    """Give each rival (resident of the player's gender) one aim; returns the (rival, target) pairs added."""
    policy = getattr(rules, "couples", None)
    appraisal = getattr(rules, "appraisal", None)
    if policy is None or appraisal is None or policy.rival_aim <= 0 or player_gender not in ("M", "F"):
        return []
    day = model.world.day_index(model.world.minute)
    ids = sorted(model.characters)
    added: list[tuple[str, str]] = []
    for rival in ids:
        if genders.get(rival) != player_gender or _in_couple(model, rival):
            continue
        if any(i.kind == "pursue" and i.target in model.characters and not _in_couple(model, i.target)
               for i in intentions(model, rival, day)):
            continue                      # a live aim: its target is still in the house and still free
        options = [t for t in ids if t != rival and not _in_couple(model, t)
                   and appraisal.covers(genders.get(rival, ""), genders.get(t, ""))]
        if not options:
            continue
        crush = random.Random(f"{model.seed}:rival_aim:{rival}").choice(options)
        add_intention(model, rival, Intention("pursue", crush, policy.rival_aim, "has their eye on them",
                                              day + AIM_DAYS))
        added.append((rival, crush))
    return added
