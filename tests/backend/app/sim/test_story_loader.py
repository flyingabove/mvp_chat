"""P-06: a SeasonRunner story built from the authored Terrace file, with no player and no network."""
import pytest

from backend.app.sim.runner import SeasonRunner
from backend.app.sim.story_loader import build_season
from backend.app.sim.writer import FakeWriter


def test_the_authored_house_is_loaded_with_the_player_slot_reserved():
    setup = build_season("six_strangers", "s1")
    model, lifecycle = setup.story.model, setup.story.cast_lifecycle
    assert len(model.characters) == 5 and set(model.characters) == set(setup.cast)
    assert lifecycle.player_slot_group == "women" and setup.story.expected_cast_size == 6
    assert setup.title == "Terrace in the City" and "six-person house" in setup.premise
    genders = [c for c in setup.cast.values()]
    assert all(note.name and note.role for note in genders)
    assert all(model.world.place_of(cid) == "living_room" for cid in model.characters)


def test_the_roster_is_repeatable_for_a_seed_and_varies_between_seeds():
    roster = lambda seed: tuple(sorted(build_season("six_strangers", seed).cast))
    assert roster("same") == roster("same")
    assert len({roster(f"seed-{n}") for n in range(8)}) > 1


def test_a_player_of_the_other_gender_holds_the_other_slot():
    assert build_season("six_strangers", "s1", player_gender="M").story.cast_lifecycle.player_slot_group == "men"


def test_clock_and_place_names_come_from_the_story():
    setup = build_season("six_strangers", "s1")
    assert setup.clock(0) == "Wednesday 15:00" and setup.clock(90) == "Wednesday 16:30"
    assert setup.place("living_room") == setup.place_names.get("living_room") or "living" in setup.place("living_room")
    assert setup.place("some_unnamed_room") == "some unnamed room"
    assert setup.name("nobody") == "nobody"


def test_a_story_that_does_not_exist_is_an_error_not_an_empty_season():
    with pytest.raises(ValueError):
        build_season("no_such_story", "s1")


def test_a_real_house_runs_two_days_on_the_fake_writer_with_no_violations():
    setup = build_season("six_strangers", "s1")
    result = SeasonRunner(setup.story, "s1", FakeWriter(), days=2).run()
    assert result.completed_days == 2 and result.all_violations == [] and result.calls_used > 0
    assert all(scene.text for day in result.days for scene in day.scenes)
