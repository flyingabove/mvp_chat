"""Small, story-free world models for unit tests."""
from __future__ import annotations

from backend.app.engine.world_model.character import CharacterState
from backend.app.engine.world_model.entities import Entity
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.routine import Routine, RoutineBlock, default_blocks
from backend.app.engine.world_model.world import World

START = "2015-09-02T19:00:00"   # a Wednesday evening


def make_model(people: dict[str, str] | None = None, player_place: str = "kitchen", **kwargs) -> WorldModel:
    """people: {character_id: place}. Characters get no routine unless a test sets one."""
    people = {"ann": "kitchen", "ben": "kitchen", "cat": "living_room"} if people is None else people
    world = World(start_datetime=START, minute=0)
    world.entities[PLAYER] = Entity(PLAYER, "player", "Paul")
    world.move(PLAYER, player_place)
    model = WorldModel(world=world, seed="test", player_name="Paul", **kwargs)
    for cid, place in people.items():
        model.characters[cid] = CharacterState(cid, cid.capitalize(), descriptor=f"the {cid} person")
        world.entities[cid] = Entity(cid, "character", cid.capitalize())
        world.move(cid, place)
    return model


def with_routine(model: WorldModel, cid: str, home: str, *blocks: RoutineBlock, sleep: bool = True,
                 free_place: str = "") -> None:
    all_blocks = (default_blocks(home) if sleep else []) + list(blocks)
    model.characters[cid].routine = Routine(blocks=all_blocks, home=home, free_place=free_place)


class FakeRelationships:
    """In-memory relationship edges for off-screen tests."""

    def __init__(self, feelings: dict[tuple[str, str], dict[str, float]] | None = None) -> None:
        self.state = {k: dict(v) for k, v in (feelings or {}).items()}
        self.notes: list[tuple[str, str, str]] = []

    def feelings(self, a: str, b: str) -> dict[str, float]:
        return dict(self.state.get((a, b), {}))

    def adjust(self, a: str, b: str, narrative: str = "", **deltas: float) -> None:
        edge = self.state.setdefault((a, b), {})
        for key, value in deltas.items():
            name = key.removesuffix("_delta")
            edge[name] = round(edge.get(name, 0.0) + value, 4)
        self.notes.append((a, b, narrative))
