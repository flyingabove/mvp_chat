"""A small, story-free six-resident Terrace-shaped fixture for `SeasonRunner` (BL-86, P-04).

Lives in `backend/app/sim/` (not under `tests/`) so both the unit tests and the operator-only season-runner
debug endpoint (`backend/app/api/season_debug.py`) can build the same fixture without production code
importing from the test tree. `tests/backend/app/sim/helpers.py` re-exports these for the existing tests.
"""
from __future__ import annotations

from backend.app.engine.cast_lifecycle import CastLifecycleState
from backend.app.engine.world_model.character import CharacterState
from backend.app.engine.world_model.entities import Entity
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.routine import Routine, RoutineBlock, default_blocks
from backend.app.engine.world_model.world import World
from backend.app.sim.runner import Story

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


class InMemoryRelationships:
    """Minimal in-memory relationship edges: no persistence, no story -- just enough for a fixture run.

    Mirrors `tests/backend/app/engine/world_model/helpers.py::FakeRelationships` on purpose (same tiny
    shape); kept here as its own copy so this production module never imports from the test tree.
    """

    def __init__(self) -> None:
        self.state: dict[tuple[str, str], dict[str, float]] = {}
        self.notes: list[tuple[str, str, str]] = []

    def feelings(self, a: str, b: str) -> dict[str, float]:
        return dict(self.state.get((a, b), {}))

    def adjust(self, a: str, b: str, narrative: str = "", **deltas: float) -> None:
        edge = self.state.setdefault((a, b), {})
        for key, value in deltas.items():
            name = key.removesuffix("_delta")
            edge[name] = round(edge.get(name, 0.0) + value, 4)
        self.notes.append((a, b, narrative))


def build_story(seed: str = "season-seed") -> Story:
    return Story(model=build_model(seed), relationships=InMemoryRelationships(), cast_lifecycle=build_lifecycle())
