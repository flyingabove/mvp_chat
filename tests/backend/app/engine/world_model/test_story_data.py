"""Authoring guard: every story's world_model section must reference real places,
characters and well-formed blocks, so the engine stays generic and data errors
fail in CI instead of silently stranding characters."""
import json
from pathlib import Path

import pytest

from backend.app.engine.world_model.routine import RoutineBlock
from backend.app.engine.world_model.threads import Thread

STORIES = Path("backend/app/stories")


def _stories_with_world_model():
    found = []
    for path in sorted(STORIES.glob("*/*_story.json")):
        story = json.loads(path.read_text(encoding="utf-8"))
        if "world_model" in story:
            world_file = STORIES / story["world"]["file"]
            world = json.loads(world_file.read_text(encoding="utf-8"))
            found.append(pytest.param(story, world, id=story["id"]))
    return found


STORY_PARAMS = _stories_with_world_model()


def test_both_playable_stories_author_a_world_model():
    assert {p.id for p in STORY_PARAMS} >= {"six_strangers", "iu_murder_mystery"}


@pytest.mark.parametrize("story,world", STORY_PARAMS)
def test_routine_places_and_characters_exist(story, world):
    section = story["world_model"]
    places = set(world["locations"]) | set(section.get("place_names") or {})
    keys = {c["key"] for c in story["characters"]}
    routines = section.get("routines") or {}
    for name, template in (routines.get("templates") or {}).items():
        for raw in template.get("blocks") or []:
            RoutineBlock.from_dict(raw, "home")
            assert raw["place"] in places | {"home"}, (name, raw["place"])
        assert not template.get("free_place") or template["free_place"] in places
    for key, cfg in (routines.get("characters") or {}).items():
        assert key in keys, key
        assert not cfg.get("template") or cfg["template"] in (routines.get("templates") or {})
        for raw in cfg.get("blocks") or []:
            RoutineBlock.from_dict(raw, "home")
            assert raw["place"] in places | {"home"}, (key, raw["place"])
    for key, home in (section.get("homes") or {}).items():
        assert key in keys and home in places


@pytest.mark.parametrize("story,world", STORY_PARAMS)
def test_threads_and_entities_are_well_formed(story, world):
    section = story["world_model"]
    places = set(world["locations"]) | set(section.get("place_names") or {})
    keys = {c["key"] for c in story["characters"]}
    for raw in section.get("threads") or []:
        thread = Thread.from_dict(raw)
        assert thread.owner in keys and thread.topics
        for milestone in thread.milestones:
            assert milestone.visibility in ("private", "public")
            assert not milestone.place or milestone.place in places
            assert set(milestone.memory_for) <= keys | {"player"}
            if milestone.visibility == "public":
                assert milestone.trace, f"{thread.id}/{milestone.id} is public but leaves no trace"
    for raw in section.get("entities") or []:
        assert raw["location"] in places and raw.get("surfaces")
        assert all(s.get("text") for s in raw["surfaces"])


def test_six_strangers_routines_keep_everyone_home_for_the_opening_dinner():
    """Wednesday 19:00: no hard block may pull a resident away at game start."""
    from backend.app.engine.world_model.routine import build_routine
    from backend.app.engine.world_model.world import World
    story = json.loads((STORIES / "7_six_strangers/six_strangers_story.json").read_text(encoding="utf-8"))
    routines = story["world_model"]["routines"]
    world = World(story["world"]["start_datetime"])
    for key, cfg in routines["characters"].items():
        block = build_routine(cfg, routines["templates"], "boys_bedroom").active(world, 0, key, "any")
        assert block is None or not block.hard, key
