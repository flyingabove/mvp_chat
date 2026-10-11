"""The Drama Theatre: camera, nudges, skips, continuity prompts, caps and persistence (BL-86, P-13)."""
import json

import pytest

from backend.app.sim.theatre import (
    Command, Gathering, NothingHappens, Theatre, TheatreCapReached, cluster, feeling_words, parse_command, start_theatre)
from backend.app.sim.writer import FakeWriter
from backend.app.engine.world_model.offscreen import Encounter


class Recorder(FakeWriter):
    """FakeWriter that keeps every prompt it was given."""


def _theatre(tmp_path=None, cap=300, seed="t1", writer=None):
    return start_theatre("six_strangers", seed, lambda setup, c: writer or Recorder(), session_id="s1", call_cap=cap,
                         log_dir=tmp_path)


NAMES = {"makoto": "Makoto Hasegawa", "yuto": "Yuto Handa"}


# ---------------------------------------------------------------- the typed line
@pytest.mark.parametrize("text, kind, minutes, clock", [
    ("skip to evening", "skip", 0, "19:00"),
    ("skip to the next morning", "skip", 0, "08:00"),
    ("Skip 3 hours", "skip", 180, ""),
    ("skip an hour", "skip", 60, ""),
    ("/skip 2 days", "skip", 2880, ""),
    ("skip a day", "skip", 1440, ""),
    ("next day", "skip", 1440, ""),
    ("tomorrow", "skip", 1440, ""),
    ("skip to 9pm", "skip", 0, "21:00"),
    ("skip until 07:30", "skip", 0, "07:30"),
    ("skip to bedtime", "skip", 0, "23:00"),
])
def test_skip_commands_are_understood(text, kind, minutes, clock):
    command = parse_command(text, NAMES)
    assert (command.kind, command.minutes, command.clock) == (kind, minutes, clock)


def test_plain_words_are_a_nudge_a_whisper_names_one_resident_and_next_is_next():
    assert parse_command("Makoto finds a letter", NAMES) == Command("nudge", "Makoto finds a letter")
    assert parse_command("@yuto pick a fight", NAMES) == Command("nudge", "pick a fight", to="yuto")
    assert parse_command("@nobody hi there", NAMES).to == ""
    assert parse_command("next", NAMES).kind == "next" and parse_command("skip", NAMES).kind == "next"
    assert parse_command("skip the drama please", NAMES).kind == "nudge", "not a time: the admin's words, not a skip"
    assert len(parse_command("x" * 900, NAMES).text) <= 400


# ---------------------------------------------------------------- the camera
def test_a_full_house_of_six_with_private_aims_and_scenes_are_group_scenes():
    theatre = _theatre()
    state = theatre.state()
    assert len(state["cast"]) == 6 and all(c["aim"].startswith("private aim") for c in state["cast"])
    beat = theatre.step()
    assert beat["type"] == "scene" and len(beat["people"]) >= 2 and beat["clock"] and beat["place"]
    prompt = theatre.writer.calls[-1]
    assert prompt.count("Present:") == 1 and all(p["id"] in prompt for p in beat["people"])
    assert "private aim" in prompt, "each scene brings the people's own aims"


def test_cluster_merges_pairs_in_one_place_into_one_gathering():
    pairs = [Encounter("a", "b", "kitchen", 10, 60), Encounter("b", "c", "kitchen", 20, 40),
             Encounter("a", "c", "kitchen", 20, 30), Encounter("d", "e", "garden", 5, 45)]
    groups = {g.place: g for g in cluster(pairs)}
    assert groups["kitchen"].people == ("a", "b", "c") and groups["kitchen"].minute == 10 and groups["kitchen"].duration == 60
    assert groups["garden"].people == ("d", "e")


def test_the_camera_prefers_people_who_have_been_off_screen():
    theatre = _theatre()
    theatre.beats = [{"type": "scene", "people": []}] * 6
    old, fresh = Gathering("a", "b", "x", 0, 60, ("a", "b")), Gathering("c", "d", "y", 0, 60, ("c", "d"))
    theatre.last_scene_step = {"a": 6, "b": 6, "c": 0, "d": 0}
    assert theatre._interest(fresh) > theatre._interest(old)


def test_a_scene_is_committed_with_everyone_present_and_stays_grounded():
    theatre = _theatre()
    beat = theatre.step()
    model = theatre.model
    event = [e for e in model.world.events if e.kind == "scene"][-1]
    assert set(event.participants) == {p["id"] for p in beat["people"]}
    assert beat["rejections"] == []
    assert theatre.runner._commit_scene(Gathering("a", "b", "p", 0, 60, ("makoto", "yuto", "zed")),
                                        type("U", (), {"summary": "s", "relationship_deltas": (
                                            type("D", (), {"a": "makoto", "b": "zed", "trust_delta": .1, "affection_delta": 0,
                                                           "suspicion_delta": 0, "fear_delta": 0})(),),
                                             "movements": ()})()) == [], "zed was in the scene: grounded"


# ---------------------------------------------------------------- nudges
def test_a_nudge_reaches_exactly_the_next_scene_and_is_then_spent():
    theatre = _theatre()
    theatre.say("the budget argument boils over")
    assert [n["text"] for n in theatre.state()["nudges"]] == ["the budget argument boils over"]
    first = theatre.step()
    assert "the budget argument boils over" in theatre.writer.calls[-1] and first["nudged"] == ["the budget argument boils over"]
    assert theatre.state()["nudges"] == []
    theatre.step()
    assert "budget argument" not in theatre.writer.calls[-1]


def test_a_whisper_reaches_only_scenes_with_that_resident_and_is_kept_until_then():
    theatre = _theatre()
    theatre.nudge("you are sure Yuto is lying", to="makoto")
    gathering = Gathering("a", "b", "p", 0, 60, ("uchi", "yuto"))
    assert "you are sure" not in theatre._prompt(gathering, theatre.nudges)
    gathering = Gathering("a", "b", "p", 0, 60, ("makoto", "yuto"))
    text = theatre._prompt(gathering, theatre.nudges)
    assert "only Makoto Hasegawa feels" in text and "you are sure Yuto is lying" in text


def test_the_camera_leans_toward_the_resident_a_nudge_names():
    theatre = _theatre()
    theatre.nudge("Makoto gets bad news")
    named = Gathering("a", "b", "p", 0, 60, ("makoto", "yuto"))
    other = Gathering("a", "b", "q", 0, 60, ("uchi", "mizuki"))
    assert theatre._interest(named) > theatre._interest(other)


def test_an_empty_nudge_is_refused():
    with pytest.raises(ValueError):
        _theatre().nudge("   ")


# ---------------------------------------------------------------- skipping time
def test_skip_moves_the_clock_without_writing_and_lands_on_the_requested_time():
    theatre = _theatre()
    before = theatre.minute
    beat = theatre.skip(clock="19:00")
    assert theatre.clock().endswith("19:00") and theatre.minute > before and theatre.calls() == 0
    assert beat["type"] == "skip" and "19:00" in beat["text"] and set(beat["place_names"]) == {c["name"] for c in theatre.state()["cast"]}
    assert not [e for e in theatre.model.world.events if e.kind == "scene"], "nothing was written"
    again = theatre.skip(minutes=180)
    assert theatre.clock().endswith("22:00") and again["minute"] == theatre.minute


def test_skipping_to_a_time_that_has_passed_goes_to_the_next_day_and_zero_is_refused():
    theatre = _theatre()
    theatre.skip(clock="19:00")
    day = theatre.clock().split()[0]
    theatre.skip(clock="08:00")
    assert theatre.clock().endswith("08:00") and theatre.clock().split()[0] != day
    with pytest.raises(ValueError, match="nothing to skip"):
        theatre.skip(minutes=-5, clock="")


def test_a_skip_leaves_meanwhile_lines_for_gatherings_it_crossed():
    theatre = _theatre()
    beat = theatre.skip(minutes=6 * 60)
    assert beat["also"] and all("were in the" in line for line in beat["also"])


def test_say_runs_a_skip_or_queues_a_nudge():
    theatre = _theatre()
    assert theatre.say("skip to evening")[0]["type"] == "skip"
    assert theatre.say("something happens")[0]["type"] == "nudge"
    assert theatre.say("next") == []


# ---------------------------------------------------------------- continuity, caps, failure, persistence
def test_later_scenes_are_told_what_happened_before_to_the_same_people():
    theatre = _theatre()
    first = theatre.step()
    theatre.pending = None
    gathering = Gathering("a", "b", first["place"], 0, 60, tuple(p["id"] for p in first["people"]))
    prompt = theatre._prompt(gathering, [])
    assert "Earlier (build on this" in prompt and first["summary"] in prompt


def test_feelings_reach_the_prompt_in_plain_words():
    assert feeling_words({"affection": 0.4}) == "is fond of"
    assert feeling_words({"trust": -0.3, "suspicion": 0.4}) == "distrusts and is suspicious of"
    assert feeling_words({"affection": 0.05}) == ""
    theatre = _theatre()
    theatre.setup.story.relationships.adjust("makoto", "yuto", affection_delta=0.5)
    prompt = theatre._prompt(Gathering("a", "b", "p", 0, 60, ("makoto", "yuto")), [])
    assert "Makoto Hasegawa is fond of Yuto Handa" in prompt


def test_the_call_cap_stops_a_scene_before_it_is_written():
    theatre = _theatre(cap=2)
    theatre.step()
    with pytest.raises(TheatreCapReached):
        theatre.step()
    assert theatre.calls() == 1, "the refused scene made no model call"


def test_a_failed_write_keeps_the_gathering_and_the_nudge_for_the_retry():
    class Flaky(Recorder):
        fail = True

        def write_scene(self, prompt):
            if self.fail:
                self.fail = False
                raise RuntimeError("model down")
            return super().write_scene(prompt)

    theatre = _theatre(writer=Flaky())
    theatre.nudge("a surprise visitor")
    with pytest.raises(RuntimeError):
        theatre.step()
    assert theatre.pending is not None and [n["text"] for n in theatre.nudges] == ["a surprise visitor"]
    where = theatre.pending
    beat = theatre.step()
    assert set(p["id"] for p in beat["people"]) == set(where.people) and beat["nudged"] == ["a surprise visitor"]


def test_every_beat_is_logged_so_a_session_can_be_replayed(tmp_path):
    theatre = _theatre(tmp_path)
    theatre.say("a nudge")
    theatre.step()
    theatre.skip(minutes=60)
    rows = [json.loads(line) for line in (tmp_path / "s1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["type"] for r in rows] == ["nudge", "scene", "skip"] and [r["n"] for r in rows] == [1, 2, 3]
    assert theatre.state(since=1)["beats"][0]["n"] == 2 and theatre.state()["last"] == 3


def test_the_same_seed_gives_the_same_house_and_first_scene():
    a, b = _theatre(seed="same"), _theatre(seed="same")
    assert [c["id"] for c in a.state()["cast"]] == [c["id"] for c in b.state()["cast"]]
    assert a.step()["place"] == b.step()["place"]


def test_a_day_with_nobody_together_says_so(monkeypatch):
    theatre = _theatre()
    monkeypatch.setattr("backend.app.sim.theatre.find_encounters", lambda step: [])
    with pytest.raises(NothingHappens):
        theatre.step()
