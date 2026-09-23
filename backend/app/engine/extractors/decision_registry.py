# backend/app/engine/extractors/decision_registry.py
"""Pure-data Decision definitions for TurnExtractor's Jev-eligible abilities.

Per JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §9 and §12 step 5 ("smallest
slice first"): only the abilities that are pure `choice`, need no fan-out,
no vocabulary authoring, and no arithmetic mapping are registered here.
Ability numbers refer to JEV_EXTRACTOR_REDESIGN_2026_09_22.md's chart:

  ability 1 (movement_intent)         -> movement_intent
  ability 2 (destination_id)          -> movement_destination
  ability 5 (previous_reply_location) -> prev_scene_location

Ability 3 (confidence) needs no Decision of its own — it's read natively
from whichever provider answered (JevRawAnswer.confidence, or the legacy
extractor's self-reported float), per the redesign doc's finding that a
dedicated field was never reliable anyway.

No engine/-purity violation: this module is pure data (dataclasses, no I/O,
no httpx import) even though it lives under engine/extractors/ alongside
turn_extractor.py, matching the package layout in
JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §2.

KNOWN SCOPE LIMITATION, documented rather than silently worked around:
`movement_destination`'s `allowed` set is built from the FULL
`world_locations` dict passed into TurnExtractor.extract(), not a
reachable-from-current-position subset. The provider architecture doc's §5
recommends prefiltering to reachable locations (cheaper, and per Jev's own
docs, more accurate) — but computing reachability needs the current
location id and the world graph's travel rules, neither of which
TurnExtractor.extract()'s existing signature carries today. Adding that
would be a signature change beyond step 3's "behaviour byte-identical"
scope, so it is deferred rather than risked here. The `none_of_these`
option and the existing allowed-id re-validation still make an
unreachable answer safe — it is only less efficient, not less correct.
"""
from __future__ import annotations

from typing import Mapping

from backend.app.llm.decisions.types import Criticality, Decision

MOVEMENT_TASK = "movement"
PREV_SCENE_TASK = "prev_scene"

NONE_OF_THESE = "none_of_these"


def movement_intent_decision() -> Decision:
    """Ability 1. Two-option choice, no fan-out, no dependency on scene
    content beyond the current player message."""
    return Decision(
        id="movement_intent",
        task=MOVEMENT_TASK,
        kind="choice",
        instructions=(
            "Does the CURRENT PLAYER MESSAGE contain an explicit, sincere "
            "intention to move to a different location right now? Sarcastic "
            "or ironic statements that actually REFUSE movement, and any "
            "hypothetical/past-tense mention of movement, must be NONE."
        ),
        criteria={
            "MOVE": "the player sincerely states they are going somewhere now",
            "NONE": "no sincere, explicit movement intent right now",
        },
        criticality=Criticality.CRITICAL,
        allowed=frozenset({"MOVE", "NONE"}),
        legacy_path=("movement", "intent"),
    )


def movement_destination_decision(world_locations: Mapping[str, str]) -> Decision:
    """Ability 2. Options built from the currently-known location set (see
    module docstring for the reachable-prefilter limitation)."""
    criteria = {
        str(loc_id): f"{str(loc_id)} ({str(name or '').strip()})"
        for loc_id, name in (world_locations or {}).items()
    }
    criteria[NONE_OF_THESE] = "no movement, or the destination is not in this list"
    return Decision(
        id="movement_destination",
        task=MOVEMENT_TASK,
        kind="choice",
        instructions=(
            "If the player is moving (per the movement_intent question), which "
            "of these known locations are they moving to? If there is no "
            "movement, or the stated destination is not one of these known "
            "locations, answer none_of_these."
        ),
        criteria=criteria,
        criticality=Criticality.CRITICAL,
        allowed=frozenset(criteria.keys()),
        none_option=NONE_OF_THESE,
        legacy_path=("movement", "destination_id"),
    )


def prev_scene_location_decision(world_locations: Mapping[str, str]) -> Decision:
    """Ability 5. Asks where the PREVIOUS assistant reply's scene took
    place — not reachability-filtered (the scene could be anywhere already
    established), matching the redesign doc's table ("all location ids +
    none_of_these")."""
    criteria = {
        str(loc_id): f"{str(loc_id)} ({str(name or '').strip()})"
        for loc_id, name in (world_locations or {}).items()
    }
    criteria[NONE_OF_THESE] = "the previous reply does not clearly establish a location"
    return Decision(
        id="prev_scene_location",
        task=PREV_SCENE_TASK,
        kind="choice",
        instructions=(
            "Which of these known locations does the PREVIOUS TURN ASSISTANT "
            "REPLY establish as the scene's location? Extract from that reply "
            "only, not from the current player message. If unclear, answer "
            "none_of_these."
        ),
        criteria=criteria,
        criticality=Criticality.CRITICAL,
        allowed=frozenset(criteria.keys()),
        none_option=NONE_OF_THESE,
        legacy_path=("previous_scene", "location_id"),
    )
