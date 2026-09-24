# backend/app/utils/stage_timer.py
"""Phase 0B — per-turn stage timing ledger.

Purpose: every later phase (1 correctness fixes, 3 measured optimization,
4 Jev economics) needs a "before/after" number to compare against. Without
this, "p95 improved" or "Jev saved X%" is a claim, not a measurement.

Design choice: this does NOT restructure `_chat_handler_impl` (that is
Phase 2's job — the turn service extraction). It is a small opt-in
accumulator that call sites bracket around existing code with a context
manager, so today's monolithic handler can start emitting real stage
timings without a rewrite. When Phase 2 splits the handler into named
services, each service can carry its own StageTimer stage naturally.

Usage:
    timer = StageTimer()
    with timer.stage("retrieval"):
        retrieved, debug = retrieve_knowledge(...)
    with timer.stage("storyteller"):
        r = await client.post(...)
    jlog({"kind": "turn_stage_ledger", **timer.as_ledger(extra_fields)})

Every stage duration is wall-clock milliseconds via time.perf_counter(),
which is monotonic and immune to system clock adjustments — important
because this runs in a long-lived server process, not a short script.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator


class StageTimer:
    """Accumulates named stage durations (ms) for one turn.

    Stages may be entered more than once (e.g. "retrieval" could run twice
    on a retry path); repeated entries accumulate rather than overwrite, so
    the ledger reflects total time spent in a stage, not just the last call.
    """

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._durations_ms: dict[str, float] = {}
        self._counts: dict[str, int] = {}
        self._errors: dict[str, str] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        t0 = time.perf_counter()
        wall_t0 = time.time()
        try:
            yield
        except Exception as exc:
            # Record which stage failed, but never swallow the exception —
            # callers still need their normal error handling to run.
            self._errors[name] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            # perf_counter is the normal source of truth. A few Windows hosts
            # have reported a temporarily under-advancing performance counter
            # after long, mixed sync/async test runs, so retain wall-clock as
            # a defensive lower bound rather than logging a knowingly short
            # stage duration.
            elapsed_ms = max(time.perf_counter() - t0, time.time() - wall_t0) * 1000.0
            self._durations_ms[name] = self._durations_ms.get(name, 0.0) + elapsed_ms
            self._counts[name] = self._counts.get(name, 0) + 1

    def total_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0

    def as_ledger(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a flat dict suitable for a single jlog(...) call.

        Stage durations are rounded to whole milliseconds — sub-millisecond
        precision is noise for anything that includes a network call, and
        rounding keeps the JSONL log compact across millions of turns.
        """
        ledger: dict[str, Any] = {
            "stage_ms": {k: round(v, 1) for k, v in self._durations_ms.items()},
            "stage_calls": dict(self._counts),
            "total_ms": round(self.total_ms(), 1),
        }
        if self._errors:
            ledger["stage_errors"] = dict(self._errors)
        if extra:
            ledger.update(extra)
        return ledger
