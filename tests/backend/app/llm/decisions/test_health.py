"""Tests for JevCircuitBreaker (backend/app/llm/decisions/health.py).

Covers every case in JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §11's circuit
breaker test plan. Uses an injectable fake clock throughout so cooldown
timing is deterministic, never a real sleep().
"""
import pytest

from backend.app.llm.decisions.health import BreakerState, JevCircuitBreaker
from backend.app.llm.decisions.types import FallbackReason


def _breaker(**overrides):
    fake_time = {"t": 0.0}
    defaults = dict(fail_threshold=3, fail_window_s=60.0, fail_rate_count=5,
                     cooldown_s=30.0, cooldown_max_s=300.0, clock=lambda: fake_time["t"])
    defaults.update(overrides)
    return JevCircuitBreaker(**defaults), fake_time


def test_starts_closed():
    b, _ = _breaker()
    assert b.state() is BreakerState.CLOSED
    assert b.allow_request() is True


def test_opens_after_consecutive_failures():
    b, _ = _breaker(fail_threshold=3)
    b.record_failure(FallbackReason.TIMEOUT)
    assert b.state() is BreakerState.CLOSED
    b.record_failure(FallbackReason.TIMEOUT)
    assert b.state() is BreakerState.CLOSED
    b.record_failure(FallbackReason.TIMEOUT)
    assert b.state() is BreakerState.OPEN


def test_opens_on_failure_rate_within_window_even_if_not_consecutive():
    """5 failures within 60s opens it even if threshold(3-consecutive)
    alone wouldn't have - interleaved successes reset consecutive count
    but not necessarily the rate-based trip."""
    b, t = _breaker(fail_threshold=10, fail_rate_count=3, fail_window_s=60.0)
    b.record_failure(FallbackReason.TIMEOUT)
    t["t"] = 10.0
    b.record_failure(FallbackReason.HTTP_ERROR)
    t["t"] = 20.0
    b.record_failure(FallbackReason.MALFORMED_RESPONSE)
    assert b.state() is BreakerState.OPEN, "3 failures within the 60s window must open it"


def test_failures_outside_the_window_do_not_count_toward_rate_trip():
    b, t = _breaker(fail_threshold=10, fail_rate_count=2, fail_window_s=10.0)
    b.record_failure(FallbackReason.TIMEOUT)
    t["t"] = 100.0  # well outside the 10s window
    b.record_failure(FallbackReason.TIMEOUT)
    assert b.state() is BreakerState.CLOSED, "the first failure aged out of the window"


def test_open_breaker_skips_jev_with_no_latency_cost():
    b, _ = _breaker(fail_threshold=1)
    b.record_failure(FallbackReason.TIMEOUT)
    assert b.state() is BreakerState.OPEN
    assert b.allow_request() is False


def test_half_open_admits_exactly_one_probe():
    b, t = _breaker(fail_threshold=1, cooldown_s=30.0)
    b.record_failure(FallbackReason.TIMEOUT)
    t["t"] = 30.0
    assert b.state() is BreakerState.HALF_OPEN
    assert b.allow_request() is True, "first caller gets the probe"
    assert b.allow_request() is False, "second concurrent caller must not also probe"


def test_half_open_success_closes_and_resets_counters():
    b, t = _breaker(fail_threshold=1, cooldown_s=30.0)
    b.record_failure(FallbackReason.TIMEOUT)
    t["t"] = 30.0
    b.allow_request()
    b.record_success()
    assert b.state() is BreakerState.CLOSED
    assert b._consecutive_failures == 0
    assert b._recent_failure_times == []


def test_half_open_success_resets_cooldown_to_base_for_a_future_outage():
    b, t = _breaker(fail_threshold=1, cooldown_s=10.0, cooldown_max_s=100.0)
    b.record_failure(FallbackReason.TIMEOUT)
    t["t"] = 10.0
    b.allow_request()
    b.record_failure(FallbackReason.TIMEOUT)  # probe fails -> cooldown doubles to 20
    assert b._current_cooldown_s == 20.0
    t["t"] = 30.0
    b.allow_request()
    b.record_success()  # probe succeeds this time
    assert b._current_cooldown_s == 10.0, "cooldown must reset to base on a successful probe"


def test_half_open_failure_reopens_with_doubled_cooldown():
    b, t = _breaker(fail_threshold=1, cooldown_s=10.0, cooldown_max_s=100.0)
    b.record_failure(FallbackReason.TIMEOUT)
    t["t"] = 10.0
    assert b.state() is BreakerState.HALF_OPEN
    b.allow_request()
    b.record_failure(FallbackReason.TIMEOUT)
    assert b.state() is BreakerState.OPEN
    assert b._current_cooldown_s == 20.0


def test_cooldown_backoff_is_capped_at_max():
    b, t = _breaker(fail_threshold=1, cooldown_s=100.0, cooldown_max_s=150.0)
    b.record_failure(FallbackReason.TIMEOUT)
    t["t"] = 100.0
    b.allow_request()
    b.record_failure(FallbackReason.TIMEOUT)  # would double to 200, capped to 150
    assert b._current_cooldown_s == 150.0


@pytest.mark.parametrize("reason", [
    FallbackReason.BELOW_THRESHOLD, FallbackReason.INVALID_OPTION, FallbackReason.MISSING_ANSWER,
])
def test_quality_failures_never_trip_the_breaker(reason):
    """Answer-quality issues must NEVER be passed to record_failure() at
    all - the design says this must be a caller bug (an assertion), not a
    silently-ignored no-op, so callers can't accidentally rely on 'passing
    it is harmless'."""
    b, _ = _breaker()
    with pytest.raises(AssertionError):
        b.record_failure(reason)
    assert b.state() is BreakerState.CLOSED, "state must be unaffected even though the call raised"


def test_snapshot_reflects_current_state_for_health_endpoint():
    b, t = _breaker(fail_threshold=1, cooldown_s=30.0)
    snap = b.snapshot()
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 0
    assert snap["opened_at"] is None

    b.record_failure(FallbackReason.TIMEOUT)
    snap = b.snapshot()
    assert snap["state"] == "open"
    assert snap["consecutive_failures"] == 1
    assert snap["opened_at"] == 0.0
    assert snap["cooldown_s"] == 30.0


def test_from_settings_reads_current_config_values(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "JEV_BREAKER_FAIL_THRESHOLD", 7)
    monkeypatch.setattr(settings, "JEV_BREAKER_COOLDOWN_S", 15.0)
    b = JevCircuitBreaker.from_settings()
    assert b.fail_threshold == 7
    assert b.cooldown_s == 15.0
