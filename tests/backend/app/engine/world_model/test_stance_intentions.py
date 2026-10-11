"""BL-100: stances other than `crush` become intentions the holder may act on, one beat a day, and end with the stance."""
import pytest

from backend.app.engine.rules.tracks import Intensity, social_rules
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.agenda import STANCE_INTENTIONS, intentions, next_beat, refresh_agendas
from backend.app.engine.world_model.stances import Stance
from backend.app.engine.world_model.standing import Standing
from backend.app.engine.world_model.turn import BEAT_TEXT
from tests.backend.app.engine.world_model.helpers import make_model

RULES = social_rules(build_story_registry()["six_strangers"]["raw"])
TRACK = RULES.appraisal.track
PLAYER_KINDS = ("resents", "owes", "ex", "distrusts")


def _model(kind, target="player", strength=1.0):
    model = make_model({"holder": "k", "friend": "k"})
    model.standing.bind(RULES.tracks)
    model.stances.add(Stance(kind, "holder", target, strength, "", (), 0))
    return model


def _refresh(model, day=0, **kw):
    refresh_agendas(model, TRACK, day, **kw)


@pytest.mark.parametrize("kind", sorted(STANCE_INTENTIONS))
def test_each_stance_kind_derives_its_own_intention(kind):
    target = "friend" if kind == "protective_of" else "player"
    model = _model(kind, target)
    _refresh(model)
    intent = STANCE_INTENTIONS[kind][0]
    assert [(i.kind, i.target) for i in intentions(model, "holder", 0)] == [(intent, target)]
    assert intent in BEAT_TEXT


@pytest.mark.parametrize("kind", PLAYER_KINDS)
def test_a_player_directed_stance_makes_a_beat_toward_the_player(kind):
    model = _model(kind)
    _refresh(model)
    cid, intention = next_beat(model, {"holder"}, 0)
    assert cid == "holder" and intention.kind == STANCE_INTENTIONS[kind][0]
    text = BEAT_TEXT[intention.kind].format(name="Holder", target="Friend")
    assert text.startswith("Holder")


def test_protectiveness_beats_only_when_the_protected_person_is_present():
    model = _model("protective_of", "friend")
    _refresh(model)
    assert next_beat(model, {"holder"}, 0) is None
    cid, intention = next_beat(model, {"holder", "friend"}, 0)
    assert (cid, intention.kind, intention.target) == ("holder", "defend", "friend")


def test_the_intention_ends_when_the_stance_does():
    model = _model("resents")
    _refresh(model)
    assert intentions(model, "holder", 0)
    model.stances.items.clear()
    _refresh(model, day=1)
    assert intentions(model, "holder", 1) == []


def test_friction_zero_switches_them_off_and_scales_priority():
    off = _model("resents")
    _refresh(off, intensity=Intensity(1.0, 1.0, 0.0))
    assert intentions(off, "holder", 0) == []
    half, full = _model("resents"), _model("resents")
    _refresh(half, intensity=Intensity(1.0, 1.0, 0.5))
    _refresh(full)
    assert intentions(half, "holder", 0)[0].priority == pytest.approx(intentions(full, "holder", 0)[0].priority / 2)


def test_still_one_unsolicited_move_a_person_a_day():
    model = _model("resents")
    _refresh(model)
    model.initiative_last_day["beat:holder"] = 0
    assert next_beat(model, {"holder"}, 0) is None
    assert next_beat(model, {"holder"}, 1) is not None


def test_a_stance_intention_never_displaces_a_pursuit():
    model = _model("resents")
    model.stances.add(Stance("crush", "holder", "player", 1.0, "", (), 0))
    model.standing.standings[("holder", "player", TRACK)] = Standing(value=60.0)
    _refresh(model)
    kinds = {i.kind for i in intentions(model, "holder", 0)}
    assert {"pursue", "confront"} <= kinds
