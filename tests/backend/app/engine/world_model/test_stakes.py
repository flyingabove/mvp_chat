"""Motivated testimony (BL-83, first slice): people with a stake in someone speak about them in their own interest.

Generic, any story with agendas. Nobody is a neutral narrator: a rival who wants Cat may play down Cat's interest in
the player or play up a flaw; they never admit it and never state what Cat privately feels as fact. The engine's truth
is untouched, only the speaker's private motive is passed to the storyteller. Candor and strategy shape how far they go.
"""
from types import SimpleNamespace

from backend.app.engine.world_model.intent import Intention
from backend.app.engine.world_model.turn import begin_turn

from tests.backend.app.engine.world_model.helpers import make_model

CFG = {"characters": [{"key": k} for k in ("ann", "ben", "cat")], "personalities": {
    "ann": {"type": "ENFP", "strategy": "scheming"}, "ben": {"type": "ISTJ"}}}


def _state(model, cfg=CFG):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=cfg,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender="M", turns=5, outcome=None)


def _notes(model):
    return [line for line in model.view.must_address if "personal stake" in line]


def _world(**places):
    model = make_model(places or {"ann": "kitchen", "ben": "kitchen", "cat": "living_room"})
    model.agendas["ann"] = [Intention("pursue", "cat", 0.5, "has their eye on them", 99)]
    return model


def test_someone_pursuing_cat_is_told_they_have_a_stake_when_the_player_brings_cat_up():
    model = _world()
    begin_turn(_state(model), "What do you think of Cat?", 0)
    [note] = _notes(model)
    assert note.startswith("Ann has a personal stake in Cat")
    assert "in their own interest" in note and "never admits" in note
    assert "never state" in note and "privately feels" in note, "never a fact about someone's private feelings"


def test_no_note_when_cat_is_not_mentioned_or_nobody_has_a_stake():
    model = _world()
    begin_turn(_state(model), "How was your day?", 0)
    assert _notes(model) == []
    begin_turn(_state(_world(ann="kitchen", cat="living_room")), "What about Ben?", 0)
    plain = _world()
    plain.agendas = {}
    begin_turn(_state(plain), "What do you think of Cat?", 0)
    assert _notes(plain) == []


def test_a_neutral_bystander_gets_no_note_and_one_cannot_have_a_stake_in_themselves():
    model = _world()
    begin_turn(_state(model), "What do you think of Cat? And you, Ann?", 0)
    assert all("Ben has" not in line for line in _notes(model))
    solo = _world(ann="kitchen", cat="kitchen")
    solo.agendas["cat"] = [Intention("pursue", "cat", 0.5, "x", 99)]
    begin_turn(_state(solo), "Tell me about Cat", 0)
    assert all("Cat has a personal stake in Cat" not in line for line in _notes(solo))


def test_strategy_and_candor_shape_how_far_they_go():
    model = _world()
    begin_turn(_state(model), "What do you think of Cat?", 0)
    assert "steers the conversation on purpose" in _notes(model)[0], "a schemer steers deliberately"
    candid = _world()
    candid.agendas["ann"] = [Intention("pursue", "cat", 0.5, "x", 99)]
    cfg = {"characters": CFG["characters"], "personalities": {"ann": {"type": "ISTJ"}}}
    begin_turn(_state(candid, cfg), "What do you think of Cat?", 0)
    note = _notes(candid)[0]
    assert "would rather withhold than say something false" in note and "steers" not in note


def test_a_person_pursuing_the_player_has_a_stake_in_how_the_player_sees_everyone_else():
    model = make_model({"ann": "kitchen", "cat": "living_room"})
    model.agendas["ann"] = [Intention("pursue", "player", 0.6, "drawn to them", 99)]
    begin_turn(_state(model), "Is Cat seeing anyone?", 0)
    assert any(line.startswith("Ann has a personal stake in Cat") for line in _notes(model))


def test_at_most_two_notes_a_turn():
    model = make_model({"ann": "kitchen", "ben": "kitchen", "dan": "kitchen", "cat": "living_room"})
    for who in ("ann", "ben", "dan"):
        model.agendas[who] = [Intention("pursue", "cat", 0.5, "x", 99)]
    cfg = {"characters": [{"key": k} for k in ("ann", "ben", "dan", "cat")]}
    begin_turn(_state(model, cfg), "What do you all think of Cat?", 0)
    assert len(_notes(model)) == 2
