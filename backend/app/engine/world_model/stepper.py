"""Move every character through an elapsed interval in chronological order.

Time only passes on player turns, so this runs once per turn over
(minute_before, minute_after]. A short conversational interval never pulls a
person out of the player's scene (anti-vanish) unless their block is `hard`;
long intervals (sleep, time skips) apply routines fully.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from backend.app.engine.world_model.routine import block_key

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

TICK_MIN = 15
ANTI_VANISH_MAX_INTERVAL = 60


@dataclass
class Transition:
    minute: int
    character: str
    origin: Optional[str]
    destination: Optional[str]
    availability: str
    activity: str


@dataclass
class StepResult:
    transitions: list[Transition] = field(default_factory=list)
    # (minute, {character: (place, availability)}, player_place, player_awake)
    timeline: list[tuple[int, dict[str, tuple[str, str]], str, bool]] = field(default_factory=list)


def _apply(model: "WorldModel", cid: str, minute: int, protected: bool) -> Optional[Transition]:
    character = model.characters[cid]
    routine = character.routine
    if not routine.blocks or not model.is_placed(cid):
        return None
    block = routine.active(model.world, minute, cid, model.seed)
    key = block_key(block)
    if key == character.block:
        return None
    if protected and not (block and block.hard):
        return None
    origin = model.world.where_is(cid)
    if block is not None:
        destination = block.place or origin
        availability, activity = block.availability, block.activity
    else:
        # Free time: leave an away-from-home block's place; otherwise stay put.
        previous_place = character.block.split("@", 1)[1].split(":", 1)[0] if "@" in character.block else ""
        away = previous_place and previous_place == origin and previous_place != routine.home
        destination = (routine.free_place or routine.home or origin) if away else origin
        availability, activity = "awake", ""
    if destination and destination != origin:
        model.world.move(cid, destination)
    character.block, character.availability, character.activity = key, availability, activity
    return Transition(minute, cid, origin, model.world.where_is(cid), availability, activity)


def step_world(model: "WorldModel", start: int, end: int, scene_present: set[str],
               player_asleep: bool = False) -> StepResult:
    result = StepResult()
    if end <= start:
        return result
    protected = set(scene_present) if end - start < ANTI_VANISH_MAX_INTERVAL else set()
    points = set(range(start + TICK_MIN, end, TICK_MIN)) | {end}
    for cid, character in model.characters.items():
        points.update(character.routine.boundaries(model.world, start, end, cid, model.seed))
    player_place = model.player_place()
    for minute in sorted(points):
        for cid in sorted(model.characters):
            transition = _apply(model, cid, minute, cid in protected)
            if transition is not None:
                result.transitions.append(transition)
        snapshot = {cid: (model.world.place_of(cid) or "", c.availability)
                    for cid, c in model.characters.items() if model.is_placed(cid)}
        result.timeline.append((minute, snapshot, player_place, not player_asleep))
    model.world.minute = end
    return result
