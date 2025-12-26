import json

from backend.app.engine.state import (
    init_state,
    apply_state_tag,
    extract_state_tag,
    CharacterState,
)


def test_init_state_defaults():
    st = init_state()
    assert st.minute >= 0
    assert st.turns == 0
    assert st.over is False


def test_apply_state_tag_clamps_relationship_and_updates_main_character():
    st = init_state()
    st.characters["IU"] = CharacterState(key="IU", name="IU", role="ghost")
    st.main_character_id = "IU"

    apply_state_tag(st, {"iu_emotion": "soft", "rel_delta": 1})
    assert st.iu_emotion == "soft"
    assert st.relationship == 1
    assert st.main_character.emotion == "soft"
    assert st.main_character.relationship == 1

    # clamp rel_delta to [-1, 1]
    apply_state_tag(st, {"iu_emotion": "wary", "rel_delta": 999})
    assert st.relationship == 2


def test_extract_state_tag_round_trip_and_strip():
    tag = {"iu_emotion": "wary", "rel_delta": 0}
    reply = "hello\n[[STATE]]" + json.dumps(tag) + "[[/STATE]]\n"
    clean, parsed = extract_state_tag(reply)
    assert "[[STATE]]" not in clean
    assert parsed == tag


def test_extract_state_tag_returns_none_on_invalid_json():
    reply = "oops [[STATE]]{not json}[[/STATE]]"
    clean, parsed = extract_state_tag(reply)
    assert parsed is None
    assert clean == reply