"""BL-77: the authored first meeting reads as two strangers on camera, not as friends (owner rules 2026-09-30).

Every possible greeter has an authored cue and line that: introduce by surname with a bow, never use the player's
name (they have not given it), never claim shared history or warmth, and never narrate attraction. Show, don't tell.
"""
import json
import re
from pathlib import Path

import pytest

STORY = Path(__file__).resolve().parents[4] / "backend/app/stories/7_six_strangers/six_strangers_story.json"
CFG = json.loads(STORY.read_text(encoding="utf-8"))
GREETERS = CFG["opening"]["first_resident"]
KEYS = [c["key"] for c in CFG["characters"]]

WARMTH = re.compile(r"\b(friend\w*|glad|happy|wonderful|lovely|great to meet|nice to meet|so good|beautiful|"
                    r"blush\w*|smil\w* warmly|warm\w*|gaze|we're|we are|us two|our)\b", re.I)


def test_every_possible_greeter_is_authored():
    assert set(GREETERS) == set(KEYS)


@pytest.mark.parametrize("key", KEYS)
def test_a_greeter_introduces_like_a_stranger_on_camera(key):
    cue, line = GREETERS[key]["cue"], GREETERS[key]["line"]
    name = next(c["name"] for c in CFG["characters"] if c["key"] == key)
    assert "hajimemashite" in line.lower(), "the formal first-meeting phrase is the show's ritual"
    surname_or_nick = [part for part in re.findall(r"[A-Za-z]+", name) if part.lower() in line.lower()]
    assert surname_or_nick, f"{key} introduces themselves by name"
    assert not WARMTH.search(cue + " " + line), f"{key} is warm or familiar with someone they just met"
    assert "{{" not in line and "Sam" not in line and "Paul" not in line, "the player's name is not known yet"


def test_greeters_do_not_all_share_one_template():
    lines = [g["line"] for g in GREETERS.values()]
    assert len(set(lines)) == len(lines)
    endings = {line.split(".")[-2].strip() if line.count(".") > 1 else line for line in lines}
    assert len(endings) > 12, "the second sentence differs person to person"


def test_the_opening_beats_state_the_show_subtext_once_and_name_no_feelings():
    texts = " ".join(s["text"] for s in CFG["opening"]["segments"])
    assert "romance show" in texts and "camera" in texts
    assert "{{GREETER_CUE}}" in texts and "{{GREETER_LINE}}" in texts
    assert not WARMTH.search(re.sub(r"\{\{.*?\}\}", "", texts))


ARRIVALS = CFG["opening"]["arrival_sequence"]


def test_every_possible_arrival_is_authored_and_nobody_is_named_before_they_speak():
    assert set(ARRIVALS["entrance_cues"]) == set(ARRIVALS["entrance_lines"]) == set(KEYS)
    for key in KEYS:
        name = next(c["name"] for c in CFG["characters"] if c["key"] == key)
        cue = ARRIVALS["entrance_cues"][key]
        assert not any(part in cue for part in re.findall(r"[A-Za-z]{3,}", name)), f"{key}'s cue names them"


@pytest.mark.parametrize("key", KEYS)
def test_an_arrival_introduces_like_a_stranger_on_camera(key):
    cue, line = ARRIVALS["entrance_cues"][key], ARRIVALS["entrance_lines"][key]
    assert "hajimemashite" in line.lower()
    assert not WARMTH.search(cue + " " + line), f"{key} is warm or familiar with strangers"
    assert "{{" not in line and "Sam" not in line and "Paul" not in line


def test_arrivals_are_spaced_so_each_pair_of_strangers_gets_a_few_exchanges():
    minutes = ARRIVALS["offset_minutes"]
    assert len(minutes) == 4 and all(b - a >= 8 for a, b in zip(minutes, minutes[1:]))


def test_the_type_round_has_a_phrase_for_every_strong_taste_in_the_cast():
    ritual = CFG["opening"]["group_ritual"]
    for key, person in CFG["personalities"].items():
        for tag, weight in person.get("tastes", {}).items():
            if weight > 0:
                assert tag in ritual["likes"], f"{key}'s liking for {tag} has no phrase"
            if weight <= -2.0:
                assert tag in ritual["dislikes"], f"{key}'s dislike of {tag} has no phrase"
