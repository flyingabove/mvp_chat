from backend.app.engine.gameplay import (
    word_count,
    sanitize_location,
    manifest_mode,
    advance_time,
    confession_detected,
)
from backend.app.engine.state import init_state


def test_word_count_and_sanitize_location():
    assert word_count("") == 0
    assert word_count("a   b c") == 3
    assert sanitize_location("<b>Room</b>\n\n302") == "Room 302"


def test_manifest_mode_defaults_and_inside_apartment():
    st = init_state()
    st.story_cfg = {}
    st.location = "Nonhyeon-dong officetel"
    assert manifest_mode(st) == "materialize"

    st.location = "Outside Park"
    assert manifest_mode(st) == "whisper"


def test_advance_time_increments_and_moves_location():
    st = init_state()
    st.story_cfg = {"time": {"mins_per_word": 0.0, "base_turn_mins": 1, "travel_mins": 10}}

    advance_time(st, "hello")
    assert st.minute == 1

    advance_time(st, "go to Cafe")
    assert st.location.lower() == "cafe"
    # base + travel
    assert st.minute == 1 + 1 + 10


def test_advance_time_does_not_move_on_natural_language_question():
    st = init_state()
    st.story_cfg = {"time": {"mins_per_word": 0.0, "base_turn_mins": 1, "travel_mins": 10}}
    st.location = "IU’s Apartment"
    st.minute = 0

    # Should NOT be interpreted as a movement command.
    advance_time(st, "Can we go to your old workplace?")
    assert st.location == "IU’s Apartment"
    assert st.minute == 1


def test_confession_detected_with_default_patterns():
    st = init_state()
    st.story_cfg = {}
    assert confession_detected("I am the mastermind", st) is True
    assert confession_detected("just chatting", st) is False