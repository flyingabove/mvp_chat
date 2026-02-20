from unittest.mock import Mock, MagicMock, patch
from backend.app.engine.gameplay import (
    word_count,
    sanitize_location,
    manifest_mode,
    advance_time,
    win_condition_detected,
)
from backend.app.engine.state import init_state


def test_word_count_and_sanitize_location():
    assert word_count("") == 0
    assert word_count("a   b c") == 3
    assert sanitize_location("<b>Room</b>\n\n302") == "Room 302"


def test_manifest_mode_defaults_and_inside_apartment():
    st = init_state()
    # With manifestation rules from story config
    st.story_cfg = {"rules": {"manifestation": {"apartment_location_contains": ["officetel", "studio"]}}}
    st.location = "Nonhyeon-dong officetel"
    assert manifest_mode(st) == "materialize"

    st.location = "Outside Park"
    assert manifest_mode(st) == "whisper"

    # Without rules (empty story_cfg), always materialize as safe default
    st2 = init_state()
    st2.story_cfg = {}
    st2.location = "Anywhere"
    assert manifest_mode(st2) == "materialize"


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


def test_win_condition_detected_with_config_patterns():
    st = init_state()
    # No win_detection config → always False
    st.story_cfg = {}
    assert win_condition_detected("I am the mastermind", st) is False

    # With config patterns → matches work
    st.story_cfg = {"win_detection": {"regex": [r"\bi am (the )?mastermind\b"]}}
    assert win_condition_detected("I am the mastermind", st) is True
    assert win_condition_detected("just chatting", st) is False


def test_advance_time_handles_no_valid_route_error():
    """Test that advance_time gracefully handles RuntimeError from travel_resolver.
    
    Scenario: User tries to move from iu_apartment_room to iu_office,
    but no valid route exists in the world graph. The travel_resolver
    raises RuntimeError("No valid route from X to Y").
    
    Expected: advance_time() should not crash, and should skip location update
    when travel resolution fails.
    """
    st = init_state()
    st.story_cfg = {"time": {"mins_per_word": 0.0, "base_turn_mins": 1, "travel_mins": 10}}
    st.location = "apartment"
    st.location_id = "iu_apartment_room"
    st.minute = 100
    
    # Mock world graph and travel resolver
    mock_graph = Mock()
    mock_graph.get_location = Mock(return_value=Mock(name="office"))
    
    # Travel resolver raises RuntimeError for invalid route
    mock_resolver = Mock()
    mock_resolver.resolve.side_effect = RuntimeError("No valid route from iu_apartment_room to iu_office")
    
    mock_clock = Mock()
    mock_clock.minute = 115
    mock_clock.advance = Mock()
    
    mock_runtime = Mock()
    mock_runtime.world_graph = mock_graph
    mock_runtime.travel_resolver = mock_resolver
    mock_runtime.world_clock = mock_clock
    
    # Attach mock runtime to state
    st.world_runtime = mock_runtime
    
    # Mock _resolve_destination_id to return a valid destination ID
    with patch("backend.app.engine.gameplay._resolve_destination_id") as mock_resolve_dest:
        mock_resolve_dest.return_value = "iu_office"
        
        # This should NOT crash despite travel_resolver raising RuntimeError
        advance_time(st, "go to office")
    
    # Verify that travel_resolver was called (it did attempt the travel)
    mock_resolver.resolve.assert_called_once_with("iu_apartment_room", "iu_office")
    
    # Verify state was NOT changed due to the error
    # Location should remain unchanged when travel resolution fails
    assert st.location == "apartment"
    assert st.location_id == "iu_apartment_room"
    # Time should be incremented by base_turn_mins only
    assert st.minute == 101