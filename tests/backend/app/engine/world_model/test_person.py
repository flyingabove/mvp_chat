"""BL-39 phase B: the character aggregate composes existing stores without copies."""
from types import SimpleNamespace

import pytest

from backend.app.engine.character_graph import CharacterGraph
from backend.app.engine.world_model.agreements import propose
from backend.app.engine.world_model.epistemics import assert_claim, observe_event, transmit
from backend.app.engine.world_model.person import Cast
from backend.app.engine.world_model.turn import begin_turn, record_questions, warmth_fn
from backend.app.engine.extractors.turn_extractor import QuestionAsked

from tests.backend.app.engine.world_model.helpers import make_model


def _graph():
    return CharacterGraph.from_dict({"edges": [
        {"from_id": "ann", "to_id": "player", "state": {"trust": 0.4, "affection": 0.2}},
        {"from_id": "ann", "to_id": "ben", "state": {"suspicion": 0.3}},
        {"from_id": "ben", "to_id": "ann", "state": {"affection": 0.5}},
    ]})


def _state(model, graph=None):
    profiles = {cid: SimpleNamespace(name=f"{cid.title()} Authored") for cid in model.characters}
    return SimpleNamespace(world_model=model, character_graph=graph if graph is not None else _graph(),
                           characters=profiles, minute=0,
                           location_id="kitchen", player_name="Paul", story_cfg={"world_model": {"enabled": True}},
                           cast_lifecycle=None)


def test_bond_feelings_are_the_graph_edge_state_itself():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model)
    bond = Cast(state).get("ann").heart.bond("player")
    edge = state.character_graph.get_edge("ann", "player")
    assert bond.feelings is edge.state, "one stored copy of every feeling"
    state.character_graph.update_edge("ann", "player", trust_delta=0.1)
    assert bond.as_dict()["trust"] == pytest.approx(0.5)
    assert Cast(state).get("ann").heart.bond("cat") is None


def test_hearts_are_directional_and_only_list_own_bonds():
    state = _state(make_model({"ann": "kitchen", "ben": "kitchen"}))
    ann, ben = Cast(state).get("ann"), Cast(state).get("ben")
    assert sorted(b.target for b in ann.heart.bonds()) == ["ben", "player"]
    assert [b.target for b in ben.heart.bonds()] == ["ann"]
    assert ben.heart.bond("ann").as_dict()["affection"] == 0.5
    assert ann.heart.bond("ben").as_dict()["affection"] == 0.0


def test_scoped_views_never_show_another_persons_private_state():
    model = make_model({"ann": "kitchen", "ben": "kitchen", "cat": "garden"})
    state = _state(model)
    model.memories.add("ann", "my secret diary", "authored", 0, private=True)
    model.memories.add("ben", "I saw a fox", "witnessed", 0)
    event = model.world.add_event(0, "kitchen", ("ann",), "@ann dropped a cup")
    observe_event(model.epistemics, "ann", event.id, "participant", event.truth, 0)
    claim = assert_claim(model.epistemics, "ben", "the fridge is broken", 0)
    transmit(model.epistemics, claim.id, "ben", "cat", 1)
    propose(model.agreements, "ann", "player", "cook dinner", 60, 0)

    cast = Cast(state)
    ann, ben, cat = cast.get("ann"), cast.get("ben"), cast.get("cat")
    assert [m.text for m in ann.memories()] == ["my secret diary"]
    assert [m.text for m in ben.memories()] == ["I saw a fox"]
    assert [o.owner for o in ann.observations()] == ["ann"] and cat.observations() == []
    assert {b.owner for b in cat.beliefs()} == {"cat"} and ann.beliefs() == []
    assert len(ann.commitments()) == 1 and ben.commitments() == []


def test_profile_body_and_player_resolve_from_the_same_state():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    cast = Cast(state)
    ann = cast.get("ann")
    assert ann.body is model.characters["ann"] and ann.profile is state.characters["ann"]
    assert ann.name == "Ann"
    player = cast.player()
    assert player.is_player and player.name == "Paul" and player.body is None and player.knows_player_name()
    with pytest.raises(KeyError):
        cast.get("stranger")
    assert cast.ids() == ["ann"]


def test_per_person_conversation_and_encounter_views():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model)
    record_questions(state, [QuestionAsked("ann", "Where were you?")], [], message="Ann, where were you? I'm Paul.")
    begin_turn(state, "Ann, where were you? I'm Paul.", 0)
    ann, ben = Cast(state).get("ann"), Cast(state).get("ben")
    assert [q.text for q in ann.owed_questions()] == ["Where were you?"] and ben.owed_questions() == []
    assert ann.knows_player_name() and ann.last_with_player() == 1


def test_speaker_warmth_reads_through_the_heart_unchanged():
    state = _state(make_model({"ann": "kitchen", "ben": "kitchen"}))
    warmth = warmth_fn(state)
    assert warmth("ann") == pytest.approx(0.3)
    assert warmth("ben") == 0.0, "no edge toward the player"
    assert warmth("nobody") == 0.0
