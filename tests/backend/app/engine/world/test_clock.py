from backend.app.engine.world.clock import WorldClock


def test_world_clock_advances_and_reports_minute():
    c = WorldClock()
    assert c.minute == 0
    c.advance(5)
    assert c.minute == 5