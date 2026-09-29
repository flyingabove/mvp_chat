"""A due promise is raised once, then left to ordinary conversation history (2026-09-29 tea loop)."""
from types import SimpleNamespace

from backend.app.engine.world_model.commitments import add_commitment, due_commitments, mark_reminded
from backend.app.engine.world_model.memory import Memory
from backend.app.engine.world_model.model import PLAYER
from backend.app.engine.world_model.turn import begin_turn

from tests.backend.app.engine.world_model.helpers import make_model


def _state(model):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul",
                           story_cfg={"world_model": {"enabled": True}}, characters=model.characters,
                           cast_lifecycle=None, character_graph=None)


def _lines(model, needle):
    return [line for line in model.view.must_address if needle in line]


def test_an_npc_promise_is_raised_once_then_never_again():
    model = make_model({"ann": "kitchen"})
    add_commitment(model, "ann", PLAYER, "make you tea", due=0, minute=0)
    state = _state(model)
    begin_turn(state, "Hi.", 0)
    assert len(_lines(model, "promised earlier")) == 1
    for _ in range(5):
        begin_turn(state, "Still here.", 0)
        assert _lines(model, "promised earlier") == []


def test_a_player_promise_is_raised_once_then_never_again():
    model = make_model({"ann": "kitchen"})
    add_commitment(model, PLAYER, "ann", "make her tea", due=0, minute=0)
    state = _state(model)
    begin_turn(state, "Hi.", 0)
    assert len(_lines(model, "The player promised")) == 1
    for _ in range(3):
        begin_turn(state, "Later.", 0)
        assert _lines(model, "The player promised") == []


def test_marking_one_side_marks_the_counterparts_copy():
    model = make_model({"ann": "kitchen"})
    own, other = add_commitment(model, "ann", PLAYER, "make you tea", due=0, minute=0)
    mark_reminded(model, own)
    assert own.reminded and other.reminded
    assert due_commitments(model, 0) == [] and due_commitments(model, 0, owner=PLAYER) == []


def test_a_reminded_promise_stays_open_for_the_judge_and_survives_a_save():
    model = make_model({"ann": "kitchen"})
    own, _ = add_commitment(model, "ann", PLAYER, "make you tea", due=0, minute=0)
    mark_reminded(model, own)
    assert own in model.memories.open_promises("ann")          # reminding does not close it
    assert Memory.from_dict(own.to_dict()).reminded is True
    assert Memory.from_dict({**own.to_dict(), "reminded": None}).reminded is False
