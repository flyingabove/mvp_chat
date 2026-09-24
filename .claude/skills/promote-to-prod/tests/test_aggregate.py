"""Tests for .claude/skills/promote-to-prod/arena/aggregate.py (JEV_GAME_ARENA_DESIGN.md §8)."""
import math

import pytest

from arena.aggregate import (
    EpisodeOutcome, Vote, bootstrap_p, classify, decide_episode, elo_delta, stratified_p, summarize,
)
from arena.contracts import Outcome

B, P, T, U = Outcome.BETA_WIN, Outcome.PROD_WIN, Outcome.TIE, Outcome.UNRESOLVED


def eps(outcomes, stratum="s1", clusters=None):
    return [EpisodeOutcome(f"{stratum}.{i}", stratum, (clusters or {}).get(i, f"c{i}"), o)
            for i, o in enumerate(outcomes)]


def test_elo_delta_matches_design_example():
    """Design §8: p = 0.60 gives approximately +70.4 Elo-equivalent."""
    assert elo_delta(0.60) == pytest.approx(70.44, abs=0.01)
    assert elo_delta(0.5) == 0.0
    assert elo_delta(0.40) == pytest.approx(-70.44, abs=0.01)


def test_elo_delta_is_unbounded_at_extremes_not_clamped():
    assert elo_delta(1.0) == math.inf
    assert elo_delta(0.0) == -math.inf


def test_classify_uses_declared_margin_with_tie_band():
    assert classify(0.56, 0.55) is B
    assert classify(0.44, 0.55) is P
    assert classify(0.55, 0.55) is T
    assert classify(0.45, 0.55) is T


def test_episode_resolved_when_unresolved_votes_cannot_flip_category():
    votes = [Vote("canon", 0, 0.5, 1.0), Vote("agency", 0, 0.4, 1.0), Vote("clarity", 0, 0.1, None)]
    d = decide_episode(votes, 0.55)
    # low = 0.9, high = 1.0 -> both beta
    assert d.outcome is B
    assert d.low == pytest.approx(0.9)
    assert d.coverage == pytest.approx(0.9)


def test_episode_unresolved_when_missing_votes_could_flip_it():
    votes = [Vote("canon", 0, 0.25, 1.0), Vote("agency", 0, 0.75, None)]
    d = decide_episode(votes, 0.55)
    assert d.outcome is U
    assert (d.low, d.high) == (pytest.approx(0.25), pytest.approx(1.0))


def test_episode_with_no_votes_is_unresolved_not_a_tie():
    assert decide_episode([], 0.55).outcome is U


def test_stratified_p_weights_strata_equally_regardless_of_sample_count():
    """Extra runs of one story must not dominate (§8 fixed suite weights)."""
    episodes = eps([B] * 9, "big") + eps([P], "small")
    assert stratified_p(episodes, {"big": 1.0, "small": 1.0}) == pytest.approx(0.5)


def test_stratified_p_ignores_unresolved_and_counts_ties_half():
    assert stratified_p(eps([B, T, P, U]), {"s1": 1}) == pytest.approx(0.5)


def test_bootstrap_is_deterministic_for_a_seed():
    episodes = eps([B, B, P, T, B, P, B])
    assert bootstrap_p(episodes, {"s1": 1}, iterations=200, seed=7) == \
        bootstrap_p(episodes, {"s1": 1}, iterations=200, seed=7)


def test_bootstrap_resamples_scenario_clusters_together():
    """Two replicates of one scenario always travel together, so a draw can
    never contain exactly one of them."""
    episodes = eps([B, B, P, P], clusters={0: "x", 1: "x", 2: "y", 3: "y"})
    samples = bootstrap_p(episodes, {"s1": 1}, iterations=300, seed=1)
    assert set(round(s, 6) for s in samples) <= {0.0, 0.5, 1.0}


def test_summary_improved_needs_lower_bound_above_margin():
    s = summarize(eps([B] * 12 + [P]), {"s1": 1}, iterations=500, calibrated=True)
    assert s.decision == "improved"
    assert s.elo_interval[0] > 0


def test_summary_regressed():
    s = summarize(eps([P] * 12 + [B]), {"s1": 1}, iterations=500, calibrated=True)
    assert s.decision == "regressed"


def test_summary_inconclusive_when_interval_spans_zero():
    s = summarize(eps([B, P] * 6), {"s1": 1}, iterations=500, calibrated=True)
    assert s.decision == "inconclusive"


def test_critical_regression_blocks_positive_recommendation():
    """Numerical quality cannot erase a correctness regression (§1)."""
    s = summarize(eps([B] * 12), {"s1": 1}, critical_regressions=["secret leak"], iterations=300)
    assert s.decision == "blocked"
    assert any("secret leak" in r for r in s.reasons)


def test_low_coverage_prevents_improved():
    s = summarize(eps([B] * 8 + [U] * 8), {"s1": 1}, iterations=300, calibrated=True)
    assert s.decision == "inconclusive"
    assert s.coverage == pytest.approx(0.5)


def test_unresolved_that_could_reverse_direction_is_inconclusive():
    s = summarize(eps([B] * 7 + [P] * 1 + [U] * 9), {"s1": 1}, iterations=300, min_coverage=0.0,
                  calibrated=True)
    assert s.p_pessimistic < 0.5 < s.p_optimistic
    assert s.decision == "inconclusive"


def test_too_few_resolved_is_inconclusive():
    s = summarize(eps([B, B, B]), {"s1": 1}, iterations=100, calibrated=True)
    assert s.decision == "inconclusive"


def test_uncalibrated_judge_always_labeled_advisory():
    s = summarize(eps([B] * 12), {"s1": 1}, iterations=100)
    assert any("advisory" in r for r in s.reasons)


def test_both_failed_and_invalid_excluded_from_rating_and_coverage():
    episodes = eps([B] * 10 + [Outcome.BOTH_FAILED, Outcome.INVALID])
    s = summarize(episodes, {"s1": 1}, iterations=100)
    assert s.coverage == 1.0
    assert s.counts["both_failed"] == 1 and s.counts["invalid"] == 1


def test_summary_json_encodes_infinite_elo_as_strings():
    s = summarize(eps([B] * 10), {"s1": 1}, iterations=100)
    data = s.to_json()
    assert data["elo_delta"] == "+inf"
    assert data["beta_rating"] == "+inf"
