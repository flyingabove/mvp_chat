"""BL-39 phase I: the studio panel knows only the footage and speaks in the finale turn."""
from types import SimpleNamespace

import pytest

from backend.app.engine.dialogue import _contract_cast_ids, dialogue_prompt, present_dialogue
from backend.app.engine.extractors.turn_extractor import SocialActUpdate
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.appraisal import record_behavior
from backend.app.engine.world_model.commentary import (
    commentary_for, dossier, finale_directive, outline, scrub_panel, stances,
)
from backend.app.engine.world_model.standing import Standing
from backend.app.engine.world_model.turn import begin_turn, end_turn, record_social_act

from tests.backend.app.engine.world_model.helpers import make_model

TERRACE = build_story_registry()["six_strangers"]["raw"]
PANEL = commentary_for(TERRACE)


def _state(model):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=TERRACE,
                           characters={c: SimpleNamespace(name=c.title(), tells=[], meta={}) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender="M", turns=9, outcome=None)


def _footage_model():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    record_behavior(model, "player", "ann", "flirtatious", ("ben",), "b1")
    record_behavior(model, "player", "ben", "boastful", ("ann",), "b2")
    model.world.move("player", "shared_bathroom")
    record_behavior(model, "player", "ann", "rude", (), "b3")
    model.world.move("player", "kitchen")
    record_behavior(model, "ann", "ben", "warm", (), "b4")
    model.world.add_event(0, "garden", ("ann", "ben"), "@ann and @ben talked for a while", kind="offscreen")
    model.standing.standings[("ann", "player", "romance")] = Standing(value=55)
    model.memories.add("ann", "I secretly like Paul", "authored", 0, private=True)
    return model


def test_the_dossier_is_filmed_player_footage_only():
    texts = [item.text for item in dossier(_footage_model(), PANEL)]
    assert texts == ["Paul was flirtatious toward Ann", "Paul was boastful toward Ben"]
    joined = " ".join(texts)
    assert "rude" not in joined, "unfilmed bathroom"
    assert "talked for a while" not in joined and "Ann was warm" not in joined, "no events without the player"
    assert "secretly" not in joined and "55" not in joined, "no memories or standings"


def test_panelists_disagree_through_their_own_tastes():
    footage = dossier(_footage_model(), PANEL)
    leaning = {pid: s[0] for pid, s in stances(PANEL, footage).items()}
    assert leaning["reina"] == "warm" and leaning["yamasato"] == "critical"
    assert stances(PANEL, footage)["yamasato"][2] == "Paul was boastful toward Ben"


def test_the_outline_keeps_acts_and_time_order():
    model = _footage_model()
    model.world.add_event(5, "kitchen", ("player", "ann"), "@ann declined @player's confession",
                          kind="confess_declined", visibility="public")
    moments = outline(PANEL, dossier(model, PANEL))
    assert any("declined" in m.text for m in moments)
    assert [m.minute for m in moments] == sorted(m.minute for m in moments)
    directive = finale_directive(PANEL, dossier(model, PANEL))
    assert "Reina Triendl" in directive and "never their worth" in directive and "score" in directive


def test_the_finale_turn_lets_panelists_speak_and_ordinary_turns_do_not():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    begin_turn(state, "Hi.", 0)
    assert model.view.panel_speakers == {} and "reina" not in _contract_cast_ids(state)
    record_social_act(state, SocialActUpdate("leave_alone"))
    begin_turn(state, "I'm leaving the house alone.", 0)
    assert set(model.view.panel_speakers) == {"reina", "yamasato", "yukiko"}
    assert {"reina", "yamasato", "yukiko"} <= set(model.view.allowed_speakers)
    assert any("THE STUDIO PANEL" in line for line in model.view.must_address)
    assert "Ryota Yamasato" in dialogue_prompt(state)
    _, segments = present_dialogue("[SPEAKER:yamasato]Bold exit.[/SPEAKER]", state)
    assert segments[0]["speaker_id"] == "yamasato" and segments[0]["speaker_name"] == "Ryota Yamasato"
    leaked = [dict(segments[0]), {"kind": "dialogue", "speaker_id": "reina", "text": "His romance score was low."}]
    end_turn(state, "I'm leaving the house alone.", leaked)
    assert [s["text"] for s in leaked] == ["Bold exit."], "internal mechanics never reach the screen"


def test_the_director_trigger_also_opens_the_finale():
    model = make_model({"ann": "kitchen"})
    model.counters["couples_left"] = 3
    begin_turn(_state(model), "Hi.", 0)
    assert model.view.panel_speakers and any("cut from the show" in l for l in model.view.must_address)


def test_scrub_only_touches_panel_lines():
    segments = [{"kind": "dialogue", "speaker_id": "ann", "text": "What a score!"},
                {"kind": "dialogue", "speaker_id": "reina", "text": "Nice tier."}]
    assert scrub_panel(segments, PANEL) == 1 and segments[0]["speaker_id"] == "ann"


def test_commentary_config_validates():
    assert commentary_for({}) is None
    for bad in ({"panelists": []}, {"panelists": [{"id": "x"}]},
                {"panelists": [{"id": "x", "name": "X"}, {"id": "x", "name": "Y"}]}):
        with pytest.raises(ValueError):
            commentary_for({"commentary": bad})
