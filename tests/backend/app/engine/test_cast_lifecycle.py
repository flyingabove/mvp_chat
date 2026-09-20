from copy import deepcopy

import pytest

from backend.app.engine.cast_lifecycle import CastLifecycleState, CastStatus
from backend.app.engine.state import GameState


def _config() -> dict:
    return {
        "enabled": True,
        "arrival_location_id": "front_entry",
        "replacement_policy": "same_slot_next",
        "departure_policy": "committed_intent",
        "slot_groups": {
            "men": {"capacity": 2, "label": "Men"},
            "women": {"capacity": 1, "label": "Women"},
        },
        "members": {
            "a": {"slot_group": "men", "initial_status": "active", "sequence": 0},
            "b": {"slot_group": "men", "initial_status": "active", "sequence": 1},
            "c": {"slot_group": "men", "initial_status": "upcoming", "sequence": 2},
            "d": {"slot_group": "men", "initial_status": "upcoming", "sequence": 3},
            "w": {"slot_group": "women", "initial_status": "active", "sequence": 0},
            "w2": {"slot_group": "women", "initial_status": "inactive", "sequence": 1},
        },
    }


def _state() -> CastLifecycleState:
    return CastLifecycleState.from_config(
        _config(),
        character_ids={"a", "b", "c", "d", "w", "w2"},
        location_ids={"front_entry", "living_room"},
    )


def test_initial_queries_are_deterministic_and_status_gates_scene_eligibility():
    state = _state()

    assert state.active_ids() == ["a", "b", "w"]
    assert state.active_ids("men") == ["a", "b"]
    assert state.vacancies("men") == 0
    assert state.next_up("men") == "c"
    assert state.is_scene_eligible("a") is True
    assert state.is_scene_eligible("c") is False
    assert state.is_scene_eligible("w2") is False
    assert state.is_scene_eligible("missing") is False


def test_replace_chooses_next_same_slot_and_records_domain_result():
    state = _state()

    result = state.replace("a", minute=42, reason="ready to leave", event_id="turn-8:a")

    assert result.departing_id == "a"
    assert result.arriving_id == "c"
    assert result.slot_group == "men"
    assert result.resulting_statuses == {"a": "departed", "c": "active"}
    assert state.members["a"].departed_minute == 42
    assert state.members["a"].departure_reason == "ready to leave"
    assert state.members["c"].activated_minute == 42
    assert state.active_ids("men") == ["b", "c"]
    assert state.arrival_location_id == "front_entry"


def test_replace_is_idempotent_by_event_id():
    state = _state()
    first = state.replace("a", minute=42, reason="ready", event_id="evt-1")
    snapshot = deepcopy(state.to_dict())

    replay = state.replace("not-even-a-member", minute=99, reason="different", event_id="evt-1")

    assert replay is first
    assert state.to_dict() == snapshot
    assert len(state.history) == 1


def test_propose_departure_does_not_change_status():
    """The audit's 'a decision to leave next week is not immediate removal':
    proposing a departure must leave the member ACTIVE and scene-eligible."""
    state = _state()

    transition = state.propose_departure("a", minute=100, reason="stated intent to leave", event_id="propose-a-1")

    assert transition.event_type == "departure_proposed"
    assert transition.departing_id == "a"
    assert state.members["a"].status is CastStatus.ACTIVE
    assert state.is_scene_eligible("a") is True
    assert "a" in state.active_ids("men")


def test_propose_departure_idempotent_by_event_id():
    state = _state()
    first = state.propose_departure("a", minute=100, reason="stated intent", event_id="propose-a-1")
    snapshot = deepcopy(state.to_dict())

    replay = state.propose_departure("b", minute=200, reason="different reason", event_id="propose-a-1")

    assert replay is first
    assert state.to_dict() == snapshot
    assert len(state.history) == 1


def test_propose_departure_rejects_non_active_member():
    state = _state()
    with pytest.raises(ValueError, match="only an active member can propose departure"):
        state.propose_departure("c", minute=100, reason="not even active", event_id="propose-c-1")


def test_propose_departure_requires_event_id():
    state = _state()
    with pytest.raises(ValueError, match="event_id must be non-empty"):
        state.propose_departure("a", minute=100, reason="x", event_id="")


def test_propose_departure_rejects_when_disabled():
    config = _config()
    config["enabled"] = False
    state = CastLifecycleState.from_config(config, character_ids={"a", "b", "c", "d", "w", "w2"})
    with pytest.raises(ValueError, match="cast lifecycle is disabled"):
        state.propose_departure("a", minute=100, reason="x", event_id="propose-a-1")


def test_wrong_slot_replacement_rejects_without_partial_mutation():
    state = _state()
    before = deepcopy(state.to_dict())

    with pytest.raises(ValueError, match="belongs to 'women', not 'men'"):
        state.replace("a", arriving_id="w2", minute=5, event_id="bad")

    assert state.to_dict() == before


def test_non_upcoming_replacement_rejects_without_partial_mutation():
    state = _state()
    before = deepcopy(state.to_dict())

    with pytest.raises(ValueError, match="must be upcoming"):
        state.replace("a", arriving_id="b", minute=5, event_id="bad")

    assert state.to_dict() == before


def test_empty_queue_allows_departure_and_leaves_a_vacancy():
    config = _config()
    del config["members"]["c"]
    del config["members"]["d"]
    state = CastLifecycleState.from_config(config)

    result = state.replace("a", minute=9, reason="new job", event_id="empty")

    assert result.arriving_id is None
    assert state.members["a"].status is CastStatus.DEPARTED
    assert state.vacancies("men") == 1


def test_deactivate_retains_member_and_activate_requires_capacity():
    state = _state()

    state.deactivate("w", minute=3, reason="travel")
    assert state.members["w"].status is CastStatus.INACTIVE
    assert state.vacancies("women") == 1
    state.activate("w2", minute=4)
    assert state.members["w2"].status is CastStatus.ACTIVE
    with pytest.raises(ValueError, match="at capacity"):
        state.activate("w", minute=5)


def test_departed_member_cannot_be_reactivated():
    state = _state()
    state.depart("a", minute=10, reason="finished")

    with pytest.raises(ValueError, match="cannot be reactivated"):
        state.activate("a", minute=11)


def test_snapshot_round_trip_preserves_statuses_history_and_queue():
    state = _state()
    state.replace("a", minute=42, reason="ready", event_id="evt-1")

    restored = CastLifecycleState.from_dict(state.to_dict())

    assert restored.to_dict() == state.to_dict()
    assert restored.next_up("men") == "d"
    assert restored.history[0].event_id == "evt-1"


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda cfg: cfg["slot_groups"]["men"].update(capacity=0), "must be a positive integer"),
        (lambda cfg: cfg["members"]["c"].update(slot_group="missing"), "unknown slot group"),
        (lambda cfg: cfg["members"]["c"].update(sequence=1), "duplicate sequence"),
        (lambda cfg: cfg["members"]["c"].update(initial_status="waiting"), "unknown initial_status"),
        (lambda cfg: cfg.update(arrival_location_id="nowhere"), "does not exist"),
        (lambda cfg: cfg["members"].update(ghost={"slot_group": "men", "initial_status": "upcoming", "sequence": 9}), "not an authored character"),
        (lambda cfg: cfg.update(departure_policy="just_leave"), "unsupported departure_policy"),
        (lambda cfg: cfg.update(replacement_timing="next_week"), "unsupported replacement_timing"),
    ],
)
def test_invalid_authoring_is_rejected_with_meaningful_errors(change, error):
    config = _config()
    change(config)

    with pytest.raises(ValueError, match=error):
        CastLifecycleState.from_config(
            config,
            character_ids={"a", "b", "c", "d", "w", "w2"},
            location_ids={"front_entry"},
        )


def test_initial_capacity_overflow_is_rejected():
    config = _config()
    config["members"]["c"]["initial_status"] = "active"

    with pytest.raises(ValueError, match="3 active members but capacity 2"):
        CastLifecycleState.from_config(config)


def test_game_state_lifecycle_is_optional_for_legacy_stories():
    game_state = GameState()

    assert game_state.cast_lifecycle is None


def test_replacement_timing_defaults_to_immediate_when_omitted():
    config = _config()
    assert "replacement_timing" not in config
    state = CastLifecycleState.from_config(
        config, character_ids={"a", "b", "c", "d", "w", "w2"}, location_ids={"front_entry"},
    )
    assert state.replacement_timing == "immediate"


def test_replacement_timing_next_day_parsed_from_config():
    config = _config()
    config["replacement_timing"] = "next_day"
    state = CastLifecycleState.from_config(
        config, character_ids={"a", "b", "c", "d", "w", "w2"}, location_ids={"front_entry"},
    )
    assert state.replacement_timing == "next_day"


def test_replacement_timing_round_trips_through_snapshot():
    config = _config()
    config["replacement_timing"] = "next_day"
    state = CastLifecycleState.from_config(
        config, character_ids={"a", "b", "c", "d", "w", "w2"}, location_ids={"front_entry"},
    )
    restored = CastLifecycleState.from_dict(state.to_dict())
    assert restored.replacement_timing == "next_day"
