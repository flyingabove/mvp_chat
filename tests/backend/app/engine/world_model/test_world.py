"""Step 1: world location index, containers, clock, events, character, persistence."""
import pytest

from backend.app.engine.world_model.character import CharacterState
from backend.app.engine.world_model.entities import Entity
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.world import World, parse_hhmm
from tests.backend.app.engine.world_model.helpers import START, make_model


def test_move_is_the_single_writer_and_keeps_both_maps_consistent():
    world = World(START)
    world.move("ann", "kitchen")
    world.move("plate", "kitchen")
    assert world.contents_of("kitchen") == {"ann", "plate"}
    assert world.move("ann", "terrace") == "kitchen"
    assert world.where_is("ann") == "terrace"
    assert world.contents_of("kitchen") == {"plate"}
    assert world.contents_of("terrace") == {"ann"}
    world.remove("plate")
    assert world.contents_of("kitchen") == set() and world.where_is("plate") is None


def test_containers_carry_their_contents_and_place_of_looks_through_them():
    world = World(START, where={"drawer": "study", "letter": "drawer", "desk": "study"})
    assert world.place_of("letter") == "study"
    assert world.contents_of("study") == {"drawer", "desk"}
    assert world.contents_of("study", recursive=True) == {"drawer", "desk", "letter"}
    world.move("drawer", "hallway")
    assert world.place_of("letter") == "hallway"


def test_an_entity_cannot_be_placed_inside_itself():
    world = World(START, where={"box": "room", "bag": "box"})
    with pytest.raises(ValueError):
        world.move("box", "bag")
    with pytest.raises(ValueError):
        world.move("box", "box")


def test_round_trip_rebuilds_contents_from_where_only():
    world = World(START, minute=95, where={"ann": "kitchen", "letter": "drawer", "drawer": "study"})
    world.add_event(10, "kitchen", ["ann"], "@ann cooked", kind="scene")
    data = world.to_dict()
    assert "contents" not in data
    restored = World.from_dict(data)
    assert restored.contents_of("study", recursive=True) == {"drawer", "letter"}
    assert restored.minute == 95 and restored.events[0].truth == "@ann cooked"


def test_clock_helpers_follow_the_story_start_datetime():
    world = World(START, minute=0)
    assert world.minute_of_day(0) == 19 * 60
    assert world.day_index(5 * 60) == 1               # 00:00 next day
    assert world.weekday(0) == 2                      # 2015-09-02 is a Wednesday
    assert world.absolute_minute(1, "07:00") == 12 * 60
    assert world.next_minute_at("07:00", after=0) == 12 * 60
    assert world.next_minute_at("20:00", after=0) == 60
    assert parse_hhmm("23:30") == 1410
    with pytest.raises(ValueError):
        parse_hhmm("25:00")


def test_events_get_monotonic_ids_and_shared_history_is_a_query():
    world = World(START)
    world.add_event(5, "park", ["a", "b"], "@a and @b argued")
    world.add_event(9, "park", ["a", "c"], "@a met @c")
    assert [e.id for e in world.events] == ["E1", "E2"]
    assert [e.id for e in world.shared_events("a", "b")] == ["E1"]
    assert world.shared_events("b", "c") == []


def test_character_location_is_read_from_the_world_index():
    model = make_model({"ann": "kitchen"})
    ann = model.characters["ann"]
    assert ann.get_location(model.world) == "kitchen"
    model.world.move("ann", "terrace")
    assert ann.get_location(model.world) == "terrace"
    assert "location" not in ann.to_dict()


def test_character_rejects_unknown_availability_and_tracks_speaking():
    with pytest.raises(ValueError):
        CharacterState("x", "X", availability="dancing")
    c = CharacterState("x", "X")
    for turn in (1, 3, 4):
        c.record_spoke(turn)
    assert c.turns_since_spoke(5) == 1
    assert CharacterState("y", "Y").turns_since_spoke(5) == 99


def test_present_with_player_excludes_asleep_unless_asked():
    model = make_model({"ann": "kitchen", "ben": "kitchen", "cat": "living_room"})
    model.characters["ben"].availability = "asleep"
    assert model.present_with_player() == ["ann"]
    assert model.present_with_player(include_asleep=True) == ["ann", "ben"]


def test_entity_alias_matching_uses_whole_words():
    closet = Entity("closet_scuff", "evidence", "closet", aliases=["jamb"])
    assert closet.matches("I examine the closet door")
    assert closet.matches("check the JAMB")
    assert not closet.matches("I look at the closets' shadows next to jambalaya")
    with pytest.raises(ValueError):
        Entity("x", "spaceship")


def test_world_model_round_trip_is_lossless():
    model = make_model()
    model.memories.add("ann", "@ben made tea", "witnessed", 3)
    model.add_trace(4, "kitchen", "@ann and @ben seem easier with each other", involves=("ann", "ben"))
    model.known_names.append("ann")
    restored = WorldModel.from_dict(model.to_dict())
    assert restored.to_dict() == model.to_dict()
    assert restored.world.where_is(PLAYER) == "kitchen"
