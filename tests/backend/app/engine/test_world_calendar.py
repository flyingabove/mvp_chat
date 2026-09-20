"""Unit tests for backend/app/engine/world_calendar.py (Phase 2 foundation:
day/schedule primitive shared by the cast-cycling scheduler and, eventually,
Phase 3 routines/commitments)."""
import pytest

from backend.app.engine.world_calendar import day_number, PendingEvent


def test_day_number_boundaries():
    assert day_number(0) == 0
    assert day_number(1439) == 0
    assert day_number(1440) == 1
    assert day_number(2881) == 2


def test_day_number_handles_none_and_negative():
    assert day_number(None) == 0
    assert day_number(-100) == 0


def test_pending_event_round_trip():
    ev = PendingEvent(
        event_id="departure_replace_makoto_5",
        event_type="cast_departure_replacement",
        scheduled_day=3,
        payload={"departing_id": "makoto", "reason": "moving out"},
        created_minute=2000,
        status="pending",
    )
    restored = PendingEvent.from_dict(ev.to_dict())
    assert restored.event_id == ev.event_id
    assert restored.event_type == ev.event_type
    assert restored.scheduled_day == ev.scheduled_day
    assert restored.payload == ev.payload
    assert restored.created_minute == ev.created_minute
    assert restored.status == ev.status
    assert restored.applied_minute is None


def test_pending_event_round_trip_with_applied_minute():
    ev = PendingEvent(
        event_id="e1", event_type="t", scheduled_day=1,
        status="applied", applied_minute=1500,
    )
    restored = PendingEvent.from_dict(ev.to_dict())
    assert restored.status == "applied"
    assert restored.applied_minute == 1500


def test_pending_event_from_dict_requires_event_id_and_type():
    with pytest.raises(ValueError):
        PendingEvent.from_dict({"event_type": "t"})
    with pytest.raises(ValueError):
        PendingEvent.from_dict({"event_id": "e1"})
