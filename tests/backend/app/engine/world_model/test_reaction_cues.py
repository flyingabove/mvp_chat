"""Gameplay: a behaviour that lands on a resident is shown to the storyteller as a legible reaction (cause -> effect).

Simulation on Ollama (2026-09-30) showed ~60% of a kind player's turns produced no extractor tag and ~40% of tagged
turns did nothing visible (Arisa's authored taste for "complimentary" is exactly 0), so the player got no feedback
and could not learn what each resident values. These cues say, per turn, how the target took it: warm (they like
it), cool (they dislike it), flat (it does not move them) or stale (they liked it, but the same gesture already
landed today). Grounded in the authored tastes and the standing book; never a number.
"""
from types import SimpleNamespace

from backend.app.engine.extractors.turn_extractor import BehaviorTagUpdate
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.turn import begin_turn, record_behaviors

from tests.backend.app.engine.world_model.helpers import make_model

TERRACE = build_story_registry()["six_strangers"]["raw"]


def _state(model, gender="M"):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=TERRACE,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender=gender, turns=5, outcome=None)


def _act(state, who, tag):
    record_behaviors(state, [BehaviorTagUpdate("player", who, tag)])


MARKERS = ("responds warmly", "reacts coolly", "unmoved by", "stopped landing")


def _cues(model):
    return [note for note in model.pending_notes if any(marker in note for marker in MARKERS)]


def _fresh():
    model = make_model({"arisa": "kitchen", "minori": "kitchen"})
    return model, _state(model)


def test_a_behaviour_the_target_likes_gets_a_warm_cue_naming_who_and_what():
    model, state = _fresh()
    _act(state, "arisa", "supportive_of_goals")
    [cue] = _cues(model)
    assert "Arisa" in cue and "warmly" in cue and "supportive of goals" in cue


def test_a_disliked_behaviour_gets_a_cool_cue():
    model, state = _fresh()
    _act(state, "arisa", "pushy")
    [cue] = _cues(model)
    assert "Arisa" in cue and "coolly" in cue


def test_a_behaviour_that_does_not_move_them_gets_a_flat_cue():
    model, state = _fresh()
    _act(state, "arisa", "complimentary")             # her authored taste for compliments is exactly 0
    [cue] = _cues(model)
    assert "Arisa" in cue and "unmoved" in cue and "no warmth" in cue


def test_the_same_gesture_repeated_the_same_day_goes_stale():
    model, state = _fresh()
    kinds = []
    for _ in range(4):
        model.pending_notes.clear()
        model.turn += 1                                  # each real turn has its own behaviour operation ids
        _act(state, "arisa", "supportive_of_goals")
        kinds.append("stopped landing" if any("stopped landing" in n for n in _cues(model)) else "warm")
    assert kinds[0] == "warm" and "stopped landing" in kinds, kinds
    stale = [n for n in model.pending_notes if "stopped landing" in n]
    assert all("do not say why" in n.lower() for n in stale)


def test_no_cue_when_the_behaviour_is_not_aimed_at_someone_in_the_scene_or_is_not_the_players():
    model = make_model({"arisa": "kitchen", "minori": "garden"})
    state = _state(model)
    _act(state, "minori", "warm")                                     # Minori is in the garden, not here
    model.turn += 1
    record_behaviors(state, [BehaviorTagUpdate("arisa", "minori", "warm")])    # a resident's behaviour, not the player's
    assert _cues(model) == []


def test_at_most_two_cues_per_turn_one_per_person_and_never_a_score():
    model, state = _fresh()
    model.world.move("player", "kitchen")
    record_behaviors(state, [BehaviorTagUpdate("player", "arisa", "supportive_of_goals"),
                             BehaviorTagUpdate("player", "arisa", "warm"),
                             BehaviorTagUpdate("player", "minori", "attentive"),
                             BehaviorTagUpdate("player", "minori", "pushy")])
    cues = _cues(model)
    assert len(cues) == 2 and sum("Arisa" in c for c in cues) == 1 and sum("Minori" in c for c in cues) == 1
    for cue in cues:
        for word in ("standing", "score", "points", "tier", "percent", "+"):
            assert word not in cue.lower(), (word, cue)


def test_the_cue_reaches_the_storyteller_this_turn_and_is_gone_the_next():
    model, state = _fresh()
    _act(state, "arisa", "supportive_of_goals")
    view = begin_turn(state, "I think your plans for the shop are wonderful.", 0)
    assert any("warmly" in line and "Arisa" in line for line in view.must_address), view.must_address
    later = begin_turn(state, "Anyway.", 0)
    assert not any(marker in line for line in later.must_address for marker in MARKERS), "a cue describes one moment only"
