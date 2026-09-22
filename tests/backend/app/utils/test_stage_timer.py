"""Phase 0B — StageTimer unit tests.

This is the ledger every later phase compares against, so its correctness
matters independent of any handler wiring: a timer that double-counts or
silently swallows a stage failure would make "before/after" numbers lie.
"""
import time

import pytest

from backend.app.utils.stage_timer import StageTimer


def test_single_stage_records_positive_duration():
    timer = StageTimer()
    with timer.stage("retrieval"):
        time.sleep(0.01)
    ledger = timer.as_ledger()
    assert ledger["stage_ms"]["retrieval"] >= 10.0
    assert ledger["stage_calls"]["retrieval"] == 1


def test_multiple_distinct_stages_are_tracked_separately():
    timer = StageTimer()
    with timer.stage("retrieval"):
        time.sleep(0.005)
    with timer.stage("storyteller"):
        time.sleep(0.005)
    ledger = timer.as_ledger()
    assert set(ledger["stage_ms"]) == {"retrieval", "storyteller"}
    assert ledger["stage_calls"] == {"retrieval": 1, "storyteller": 1}


def test_repeated_entry_into_same_stage_accumulates_not_overwrites():
    """A retry path might re-enter 'retrieval' twice in one turn; the ledger
    must reflect total time spent, not just the most recent call."""
    timer = StageTimer()
    with timer.stage("retrieval"):
        time.sleep(0.01)
    with timer.stage("retrieval"):
        time.sleep(0.01)
    ledger = timer.as_ledger()
    assert ledger["stage_ms"]["retrieval"] >= 20.0
    assert ledger["stage_calls"]["retrieval"] == 2


def test_total_ms_covers_the_whole_timer_lifetime_not_just_stages():
    timer = StageTimer()
    time.sleep(0.005)  # time NOT inside any stage (e.g. lock wait)
    with timer.stage("retrieval"):
        time.sleep(0.005)
    ledger = timer.as_ledger()
    assert ledger["total_ms"] >= ledger["stage_ms"]["retrieval"]


def test_exception_inside_a_stage_propagates_and_is_recorded():
    """A failing stage must not be silently absorbed — callers rely on their
    own try/except around the stage body for error handling."""
    timer = StageTimer()
    with pytest.raises(RuntimeError, match="boom"):
        with timer.stage("storyteller"):
            raise RuntimeError("boom")
    ledger = timer.as_ledger()
    assert "storyteller" in ledger["stage_ms"]  # duration up to the raise still recorded
    assert "RuntimeError: boom" in ledger["stage_errors"]["storyteller"]


def test_as_ledger_merges_extra_fields_without_clobbering_stage_data():
    timer = StageTimer()
    with timer.stage("retrieval"):
        pass
    ledger = timer.as_ledger({"req_id": "abc123", "session_id": "s1"})
    assert ledger["req_id"] == "abc123"
    assert ledger["session_id"] == "s1"
    assert "retrieval" in ledger["stage_ms"]


def test_as_ledger_omits_stage_errors_key_when_no_stage_failed():
    timer = StageTimer()
    with timer.stage("retrieval"):
        pass
    ledger = timer.as_ledger()
    assert "stage_errors" not in ledger


def test_durations_are_rounded_to_one_decimal_for_compact_logging():
    timer = StageTimer()
    with timer.stage("x"):
        pass
    ledger = timer.as_ledger()
    # round(x, 1) always leaves at most one decimal digit.
    val = ledger["stage_ms"]["x"]
    assert round(val, 1) == val
