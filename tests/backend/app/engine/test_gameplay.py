from unittest.mock import Mock, patch
from backend.app.engine.gameplay import (
    word_count,
    sanitize_location,
    manifest_mode,
    advance_time,
    advance_time_by,
    win_condition_detected,
    process_pending_events,
)
from backend.app.engine.state import init_state
from backend.app.engine.cast_lifecycle import CastLifecycleState
from backend.app.engine.world_calendar import PendingEvent


def test_word_count_and_sanitize_location():
    assert word_count("") == 0
    assert word_count("a   b c") == 3
    assert sanitize_location("<b>Room</b>\n\n302") == "Room 302"


def test_manifest_mode_defaults_and_inside_location():
    st = init_state()
    # With manifestation rules from story config (generic key)
    st.story_cfg = {"rules": {"manifestation": {"location_name_contains": ["officetel", "studio"]}}}
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


def test_advance_time_by_jumps_minute_without_touching_location():
    st = init_state()
    st.minute = 100
    st.location = "Cafe"
    st.location_id = "cafe"

    advance_time_by(st, 8 * 60)

    assert st.minute == 100 + 8 * 60
    # A time skip is a pure clock jump, never a movement command.
    assert st.location == "Cafe"
    assert st.location_id == "cafe"


def test_advance_time_by_zero_or_negative_is_noop():
    st = init_state()
    st.minute = 50

    advance_time_by(st, 0)
    assert st.minute == 50

    advance_time_by(st, -100)
    assert st.minute == 50


def test_advance_time_by_syncs_world_clock_when_present():
    st = init_state()
    st.minute = 100

    mock_clock = Mock()
    mock_clock.minute = 100 + 240  # world_clock is authoritative post-advance
    mock_clock.advance = Mock()

    mock_runtime = Mock()
    mock_runtime.world_clock = mock_clock
    st.world_runtime = mock_runtime

    advance_time_by(st, 240)

    mock_clock.advance.assert_called_once_with(240)
    assert st.minute == 340


def test_win_condition_detected_with_config_patterns():
    st = init_state()
    # No win_detection config → always False
    st.story_cfg = {}
    assert win_condition_detected("I am the mastermind", st) is False

    # With config patterns → matches work
    st.story_cfg = {"win_detection": {"regex": [r"\bi am (the )?mastermind\b"]}}
    assert win_condition_detected("I am the mastermind", st) is True
    assert win_condition_detected("just chatting", st) is False


def test_win_condition_detected_false_for_terrace_until_departure_is_state_validated():
    """A romance objective does not make arbitrary story text proof of mutual departure."""
    from backend.app.engine.story_loader import load_story

    story = load_story("six_strangers")
    assert story is not None
    story_dict = story.as_dict()
    assert "win_detection" not in story_dict
    assert story_dict["goal"]["win_text_rule"]

    st = init_state()
    st.story_cfg = story_dict
    assert win_condition_detected("I confess to everything", st) is False
    assert win_condition_detected("I am the mastermind", st) is False
    assert win_condition_detected("We both agree to leave the house together", st) is False


# ─── BUG-06: manifest_mode uses location_id, not display string ─────────────

def test_manifest_mode_uses_location_id_when_location_ids_defined():
    """Preferred path uses state.location_id exact match."""
    st = init_state()
    st.story_cfg = {"rules": {"manifestation": {"location_ids": ["home_room"]}}}
    st.location_id = "home_room"
    assert manifest_mode(st) == "materialize"

    st.location_id = "outside_plaza"
    assert manifest_mode(st) == "whisper"


def test_manifest_mode_location_id_empty_returns_whisper():
    """If location_ids is set but location_id is empty, whisper."""
    st = init_state()
    st.story_cfg = {"rules": {"manifestation": {"location_ids": ["home_room"]}}}
    st.location_id = ""
    assert manifest_mode(st) == "whisper"


def test_manifest_mode_falls_back_to_display_name_when_no_location_ids():
    """location_name_contains substring match works when location_ids absent."""
    st = init_state()
    st.story_cfg = {"rules": {"manifestation": {"location_name_contains": ["officetel"]}}}
    st.location = "Nonhyeon-dong officetel"
    assert manifest_mode(st) == "materialize"

    st.location = "Outside Park"
    assert manifest_mode(st) == "whisper"


# ─── Backward-compat: deprecated apartment_* keys still work ─────────────────

def test_manifest_mode_backward_compat_apartment_location_ids():
    """Deprecated apartment_location_ids key is still honoured."""
    st = init_state()
    st.story_cfg = {"rules": {"manifestation": {"apartment_location_ids": ["legacy_room"]}}}
    st.location_id = "legacy_room"
    assert manifest_mode(st) == "materialize"

    st.location_id = "other_room"
    assert manifest_mode(st) == "whisper"


def test_manifest_mode_backward_compat_apartment_location_contains():
    """Deprecated apartment_location_contains key is still honoured."""
    st = init_state()
    st.story_cfg = {"rules": {"manifestation": {"apartment_location_contains": ["officetel"]}}}
    st.location = "Nonhyeon-dong officetel"
    assert manifest_mode(st) == "materialize"

    st.location = "Outside Park"
    assert manifest_mode(st) == "whisper"


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


# ---------------------------------------------------------------------------
# Phase 2 cast-cycling scheduler: process_pending_events
# ---------------------------------------------------------------------------

def _lifecycle_config() -> dict:
    return {
        "enabled": True,
        "arrival_location_id": "front_entry",
        "replacement_policy": "same_slot_next",
        "departure_policy": "committed_intent",
        "slot_groups": {"men": {"capacity": 1, "label": "Men"}},
        "members": {
            "a": {"slot_group": "men", "initial_status": "active", "sequence": 0},
            "b": {"slot_group": "men", "initial_status": "upcoming", "sequence": 1},
        },
    }


def _state_with_lifecycle(minute: int = 0) -> "GameState":
    st = init_state()
    st.cast_lifecycle = CastLifecycleState.from_config(
        _lifecycle_config(), character_ids={"a", "b"}, location_ids={"front_entry"},
    )
    st.minute = minute
    st.character_locations = {"a": "front_entry"}
    return st


def _fake_apply_cast_replacement(state, departing_id, *, reason, event_id, arriving_id=None):
    """Mirrors prompt_engine.py's _apply_cast_replacement without importing
    it (avoids the same circular-import concern process_pending_events
    itself is designed to sidestep)."""
    transition = state.cast_lifecycle.replace(
        departing_id, minute=state.minute, reason=reason, event_id=event_id, arriving_id=arriving_id,
    )
    state.character_locations.pop(departing_id, None)
    if transition.arriving_id:
        state.character_locations[transition.arriving_id] = state.cast_lifecycle.arrival_location_id
    return transition


def test_process_pending_events_skips_events_not_yet_due():
    st = _state_with_lifecycle(minute=100)  # day 0
    st.pending_events = [PendingEvent(
        event_id="e1", event_type="cast_departure_replacement",
        scheduled_day=1, payload={"departing_id": "a", "reason": "leaving"},
    )]

    fired = process_pending_events(st, apply_cast_replacement=_fake_apply_cast_replacement)

    assert fired == []
    assert st.pending_events[0].status == "pending"
    assert st.cast_lifecycle.members["a"].status.value == "active"


def test_process_pending_events_executes_event_due_today():
    st = _state_with_lifecycle(minute=1500)  # day 1
    st.pending_events = [PendingEvent(
        event_id="e1", event_type="cast_departure_replacement",
        scheduled_day=1, payload={"departing_id": "a", "reason": "leaving"},
    )]

    fired = process_pending_events(st, apply_cast_replacement=_fake_apply_cast_replacement)

    assert len(fired) == 1
    fired_event, transition = fired[0]
    assert fired_event.status == "applied"
    assert fired_event.applied_minute == 1500
    assert transition.departing_id == "a"
    assert transition.arriving_id == "b"
    assert st.cast_lifecycle.members["a"].status.value == "departed"
    assert st.cast_lifecycle.members["b"].status.value == "active"
    assert st.character_locations.get("b") == "front_entry"
    assert "a" not in st.character_locations


def test_process_pending_events_executes_event_scheduled_for_an_earlier_day():
    """A day boundary that has already passed (e.g. the player skipped
    several days in one turn) must still fire, not just an exact match."""
    st = _state_with_lifecycle(minute=1440 * 5)  # day 5
    st.pending_events = [PendingEvent(
        event_id="e1", event_type="cast_departure_replacement",
        scheduled_day=1, payload={"departing_id": "a", "reason": "leaving"},
    )]

    fired = process_pending_events(st, apply_cast_replacement=_fake_apply_cast_replacement)

    assert len(fired) == 1
    assert st.cast_lifecycle.members["a"].status.value == "departed"


def test_process_pending_events_ignores_non_pending_events():
    st = _state_with_lifecycle(minute=1500)
    st.pending_events = [PendingEvent(
        event_id="e1", event_type="cast_departure_replacement",
        scheduled_day=1, payload={"departing_id": "a", "reason": "leaving"},
        status="applied",
    )]

    fired = process_pending_events(st, apply_cast_replacement=_fake_apply_cast_replacement)

    assert fired == []


def test_process_pending_events_cancels_event_on_apply_failure():
    st = _state_with_lifecycle(minute=1500)
    # Simulate the departing member already being gone via some other path
    # (e.g. depart() called directly) by the time the pending event fires -
    # replace() requires the departing member to still be ACTIVE and raises
    # ValueError otherwise.
    st.cast_lifecycle.depart("a", minute=1000, reason="already gone via another path")
    st.pending_events = [PendingEvent(
        event_id="e1", event_type="cast_departure_replacement",
        scheduled_day=1, payload={"departing_id": "a", "reason": "leaving"},
    )]

    fired = process_pending_events(st, apply_cast_replacement=_fake_apply_cast_replacement)

    assert fired == []
    assert st.pending_events[0].status == "cancelled"


def test_process_pending_events_leaves_valid_vacancy_when_queue_empty():
    st = _state_with_lifecycle(minute=1500)
    # Exhaust the upcoming queue so no replacement is available: deactivate
    # "b" (the only upcoming member) via activate-then-deactivate is not
    # possible while upcoming, so simulate emptiness by monkeypatching
    # next_up to report none - simplest is to directly flip status.
    from backend.app.engine.cast_lifecycle import CastStatus
    st.cast_lifecycle.members["b"].status = CastStatus.INACTIVE
    st.pending_events = [PendingEvent(
        event_id="e1", event_type="cast_departure_replacement",
        scheduled_day=1, payload={"departing_id": "a", "reason": "leaving"},
    )]

    fired = process_pending_events(st, apply_cast_replacement=_fake_apply_cast_replacement)

    assert len(fired) == 1
    fired_event, transition = fired[0]
    assert transition.arriving_id is None
    assert st.cast_lifecycle.active_ids("men") == []
    assert "a" not in st.character_locations
