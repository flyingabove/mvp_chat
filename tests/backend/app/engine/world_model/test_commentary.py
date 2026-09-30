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
from backend.app.engine.world_model.social_acts import CONFIRMED, SocialAct, Verdict
from backend.app.engine.world_model.standing import Standing
from backend.app.engine.world_model.turn import begin_turn, end_turn, record_social_act

from tests.backend.app.engine.world_model.helpers import make_model

TERRACE = build_story_registry()["six_strangers"]["raw"]
PANEL = commentary_for(TERRACE)


def _state(model):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=TERRACE,
                           characters={c: SimpleNamespace(name=c.title(), tells=[], meta={}) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender="M", turns=9, outcome=None)


def _confirm_leaving(state, partner="ann"):
    """The player confirmed leaving together (BL-46): the only way to reach the finale turn."""
    model = state.world_model
    model.romance_relationship_partner = partner
    model.pending_verdicts = [Verdict(SocialAct("ask_leave_together", partner), "accept", CONFIRMED)]


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
    _confirm_leaving(state)
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


def test_panelists_never_speak_inside_the_house_scene():
    """Live finale (2026-09-29): the model gave housemates' goodbyes to Reina and Yukiko
    ("Are you going somewhere?") because panelists were listed with the house cast."""
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    _confirm_leaving(state)
    begin_turn(state, "I'm leaving the house alone.", 0)
    prompt = dialogue_prompt(state)
    assert "TV studio" in prompt and "`panel` array" in prompt
    segments = [{"kind": "narration", "text": "You pack."},
                {"kind": "dialogue", "speaker_id": "reina", "speaker_name": "Reina Triendl", "text": "Going somewhere?"},
                {"kind": "narration", "text": "You step out."},
                {"kind": "dialogue", "speaker_id": "yamasato", "speaker_name": "Ryota Yamasato", "text": "Bold exit."},
                {"kind": "dialogue", "speaker_id": "yukiko", "speaker_name": "Yukiko Ehara", "text": "Sincere, though."}]
    end_turn(state, "I'm leaving the house alone.", segments)
    assert segments[1] == {"kind": "narration", "text": "“Going somewhere?”"}
    assert [s.get("speaker_id") for s in segments[3:]] == ["yamasato", "yukiko"], "the closing panel stays"


def test_a_reply_without_the_panel_gets_a_footage_only_fallback():
    """Live finale (2026-09-29): the model wrote the exit scene but no panel."""
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    record_behavior(model, "player", "ann", "boastful", (), "b1")
    _confirm_leaving(state)
    begin_turn(state, "I'm leaving the house alone.", 0)
    assert "MUST end with the studio panel section" in dialogue_prompt(state)
    segments = [{"kind": "narration", "text": "You step out."}]
    end_turn(state, "I'm leaving the house alone.", segments)
    panel = [s for s in segments if s.get("speaker_id") in {"reina", "yamasato", "yukiko"}]
    assert [s["speaker_name"] for s in panel] == ["Reina Triendl", "Ryota Yamasato", "Yukiko Ehara"]
    assert "boastful" in panel[1]["text"], "Yamasato's line cites the footage he disliked"
    assert model.view.panel_fallbacks == 1
    assert not any(word in s["text"].lower() for s in panel for word in ("score", "tier", "standing"))


def test_the_finale_keeps_the_exit_scene_when_the_player_has_walked_out():
    """Live finale: the player moved to the street, a goodbye came from an unidentified voice,
    and the empty-scene gate replaced the whole exit scene with 'no one is here'."""
    from backend.app.engine.dialogue import ground_social_scene
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    _confirm_leaving(state)
    begin_turn(state, "I'm leaving the house alone.", 0)
    model.world.move("player", "street")
    state.location = "Street"
    scene = [{"kind": "narration", "text": "You pull the door shut."},
             {"kind": "dialogue", "speaker_id": None, "text": "Take care!"}]
    grounded = ground_social_scene(scene, state)
    assert grounded[0]["text"] == "You pull the door shut."
    assert grounded[1] == {"kind": "narration", "text": "“Take care!”"}
    assert not any("no one is here" in s["text"] for s in grounded)


def test_on_the_exit_turn_the_people_being_left_can_still_say_goodbye():
    model = make_model({"ann": "kitchen", "ben": "garden"})
    state = _state(model)
    _confirm_leaving(state)
    state.location_id = "street"
    begin_turn(state, "I'm leaving the house alone.", 0)
    assert model.player_place() == "street" and "ann" in model.view.allowed_speakers
    assert "ben" not in model.view.allowed_speakers
    begin_turn(state, "Walking on.", 0)
    assert "ann" not in model.view.allowed_speakers, "only on the exit turn"


def test_the_finale_schema_requires_a_panel_the_model_cannot_skip():
    """BL-42: the model skipped the panel in 5/5 live finales; on finale turns only,
    the strict response schema requires a panel array of panelist lines."""
    from backend.app.engine.dialogue import decode_dialogue_response, dialogue_response_format, finale_turn
    import json as _json
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    begin_turn(state, "Hi.", 0)
    ordinary = dialogue_response_format(state)["json_schema"]["schema"]
    assert "panel" not in ordinary["properties"] and not finale_turn(state)
    _confirm_leaving(state)
    begin_turn(state, "I'm leaving the house alone.", 0)
    schema = dialogue_response_format(state)["json_schema"]["schema"]
    assert "panel" in schema["required"] and finale_turn(state)
    assert schema["properties"]["panel"]["items"]["properties"]["speaker_id"]["enum"] == ["reina", "yamasato", "yukiko"]
    raw = _json.dumps({"segments": [{"kind": "narration", "speaker_id": None, "text": "You go."}],
                       "panel": [{"speaker_id": "yamasato", "text": "Bold."}, {"speaker_id": "ann", "text": "x"}],
                       "state": {"emotion": "calm", "rel_delta": 0}})
    decoded = decode_dialogue_response(raw, state)
    assert decoded.index("You go.") < decoded.index("[SPEAKER:yamasato]Bold.[/SPEAKER]")
    assert "[SPEAKER:ann]x" not in decoded, "only panelists may speak in the panel"


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
