"""Rival pressure: someone pursuing a person pulls them toward the pursuer and away from the player (BL-98).

Rival aims were only words (a `compete_for` beat) and a seeded `pursue` priority, so a scripted engaged player won in
12 to 18 days whatever the rivals' strength (P-08 sweep). Once a day, for every resident pursuing another resident who is
not in a couple, the target's standing toward the pursuer rises by `tuning.rival_pull x priority` and, when the target
is drawn to the player, their standing toward the player falls by `tuning.rival_cost x` the strongest rival's priority,
both scaled by the `rivalry` intensity. Standing gains obey the track's own caps and ceilings; a loss never goes below
zero. If the target ends up pursuing the pursuer back and both reach the dating tier, `agenda.couples_ready` makes them
a couple, which is how a rival wins. No gender, story or name appears here; who pursues whom comes from the agendas.
"""
from __future__ import annotations

from typing import Any

from backend.app.engine.world_model.agenda import intentions
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.standing import Impression

TAG = "rival_pressure"


def apply_rival_pressure(model: WorldModel, rules: Any, day: int, minute: int) -> None:
    """Apply today's pressure once (idempotent per rival, target and day)."""
    if rules is None or rules.appraisal is None or rules.intensity.rivalry <= 0:
        return
    track, tuning, rivalry = rules.appraisal.track, rules.tuning, rules.intensity.rivalry
    coupled = {cid for key in model.npc_couples for cid in key.split("|")}
    strongest: dict[str, float] = {}
    for rival in sorted(model.characters):
        if rival == PLAYER or rival in coupled:
            continue
        for aim in intentions(model, rival, day):
            if aim.kind != "pursue" or aim.target in (PLAYER, rival) or aim.target in coupled                     or aim.target not in model.characters:
                continue
            cause = f"rival_pressure:{rival}:{aim.target}:{day}"
            model.standing.apply(Impression(f"{cause}:pull", aim.target, rival, track, TAG,
                                            tuning.rival_pull * rivalry * aim.priority, cause, minute, day, "participant"))
            strongest[aim.target] = max(strongest.get(aim.target, 0.0), aim.priority)
    for target, priority in sorted(strongest.items()):
        if model.stances.has(target, "crush", PLAYER):
            cause = f"rival_pressure:{target}:{day}"
            model.standing.apply(Impression(f"{cause}:cost", target, PLAYER, track, TAG,
                                            -tuning.rival_cost * rivalry * priority, cause, minute, day, "participant"))
