# tests/backend/engine/world/test_exposure.py
from backend.app.engine.world.exposure import ExposureResolver


def test_exposure_without_intermediate():
    probs = {
        "p_exit_A": 1.0,
        "p_pass_C": 1.0,
        "p_event_at_C": 1.0,
        "p_enter_B": 1.0,
        "p_describe_B": 1.0,
    }

    resolver = ExposureResolver(seed=123, probs=probs)
    exposure = resolver.roll(intermediate_id=None)

    assert exposure.exit_event is True
    assert exposure.pass_intermediate is False
    assert exposure.event_at_intermediate is False
    assert exposure.enter_event is True
    assert exposure.describe_destination is True


def test_exposure_with_intermediate():
    probs = {
        "p_exit_A": 0.0,
        "p_pass_C": 1.0,
        "p_event_at_C": 1.0,
        "p_enter_B": 0.0,
        "p_describe_B": 0.0,
    }

    resolver = ExposureResolver(seed=999, probs=probs)
    exposure = resolver.roll(intermediate_id="cafe")

    assert exposure.pass_intermediate is True
    assert exposure.event_at_intermediate is True
    assert exposure.intermediate_id == "cafe"
