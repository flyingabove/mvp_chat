# backend/app/evaluation/pipeline.py
"""Judge pipeline: arms -> windows -> order-swapped judgments -> votes ->
episode outcome (JEV_GAME_ARENA_DESIGN.md §5A, §7, §8).

Order swap: every window is judged twice in SEPARATE requests (beta shown
as A, then prod shown as A). A dimension vote is resolved only when both
orders agree after remapping; otherwise it is unresolved. The two orders are
one measurement, not two samples.

Reliability policy (§8): a genuine target-side failure on one arm makes the
episode a loss for that release; both failing is reported as both_failed;
evaluator-side problems (drift, cancel, player failure, judge failure) are
never scored as anyone's win.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from backend.app.evaluation.aggregate import EpisodeOutcome, Vote, decide_episode
from backend.app.evaluation.checks import DEFAULT_CHECKS, CorrectnessCheck, run_checks
from backend.app.evaluation.contracts import (
    BETA, PROD, ArmStatus, ArmTranscript, Outcome, PairSpec,
)
from backend.app.evaluation.evidence import build_packet, window_count
from backend.app.evaluation.judge import (
    JudgeCall, PairwiseJudge, cmp_id, evidence_id, probe_id, score_id,
)
from backend.app.evaluation.knowledge import GameKnowledgeBundle
from backend.app.evaluation.rubric import Rubric
from backend.app.evaluation.store import ArtifactStore

ORIENTATIONS = {
    "beta_as_A": {"A": BETA, "B": PROD},
    "prod_as_A": {"A": PROD, "B": BETA},
}
VOTE_VALUE = {BETA: 1.0, "tie": 0.5, PROD: 0.0}


def remap_choice(choice: str | None, mapping: Mapping[str, str]) -> str | None:
    if choice in ("A", "B"):
        return mapping[choice]
    return choice


def letter_for(side: str, mapping: Mapping[str, str]) -> str:
    return next(k for k, v in mapping.items() if v == side)


def reconcile_dimension(dim_id: str, calls: Mapping[str, JudgeCall]) -> tuple[float | None, str, dict]:
    """Returns (vote value or None, reason, per-order detail)."""
    detail: dict[str, Any] = {}
    remapped = []
    for orientation, call in calls.items():
        if call.failed or call.error.startswith("model_mismatch"):
            return None, f"judge_failure:{call.error[:80]}", detail
        ans = call.answer(cmp_id(dim_id))
        if not ans.valid:
            return None, f"invalid:{ans.reason}", detail
        release = remap_choice(ans.choice, ORIENTATIONS[orientation])
        detail[orientation] = {"choice": ans.choice, "release": release, "confidence": ans.confidence,
                               "probabilities": ans.probabilities}
        remapped.append(release)
    if "insufficient_evidence" in remapped:
        return None, "insufficient_evidence", detail
    if len(set(remapped)) != 1:
        return None, "order_disagreement", detail
    return VOTE_VALUE[remapped[0]], "resolved", detail


def side_scores(dim_id: str, calls: Mapping[str, JudgeCall]) -> dict[str, float | None]:
    """Diagnostic 0-4 bands averaged over both orders, per release."""
    out: dict[str, float | None] = {}
    for side in (BETA, PROD):
        vals = []
        for orientation, call in calls.items():
            ans = call.answer(score_id(letter_for(side, ORIENTATIONS[orientation]), dim_id))
            if ans.valid and ans.score is not None:
                vals.append(ans.score)
        out[side] = sum(vals) / len(vals) if vals else None
    return out


def evidence_spans(dim_id: str, calls: Mapping[str, JudgeCall]) -> list[dict]:
    """Selected span IDs remapped to (release, turn, kind) for drill-down."""
    out = []
    for orientation, call in calls.items():
        ans = call.answer(evidence_id(dim_id))
        if not ans.valid or not ans.choice or ans.choice == "none":
            continue
        letter, rest = ans.choice[0], ans.choice[1:]
        kind = "player" if rest.endswith("p") else "game"
        turn = int(rest.rstrip("pr") or 0)
        out.append({"orientation": orientation, "release": ORIENTATIONS[orientation][letter],
                    "turn": turn, "kind": kind})
    return out


def probe_results(rubric: Rubric, calls: Mapping[str, JudgeCall]) -> dict[str, dict[str, Any]]:
    """Confirmed = probability >= threshold in BOTH orders; disputed = one."""
    results: dict[str, dict[str, Any]] = {}
    for probe in rubric.critical_probes:
        for side in (BETA, PROD):
            readings = []
            for orientation, call in calls.items():
                ans = call.answer(probe_id(letter_for(side, ORIENTATIONS[orientation]), probe.id))
                readings.append(ans.probability if ans.valid else None)
            hits = [r is not None and r >= rubric.critical_threshold for r in readings]
            results.setdefault(probe.id, {})[side] = {
                "readings": readings,
                "confirmed": all(hits) and len(hits) == 2,
                "disputed": any(hits) and not all(hits),
            }
    return results


@dataclass
class ArmsJudgment:
    votes: list[Vote]
    windows: list[dict[str, Any]]
    calls: list[JudgeCall]


async def judge_arms(bundle: GameKnowledgeBundle, beta_arm: ArmTranscript, prod_arm: ArmTranscript,
                     judge: PairwiseJudge, rubric: Rubric, window_turns: int,
                     windows: Sequence[int] | None = None,
                     semaphore: asyncio.Semaphore | None = None) -> ArmsJudgment:
    """Judge every window of two arms in both orders. Reused by calibration
    (with an original arm in the beta slot and a mutant in the prod slot)."""
    sem = semaphore or asyncio.Semaphore(4)
    n = window_count(beta_arm, prod_arm, window_turns)
    indices = list(windows) if windows is not None else list(range(n))

    async def one(w: int, orientation: str) -> JudgeCall:
        a, b = (beta_arm, prod_arm) if orientation == "beta_as_A" else (prod_arm, beta_arm)
        packet = build_packet(bundle, a, b, w, window_turns)
        async with sem:
            return await judge.judge(packet, orientation=orientation)

    tasks = {(w, o): asyncio.create_task(one(w, o)) for w in indices for o in ORIENTATIONS}
    done = {k: await t for k, t in tasks.items()}

    votes: list[Vote] = []
    window_rows: list[dict[str, Any]] = []
    for w in indices:
        calls = {o: done[(w, o)] for o in ORIENTATIONS}
        row: dict[str, Any] = {"window": w, "dimensions": {}, "probes": probe_results(rubric, calls)}
        for dim in rubric.dimensions:
            value, reason, detail = reconcile_dimension(dim.id, calls)
            votes.append(Vote(dim.id, w, dim.weight / len(indices), value))
            row["dimensions"][dim.id] = {
                "value": value, "reason": reason, "orders": detail,
                "scores": side_scores(dim.id, calls), "evidence": evidence_spans(dim.id, calls),
            }
        window_rows.append(row)
    return ArmsJudgment(votes=votes, windows=window_rows, calls=list(done.values()))


class JudgePipeline:
    def __init__(self, *, store: ArtifactStore, bundles: Mapping[str, GameKnowledgeBundle],
                 judge: PairwiseJudge, rubric: Rubric, window_turns: int,
                 checks: tuple[CorrectnessCheck, ...] = DEFAULT_CHECKS, concurrency: int = 4,
                 max_judge_input_tokens: int = 5_000_000) -> None:
        self.store = store
        self.bundles = bundles
        self.judge = judge
        self.rubric = rubric
        self.window_turns = window_turns
        self.checks = checks
        self.sem = asyncio.Semaphore(concurrency)
        self.max_tokens = max_judge_input_tokens
        self.tokens_used = 0

    async def judge_pair(self, pair: PairSpec, *, force: bool = False) -> dict[str, Any]:
        cached = None if force else self.store.load_judgment(pair.pair_id)
        if cached is not None:
            return cached
        bundle = self.bundles[pair.scenario.story_id]
        arms = {side: self.store.load_arm(pair.arm_id(side)) for side in (BETA, PROD)}
        base = {
            "pair_id": pair.pair_id, "story_id": pair.scenario.story_id,
            "scenario_id": pair.scenario.scenario_id, "persona": pair.persona.id,
            "replicate": pair.replicate, "first_side": pair.first_side,
        }
        if any(a is None for a in arms.values()):
            return {**base, "outcome": Outcome.INVALID.value, "reason": "missing arm"}

        checks = {side: [f.to_json() for f in run_checks(arm, bundle, self.checks)] for side, arm in arms.items()}
        statuses = {side: arm.status for side, arm in arms.items()}
        base.update({"statuses": {s: v.value for s, v in statuses.items()}, "checks": checks,
                     "status_detail": {s: a.status_detail for s, a in arms.items()}})

        invalid = [s for s, st in statuses.items()
                   if st in (ArmStatus.DRIFT, ArmStatus.CANCELLED, ArmStatus.PLAYER_FAILURE)]
        if invalid:
            result = {**base, "outcome": Outcome.INVALID.value, "reason": f"invalid arm(s): {invalid}"}
            self.store.save_judgment(pair.pair_id, result)
            return result
        failed = [s for s, st in statuses.items() if st is ArmStatus.TARGET_FAILURE]
        if failed:
            outcome = (Outcome.BOTH_FAILED if len(failed) == 2
                       else Outcome.PROD_WIN if failed[0] == BETA else Outcome.BETA_WIN)
            result = {**base, "outcome": outcome.value, "reason": f"target failure: {failed}"}
            self.store.save_judgment(pair.pair_id, result)
            return result

        if self.tokens_used >= self.max_tokens:
            return {**base, "outcome": Outcome.UNRESOLVED.value, "reason": "judge token budget exhausted"}

        judged = await judge_arms(bundle, arms[BETA], arms[PROD], self.judge, self.rubric,
                                  self.window_turns, semaphore=self.sem)
        self.tokens_used += sum(c.input_tokens for c in judged.calls)
        decision = decide_episode(judged.votes, self.rubric.win_margin)
        result = {
            **base,
            "outcome": decision.outcome.value,
            "episode_vote": {"point": decision.point, "low": decision.low, "high": decision.high,
                             "coverage": decision.coverage},
            "windows": judged.windows,
            "judge_calls": [{
                "window": c.window_index, "orientation": c.orientation, "model": c.model,
                "attempts": c.attempts, "input_tokens": c.input_tokens, "latency_ms": c.latency_ms,
                "error": c.error, "estimated_state_tokens": c.estimated_state_tokens,
                "invalid_answers": {k: v.reason for k, v in c.answers.items() if not v.valid},
            } for c in judged.calls],
        }
        # Judge infra failures stay unresolved and are never cached as final,
        # so a rerun retries them against the same stored transcripts.
        if not any(c.failed for c in judged.calls):
            self.store.save_judgment(pair.pair_id, result)
        return result

    async def run(self, pairs: Sequence[PairSpec], *, force: bool = False) -> list[dict[str, Any]]:
        return list(await asyncio.gather(*(self.judge_pair(p, force=force) for p in pairs)))


def episode_outcomes(results: Sequence[Mapping[str, Any]]) -> list[EpisodeOutcome]:
    return [EpisodeOutcome(r["pair_id"], r["story_id"], r["scenario_id"], Outcome(r["outcome"]))
            for r in results]
