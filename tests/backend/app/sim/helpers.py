"""A small, story-free six-resident Terrace-shaped fixture for SeasonRunner tests."""
from __future__ import annotations

from backend.app.engine.cast_lifecycle import CastLifecycleState
from backend.app.engine.world_model.character import CharacterState
from backend.app.engine.world_model.entities import Entity
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.routine import Routine, RoutineBlock, default_blocks
from backend.app.engine.world_model.world import World
from backend.app.sim.runner import Story
from tests.backend.app.engine.world_model.helpers import FakeRelationships

START = "2015-09-02T06:00:00"
NPC_IDS = ("ava", "ben", "cleo", "drew", "eli")
LIVING_ROOM, BEDROOM = "living_room", "bedroom"


def build_model(seed: str = "season-seed") -> WorldModel:
    """Five NPCs plus the player, all under the same shared-living-room routine.

    The player is just another character here: it gets a `CharacterState` and a routine like any NPC, so
    `step_world` drives it the same way -- nothing in the runner (or this fixture) hard-assumes a human.
    """
    world = World(start_datetime=START, minute=0)
    model = WorldModel(world=world, seed=seed, player_name="Resident F")
    day_block = RoutineBlock("07:00", "23:00", LIVING_ROOM, "hanging out", "awake")
    for cid in (*NPC_IDS, PLAYER):
        name = cid.capitalize() if cid != PLAYER else "Resident F"
        model.characters[cid] = CharacterState(cid, name, descriptor="a housemate")
        model.characters[cid].routine = Routine(blocks=default_blocks(BEDROOM) + [day_block], home=BEDROOM)
        world.entities[cid] = Entity(cid, "character", name)
        world.move(cid, BEDROOM)
    return model


def build_lifecycle() -> CastLifecycleState:
    config = {
        "enabled": True,
        "arrival_location_id": LIVING_ROOM,
        "slot_groups": {"house": {"capacity": 6, "label": "House"}},
        "members": {cid: {"slot_group": "house", "sequence": i, "initial_status": "active"}
                   for i, cid in enumerate(NPC_IDS)},
    }
    lifecycle = CastLifecycleState.from_config(config, character_ids=NPC_IDS, location_ids=[LIVING_ROOM, BEDROOM])
    lifecycle.reserve_player_slot("house")
    return lifecycle


def build_story(seed: str = "season-seed") -> Story:
    return Story(model=build_model(seed), relationships=FakeRelationships(), cast_lifecycle=build_lifecycle())
