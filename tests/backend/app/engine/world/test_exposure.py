from backend.app.engine.world.exposure import ExposureResolver


def test_exposure_resolver_prob_extremes():
    probs = {
        "p_pass_C": 1.0,
        "p_event_at_C": 1.0,
        "p_exit_A": 1.0,
        "p_enter_B": 0.0,
        "p_describe_B": 0.0,
    }
    r = ExposureResolver(seed=123, probs=probs)
    exp = r.roll(intermediate_id="C")

    assert exp.pass_intermediate is True
    assert exp.event_at_intermediate is True
    assert exp.exit_event is True
    assert exp.enter_event is False
    assert exp.describe_destination is False
    assert exp.intermediate_id == "C"