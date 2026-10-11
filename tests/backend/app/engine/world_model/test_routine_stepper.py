"""Step 3: routines and the world stepper."""
import pytest

from backend.app.engine.world_model.routine import Routine, RoutineBlock, build_routine, default_blocks
from backend.app.engine.world_model.stepper import step_world
from tests.backend.app.engine.world_model.helpers import make_model, with_routine

WORK = RoutineBlock("09:00", "17:00", "office", "at work", "busy")


def test_blocks_can_wrap_midnight_and_free_time_is_none():
    model = make_model({})
    routine = Routine(default_blocks("bedroom"), home="bedroom")
    w = model.world
    assert routine.active(w, w.absolute_minute(0, "23:45"), "ann", "s").availability == "asleep"
    assert routine.active(w, w.absolute_minute(1, "03:00"), "ann", "s").availability == "asleep"
    assert routine.active(w, w.absolute_minute(1, "07:30"), "ann", "s") is None


def test_weekday_filter_applies():
    model = make_model({})
    routine = Routine([RoutineBlock("09:00", "17:00", "office", "at work", days=(5,))])   # Saturdays only
    w = model.world
    assert routine.active(w, w.absolute_minute(1, "10:00"), "ann", "s") is None           # Thursday
    assert routine.active(w, w.absolute_minute(3, "10:00"), "ann", "s") is not None       # Saturday


def test_jitter_is_seeded_bounded_and_stable():
    model = make_model({})
    block = RoutineBlock("09:00", "17:00", "office", "at work", variance=20)
    starts = []
    for seed in ("a", "b", "c", "d", "e"):
        boundaries = Routine([block]).boundaries(model.world, 0, 2 * 1440, "ann", seed)
        starts.append(boundaries[0])
        assert boundaries == Routine([block]).boundaries(model.world, 0, 2 * 1440, "ann", seed)
    base = model.world.absolute_minute(1, "09:00")
    assert all(abs(s - base) <= 20 for s in starts)
    assert len(set(starts)) > 1


def test_invalid_blocks_are_rejected():
    with pytest.raises(ValueError):
        RoutineBlock("09:00", "17:00", "office", "x", availability="flying")
    with pytest.raises(ValueError):
        RoutineBlock("9am", "17:00", "office", "x")


def test_build_routine_merges_template_character_blocks_and_default_sleep():
    templates = {"resident": {"free_place": "living_room",
                              "blocks": [{"start": "07:15", "end": "08:00", "place": "kitchen",
                                          "activity": "breakfast", "availability": "awake"}]}}
    routine = build_routine({"template": "resident", "blocks": [WORK.to_dict()]}, templates, "bedroom")
    assert [b.activity for b in routine.blocks] == ["sleeping", "breakfast", "at work"]
    assert routine.free_place == "living_room" and routine.home == "bedroom"
    homed = build_routine({"blocks": [{"start": "21:00", "end": "22:00", "place": "home", "activity": "reading"}]},
                          {}, "bedroom")
    assert homed.blocks[-1].place == "bedroom"


def test_overnight_step_puts_everyone_to_bed_then_wakes_them_in_order():
    model = make_model({"ann": "living_room", "ben": "kitchen"}, player_place="terrace")
    with_routine(model, "ann", "girls_bedroom")
    with_routine(model, "ben", "boys_bedroom")
    start = 3 * 60                                    # 22:00
    end = model.world.absolute_minute(1, "08:00")
    result = step_world(model, start, end, scene_present=set())
    assert model.world.where_is("ann") == "girls_bedroom"
    assert model.characters["ann"].availability == "awake"     # woke at ~07:00
    minutes = [t.minute for t in result.transitions]
    assert minutes == sorted(minutes)
    asleep = [t for t in result.transitions if t.availability == "asleep"]
    assert {t.character for t in asleep} == {"ann", "ben"}
    assert model.world.minute == end


def test_anti_vanish_keeps_scene_members_through_short_intervals_only():
    model = make_model({"ann": "kitchen"})
    with_routine(model, "ann", "bedroom", RoutineBlock("19:05", "21:00", "office", "night shift", "busy"), sleep=False)
    step_world(model, 0, 10, scene_present={"ann"})
    assert model.world.where_is("ann") == "kitchen"               # protected mid-conversation
    step_world(model, 10, 90, scene_present={"ann"})
    assert model.world.where_is("ann") == "office"                # long interval: routine wins


def test_hard_blocks_override_anti_vanish():
    model = make_model({"ann": "kitchen"})
    with_routine(model, "ann", "bedroom",
                 RoutineBlock("19:05", "20:00", "clinic", "appointment", "out", hard=True), sleep=False)
    step_world(model, 0, 10, scene_present={"ann"})
    assert model.world.where_is("ann") == "clinic"


def test_leaving_an_away_block_sends_them_to_the_free_place_but_home_blocks_stay():
    model = make_model({"ann": "office"}, player_place="terrace")
    with_routine(model, "ann", "bedroom", RoutineBlock("18:00", "19:30", "office", "at work"), sleep=False,
                 free_place="living_room")
    model.characters["ann"].block = "18:00-19:30@office:at work"
    step_world(model, 0, 60, scene_present=set())
    assert model.world.where_is("ann") == "living_room"
    assert model.characters["ann"].availability == "awake"


def test_characters_without_routines_or_places_never_move():
    model = make_model({"ann": "kitchen"})
    model.characters["ghost"] = type(model.characters["ann"])("ghost", "Ghost")
    result = step_world(model, 0, 600, scene_present=set())
    assert model.world.where_is("ann") == "kitchen" and model.world.where_is("ghost") is None
    assert result.transitions == []


def test_timeline_records_snapshots_for_offscreen_resolution():
    model = make_model({"ann": "kitchen", "ben": "kitchen"}, player_place="terrace")
    result = step_world(model, 0, 60, scene_present=set(), player_asleep=True)
    assert result.timeline[-1][0] == 60
    assert result.timeline[0][1]["ann"] == ("kitchen", "awake")
    assert result.timeline[0][3] is False                         # player asleep
    assert step_world(model, 60, 60, set()).timeline == []
