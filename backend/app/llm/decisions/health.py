# backend/app/llm/decisions/health.py
"""Jev circuit breaker — the mechanism behind "each request automatically
knows" a Jev outage without paying a timeout on every subsequent turn.

Exact design from documentation/JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §6.
Per-process, in-memory. Single uvicorn worker is the documented deployment
assumption (the same one prompt_engine.py's A12 _SESSION_LOCKS comment
relies on). `allow_request()` touches only process memory — that is the
property that caps a sustained outage at ~3 slow turns instead of every
turn, since an OPEN breaker costs zero latency.

Only transport/availability failures trip this breaker (timeout, connect
error, non-2xx, unparseable body). Answer-quality issues (BELOW_THRESHOLD,
INVALID_OPTION, MISSING_ANSWER) must NEVER be passed to record_failure() —
Jev is up and answering in those cases; conflating quality tuning with
availability would open the breaker during ordinary threshold tuning.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from backend.app.llm.decisions.types import FallbackReason

# Failures that indicate Jev itself is unavailable, as opposed to Jev being
# up and giving an answer we chose not to use. Only these may ever be passed
# to record_failure() — enforced by an assertion, not just a docstring,
# since a caller passing e.g. BELOW_THRESHOLD here would silently corrupt
# the breaker's availability signal with quality-tuning noise.
_AVAILABILITY_FAILURE_REASONS = frozenset({
    FallbackReason.TIMEOUT,
    FallbackReason.HTTP_ERROR,
    FallbackReason.MALFORMED_RESPONSE,
})


class BreakerState(Enum):
    CLOSED = "closed"        # normal: use Jev
    OPEN = "open"             # Jev presumed down: skip it, zero latency cost
    HALF_OPEN = "half_open"  # cooldown elapsed: let exactly ONE probe through


@dataclass
class JevCircuitBreaker:
    """Construct with the config values from settings.py
    (JEV_BREAKER_FAIL_THRESHOLD etc.) — see __init__ below for the
    convenience constructor that reads them.
    """
    fail_threshold: int = 3
    fail_window_s: float = 60.0
    fail_rate_count: int = 5
    cooldown_s: float = 30.0
    cooldown_max_s: float = 300.0
    clock: Callable[[], float] = field(default=time.monotonic)

    def __post_init__(self) -> None:
        self._state = BreakerState.CLOSED
        self._consecutive_failures = 0
        self._recent_failure_times: list[float] = []
        self._opened_at: float | None = None
        self._current_cooldown_s = self.cooldown_s
        self._half_open_probe_in_flight = False

    @classmethod
    def from_settings(cls) -> "JevCircuitBreaker":
        from backend.app.config import settings
        return cls(
            fail_threshold=settings.JEV_BREAKER_FAIL_THRESHOLD,
            fail_window_s=settings.JEV_BREAKER_FAIL_WINDOW_S,
            fail_rate_count=settings.JEV_BREAKER_FAIL_RATE_COUNT,
            cooldown_s=settings.JEV_BREAKER_COOLDOWN_S,
            cooldown_max_s=settings.JEV_BREAKER_COOLDOWN_MAX_S,
        )

    def state(self) -> BreakerState:
        self._maybe_transition_open_to_half_open()
        return self._state

    def allow_request(self) -> bool:
        """Call once per turn before attempting Jev. False means: skip Jev
        entirely, go straight to legacy, at zero latency cost (CLOSED path
        excluded — this only returns False for OPEN).

        HALF_OPEN admission: exactly ONE caller gets True per HALF_OPEN
        window (the "probe"); concurrent callers arriving while a probe is
        already in flight are treated as OPEN (False) so a burst of
        requests during the exact cooldown-elapsed instant doesn't all
        become simultaneous probes.
        """
        current = self.state()
        if current is BreakerState.CLOSED:
            return True
        if current is BreakerState.OPEN:
            return False
        # HALF_OPEN: admit exactly one probe.
        if self._half_open_probe_in_flight:
            return False
        self._half_open_probe_in_flight = True
        return True

    def record_success(self) -> None:
        was_half_open = self._state is BreakerState.HALF_OPEN
        self._consecutive_failures = 0
        self._recent_failure_times.clear()
        self._state = BreakerState.CLOSED
        self._opened_at = None
        self._half_open_probe_in_flight = False
        if was_half_open:
            # Probe succeeded: reset cooldown to the base value, not just
            # the failure counters, so a FUTURE outage starts its backoff
            # fresh rather than continuing from a previously-doubled value.
            self._current_cooldown_s = self.cooldown_s

    def record_failure(self, reason: FallbackReason) -> None:
        assert reason in _AVAILABILITY_FAILURE_REASONS, (
            f"record_failure() called with a non-availability reason {reason!r} — "
            "quality-tuning failures (BELOW_THRESHOLD, INVALID_OPTION, "
            "MISSING_ANSWER) must never trip the breaker. This is a caller bug."
        )
        now = self.clock()
        was_half_open = self._state is BreakerState.HALF_OPEN
        self._half_open_probe_in_flight = False

        if was_half_open:
            # Probe failed: reopen immediately, double the cooldown (capped).
            self._state = BreakerState.OPEN
            self._opened_at = now
            self._current_cooldown_s = min(self._current_cooldown_s * 2, self.cooldown_max_s)
            return

        self._consecutive_failures += 1
        self._recent_failure_times.append(now)
        self._recent_failure_times = [
            t for t in self._recent_failure_times if now - t <= self.fail_window_s
        ]

        if (self._consecutive_failures >= self.fail_threshold
                or len(self._recent_failure_times) >= self.fail_rate_count):
            self._state = BreakerState.OPEN
            self._opened_at = now

    def _maybe_transition_open_to_half_open(self) -> None:
        if self._state is not BreakerState.OPEN:
            return
        if self._opened_at is None:
            return
        if self.clock() - self._opened_at >= self._current_cooldown_s:
            self._state = BreakerState.HALF_OPEN
            self._half_open_probe_in_flight = False

    def snapshot(self) -> dict:
        """For GET /api/health's non-authoritative `jev` block and for
        telemetry (JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §10)."""
        current = self.state()
        return {
            "state": current.value,
            "consecutive_failures": self._consecutive_failures,
            "opened_at": self._opened_at,
            "cooldown_s": self._current_cooldown_s,
        }
