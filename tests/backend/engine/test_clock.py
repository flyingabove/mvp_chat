# tests/backend/engine/world/test_clock.py
import pytest
from backend.app.engine.world.clock import WorldClock


def test_clock_advances_time():
    clock = WorldClock(start_minute=0)
    clock.advance(5)
    assert clock.minute == 5


def test_clock_rejects_non_positive_advance():
    clock = WorldClock()
    with pytest.raises(ValueError):
        clock.advance(0)

    with pytest.raises(ValueError):
        clock.advance(-3)
