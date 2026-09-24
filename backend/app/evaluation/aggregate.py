# backend/app/evaluation/aggregate.py
"""Pure rating statistics (JEV_GAME_ARENA_DESIGN.md §8). No I/O.

Units: one independent observation is a paired scenario replicate (an
episode), never a turn, a question or an order swap.

  vote          beta win = 1, tie = 0.5, prod win = 0 (per dimension/window)
  episode       weighted vote -> beta / prod / tie via a declared margin;
                unresolved if unresolved votes could flip the category
  p             stratified match score over resolved episodes
  delta         400 * log10(p / (1 - p)) Elo-equivalent vs the prod anchor
  interval      percentile bootstrap resampling scenario clusters in strata

Jev confidence is never converted into Elo or a win probability.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Iterable, Mapping, Sequence

from backend.app.evaluation.contracts import Outcome

PROD_ANCHOR = 1000.0


@dataclass(frozen=True)
class Vote:
    dimension: str
    window_index: int
    weight: float
    value: float | None          # None = unresolved


@dataclass(frozen=True)
class EpisodeDecision:
    outcome: Outcome
    point: float | None          # resolved-only weighted vote
    low: float                   # all unresolved -> prod
    high: float                  # all unresolved -> beta
    coverage: float              # resolved weight / total weight


def classify(value: float, margin: float) -> Outcome:
    if value > margin:
        return Outcome.BETA_WIN
    if value < 1.0 - margin:
        return Outcome.PROD_WIN
    return Outcome.TIE


def decide_episode(votes: Sequence[Vote], margin: float) -> EpisodeDecision:
    total = sum(v.weight for v in votes)
    if total <= 0:
        return EpisodeDecision(Outcome.UNRESOLVED, None, 0.0, 1.0, 0.0)
    resolved = [v for v in votes if v.value is not None]
    resolved_w = sum(v.weight for v in resolved)
    got = sum(v.weight * v.value for v in resolved)
    unresolved_w = total - resolved_w
    low, high = got / total, (got + unresolved_w) / total
    point = got / resolved_w if resolved_w > 0 else None
    lo_cat, hi_cat = classify(low, margin), classify(high, margin)
    outcome = lo_cat if lo_cat == hi_cat else Outcome.UNRESOLVED
    return EpisodeDecision(outcome, point, low, high, resolved_w / total)


@dataclass(frozen=True)
class EpisodeOutcome:
    pair_id: str
    stratum: str                 # story id
    cluster: str                 # scenario id (replicates share it)
    outcome: Outcome


RESOLVED = {Outcome.BETA_WIN: 1.0, Outcome.TIE: 0.5, Outcome.PROD_WIN: 0.0}


def elo_delta(p: float) -> float:
    """Unbounded at p = 0 / 1 (reported as -inf / +inf, never clamped)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    return 400.0 * math.log10(p / (1.0 - p))


def stratified_p(episodes: Iterable[EpisodeOutcome], weights: Mapping[str, float]) -> float | None:
    by_stratum: dict[str, list[float]] = defaultdict(list)
    for ep in episodes:
        if ep.outcome in RESOLVED:
            by_stratum[ep.stratum].append(RESOLVED[ep.outcome])
    num = den = 0.0
    for stratum, values in by_stratum.items():
        w = weights.get(stratum, 1.0)
        num += w * (sum(values) / len(values))
        den += w
    return num / den if den > 0 else None


def reassign_unresolved(episodes: Sequence[EpisodeOutcome], to: Outcome) -> list[EpisodeOutcome]:
    return [EpisodeOutcome(e.pair_id, e.stratum, e.cluster, to) if e.outcome is Outcome.UNRESOLVED else e
            for e in episodes]


def bootstrap_p(episodes: Sequence[EpisodeOutcome], weights: Mapping[str, float], *,
                iterations: int = 2000, seed: int = 0) -> list[float]:
    """Resample scenario clusters (with all their replicates) within each
    stratum, so replicates of one authored scenario don't fake precision."""
    rng = random.Random(seed)
    strata: dict[str, dict[str, list[EpisodeOutcome]]] = defaultdict(lambda: defaultdict(list))
    for ep in episodes:
        strata[ep.stratum][ep.cluster].append(ep)
    samples: list[float] = []
    for _ in range(iterations):
        drawn: list[EpisodeOutcome] = []
        for clusters in strata.values():
            keys = sorted(clusters)
            for _k in keys:
                drawn.extend(clusters[rng.choice(keys)])
        p = stratified_p(drawn, weights)
        if p is not None:
            samples.append(p)
    return samples


def percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return math.nan
    idx = min(len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[idx]


@dataclass
class RatingSummary:
    n_pairs: int
    counts: dict[str, int]
    p: float | None
    elo_delta: float | None
    beta_rating: float | None
    p_interval: tuple[float, float] | None
    elo_interval: tuple[float, float] | None
    p_pessimistic: float | None
    p_optimistic: float | None
    coverage: float
    decision: str
    reasons: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        def fin(x):
            if isinstance(x, (tuple, list)):
                return [fin(v) for v in x]
            if isinstance(x, float) and not math.isfinite(x):
                return "+inf" if x > 0 else "-inf"
            return x
        data = asdict(self)
        return {k: fin(v) for k, v in data.items()}


def summarize(episodes: Sequence[EpisodeOutcome], weights: Mapping[str, float], *,
              critical_regressions: Sequence[str] = (), practical_margin_elo: float = 0.0,
              min_coverage: float = 0.8, min_resolved: int = 6, iterations: int = 2000,
              seed: int = 0, calibrated: bool = False) -> RatingSummary:
    counts = {o.value: 0 for o in Outcome}
    for ep in episodes:
        counts[ep.outcome.value] += 1
    scored = [e for e in episodes if e.outcome not in (Outcome.INVALID, Outcome.BOTH_FAILED)]
    resolved = [e for e in scored if e.outcome in RESOLVED]
    coverage = len(resolved) / len(scored) if scored else 0.0

    p = stratified_p(resolved, weights)
    samples = sorted(bootstrap_p(resolved, weights, iterations=iterations, seed=seed)) if resolved else []
    p_int = (percentile(samples, 0.025), percentile(samples, 0.975)) if samples else None
    elo_int = (elo_delta(p_int[0]), elo_delta(p_int[1])) if p_int else None
    p_pes = stratified_p(reassign_unresolved(scored, Outcome.PROD_WIN), weights)
    p_opt = stratified_p(reassign_unresolved(scored, Outcome.BETA_WIN), weights)

    reasons: list[str] = []
    decision = "inconclusive"
    if p is None or len(resolved) < min_resolved:
        reasons.append(f"only {len(resolved)} resolved paired episodes (minimum {min_resolved})")
    elif elo_int[0] > practical_margin_elo:
        decision = "improved"
    elif elo_int[1] < -practical_margin_elo:
        decision = "regressed"
    else:
        reasons.append("confidence interval includes the practical margin")
    if decision != "inconclusive" and p_pes is not None and p_opt is not None:
        if (elo_delta(p_pes) > 0) != (elo_delta(p_opt) > 0):
            reasons.append("unresolved episodes could reverse the direction")
            decision = "inconclusive"
    if coverage < min_coverage:
        reasons.append(f"coverage {coverage:.0%} below required {min_coverage:.0%}")
        if decision == "improved":
            decision = "inconclusive"
    if critical_regressions:
        # Numerical quality can never erase a correctness regression (§1).
        reasons.append("critical regression: " + "; ".join(critical_regressions))
        if decision == "improved":
            decision = "blocked"
    if not calibrated:
        reasons.append("judge not yet calibrated against human labels: advisory only")

    delta = elo_delta(p) if p is not None else None
    return RatingSummary(
        n_pairs=len(episodes), counts=counts, p=p, elo_delta=delta,
        beta_rating=(PROD_ANCHOR + delta) if delta is not None else None,
        p_interval=p_int, elo_interval=elo_int, p_pessimistic=p_pes, p_optimistic=p_opt,
        coverage=coverage, decision=decision, reasons=reasons,
    )


def release_gate(strata_p_by_judge: Mapping[str, Mapping[str, float | None]],
                 games: Sequence[str], critical_regressions: Sequence[str] = ()) -> dict:
    """Promotion gate agreed 2026-09-24: for EVERY game, beta must win (match
    score > 50%) under AT LEAST ONE judge, and no critical regression may
    exist under any judge. Deliberately a point-estimate rule for a cheap
    gate profile; the per-judge intervals in the report say how firm it is."""
    per_game: dict[str, dict] = {}
    reasons: list[str] = []
    for game in games:
        scores = {judge: strata.get(game) for judge, strata in strata_p_by_judge.items()}
        winners = sorted(j for j, p in scores.items() if p is not None and p > 0.5)
        per_game[game] = {"match_score_by_judge": scores, "beta_wins_under": winners, "passed": bool(winners)}
        if not winners:
            reasons.append(f"{game}: beta did not win under any judge")
    if critical_regressions:
        reasons.append("critical regression: " + "; ".join(critical_regressions))
    passed = all(g["passed"] for g in per_game.values()) and not critical_regressions and bool(per_game)
    if not per_game:
        reasons.append("no games were judged")
    return {"passed": passed, "rule": "each game won by beta under at least one judge; no critical regression",
            "per_game": per_game, "reasons": reasons}
