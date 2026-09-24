"""Phase 0B — unit tests for the workload harness's pure summary math.

Does not make network calls (no server dependency); exercises
ScenarioResults.summary() directly, which is the part later phases actually
read numbers from. The harness's HTTP driving logic is exercised by actually
running it (see documentation/PHASE_0B_BASELINE_2026_09_22.json for a real
captured run against live beta), not by mocking httpx here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "bench"))

from turn_workload_harness import ScenarioResults, TurnResult  # noqa: E402


def test_summary_computes_p50_p95_over_successful_results_only():
    sr = ScenarioResults("test")
    # 10 successes at 100..1000ms, one failure that must not skew latency stats.
    for i in range(1, 11):
        sr.results.append(TurnResult("test", True, latency_ms=i * 100.0))
    sr.results.append(TurnResult("test", False, latency_ms=99999.0, error="boom"))

    s = sr.summary()
    assert s["attempts"] == 11
    assert s["ok"] == 10
    assert s["failed"] == 1
    assert s["latency_ms_max"] == 1000.0  # not 99999 — failures excluded
    assert s["latency_ms_p50"] == 500.0 or s["latency_ms_p50"] == 600.0  # index-based, either edge is fine
    assert s["latency_ms_p95"] >= s["latency_ms_p50"]


def test_summary_handles_all_failures_without_crashing():
    sr = ScenarioResults("test")
    sr.results.append(TurnResult("test", False, latency_ms=500.0, error="timeout"))
    s = sr.summary()
    assert s["ok"] == 0
    assert s["failed"] == 1
    assert s["latency_ms_p50"] is None
    assert s["latency_ms_max"] is None


def test_summary_handles_empty_results():
    sr = ScenarioResults("empty")
    s = sr.summary()
    assert s["attempts"] == 0
    assert s["ok"] == 0
    assert s["latency_ms_p50"] is None


def test_token_means_ignore_none_values():
    sr = ScenarioResults("test")
    sr.results.append(TurnResult("test", True, latency_ms=100.0, prompt_tokens=1000, completion_tokens=100))
    sr.results.append(TurnResult("test", True, latency_ms=100.0, prompt_tokens=None, completion_tokens=None))
    s = sr.summary()
    assert s["prompt_tokens_mean"] == 1000
    assert s["completion_tokens_mean"] == 100


def test_p95_is_at_or_above_p50_for_monotonic_latencies():
    sr = ScenarioResults("test")
    for i in range(1, 101):
        sr.results.append(TurnResult("test", True, latency_ms=float(i)))
    s = sr.summary()
    assert s["latency_ms_p95"] >= s["latency_ms_p50"]
    assert s["latency_ms_max"] == 100.0
