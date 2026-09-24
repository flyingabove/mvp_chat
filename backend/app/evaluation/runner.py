# backend/app/evaluation/runner.py
"""ArenaRunner: paired full-game play (JEV_GAME_ARENA_DESIGN.md §4, §5A, §10).

For each PairSpec, the same player policy/persona/seed plays the same
scenario once against each release, concurrently (equal conditions, no
shared context). Results are persisted per arm; a rerun skips finished
arms, and invalid arms (drift / cancel / evaluator failure) are archived and
replayed under the same pair identity.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from backend.app.evaluation.contracts import (
    BETA, PROD, SIDES, ArmStatus, ArmTranscript, Budget, ObservedState, PairSpec, PersonaSpec,
    ScenarioSpec, TargetIdentity, TurnRecord,
)
from backend.app.evaluation.players import PlayerObservation, PlayerPolicy, build_public_brief
from backend.app.evaluation.store import ArtifactStore
from backend.app.evaluation.targets import TargetAdapter, new_arm_session

RERUN_STATUSES = frozenset({ArmStatus.DRIFT, ArmStatus.CANCELLED, ArmStatus.PLAYER_FAILURE})


def build_pairs(scenarios: Iterable[ScenarioSpec], personas: Iterable[PersonaSpec], replicates: int,
                seed: int) -> list[PairSpec]:
    """Every scenario x persona x replicate. First-side is balanced by
    alternation BEFORE shuffling, then execution order is randomized."""
    rng = random.Random(seed)
    pairs: list[PairSpec] = []
    personas = list(personas)
    i = 0
    for sc in scenarios:
        for persona in personas:
            for rep in range(replicates):
                pairs.append(PairSpec(
                    pair_id=f"{sc.scenario_id}.{persona.id}.r{rep}",
                    scenario=sc, persona=persona, replicate=rep,
                    seed=rng.randrange(1, 2**31 - 1),
                    first_side=BETA if i % 2 == 0 else PROD,
                ))
                i += 1
    rng.shuffle(pairs)
    return pairs


@dataclass
class RunSummary:
    arms_run: int = 0
    arms_skipped: int = 0
    game_turns: int = 0
    statuses: dict[str, int] = field(default_factory=dict)
    stopped_reason: str = ""


class ArenaRunner:
    def __init__(self, *, experiment_id: str, store: ArtifactStore, targets: Mapping[str, TargetAdapter],
                 pinned: Mapping[str, TargetIdentity], player: PlayerPolicy, budget: Budget,
                 concurrency: int = 2) -> None:
        self.experiment_id = experiment_id
        self.store = store
        self.targets = targets
        self.pinned = pinned
        self.player = player
        self.budget = budget
        self.concurrency = concurrency
        self.summary = RunSummary()
        self.started = time.monotonic()
        self.player_tokens = 0
        self.briefs: dict[tuple[str, str], str] = {}

    # ---- budget / cancellation ------------------------------------------
    def stop_reason(self) -> str:
        if self.store.cancel_requested:
            return "cancel requested (STOP file)"
        if self.summary.game_turns >= self.budget.max_game_turns:
            return f"game-turn ceiling {self.budget.max_game_turns} reached"
        if time.monotonic() - self.started > self.budget.max_wall_seconds:
            return f"wall-clock ceiling {self.budget.max_wall_seconds}s reached"
        if self.player_tokens >= self.budget.max_player_tokens:
            return f"player-token ceiling {self.budget.max_player_tokens} reached"
        return ""

    async def brief_for(self, side: str, story_id: str) -> str:
        key = (side, story_id)
        if key not in self.briefs:
            try:
                self.briefs[key] = build_public_brief(await self.targets[side].public_story(story_id))
            except Exception:  # noqa: BLE001 - brief is best-effort public info
                self.briefs[key] = ""
        return self.briefs[key]

    # ---- one arm ---------------------------------------------------------
    async def run_arm(self, pair: PairSpec, side: str) -> ArmTranscript:
        arm_id = pair.arm_id(side)
        existing = self.store.load_arm(arm_id)
        if existing is not None:
            if existing.status not in RERUN_STATUSES:
                self.summary.arms_skipped += 1
                return existing
            self.store.discard_arm(arm_id, existing.status.value)

        target = self.targets[side]
        t0 = time.monotonic()
        pinned = self.pinned[side]

        def finish(status: ArmStatus, detail: str, opening: str = "", opening_obs=None,
                   turns=None, after: TargetIdentity | None = None) -> ArmTranscript:
            arm = ArmTranscript(
                arm_id=arm_id, pair_id=pair.pair_id, side=side, identity_before=pinned,
                identity_after=after, opening=opening, opening_observed=opening_obs or ObservedState(),
                turns=turns or [], status=status, status_detail=detail,
                player_usage={"total_tokens": sum(int(t.usage.get("player_tokens", 0)) for t in turns or [])},
                wall_ms=int((time.monotonic() - t0) * 1000),
            )
            self.store.save_arm(arm)
            self.summary.arms_run += 1
            self.summary.statuses[status.value] = self.summary.statuses.get(status.value, 0) + 1
            self.store.log("arm_finished", arm_id=arm_id, status=status.value, detail=detail, turns=len(arm.turns))
            return arm

        try:
            before = await target.identify()
        except Exception as exc:  # noqa: BLE001
            return finish(ArmStatus.TARGET_FAILURE, f"health check failed: {exc}")
        if before.pin_key != pinned.pin_key:
            return finish(ArmStatus.DRIFT, f"release changed before arm: {pinned.pin_key} -> {before.pin_key}")

        session = new_arm_session(self.experiment_id, arm_id)
        sc = pair.scenario
        opening = await target.start(session, sc.story_id, sc.gender, sc.player_name)
        if opening.error:
            return finish(ArmStatus.TARGET_FAILURE, f"new game failed: {opening.error}")

        brief = await self.brief_for(side, sc.story_id)
        turns: list[TurnRecord] = []
        history: list[tuple[str, str]] = []
        status, detail = ArmStatus.COMPLETE, ""
        for i in range(1, sc.max_player_turns + 1):
            reason = self.stop_reason()
            if reason:
                status, detail = ArmStatus.CANCELLED, reason
                break
            obs = PlayerObservation(brief=brief, persona=pair.persona, opening=opening.reply,
                                    history=history, turn=i, max_turns=sc.max_player_turns)
            move = await self.player.next_move(obs, seed=pair.seed + i)
            ptoks = int(move.usage.get("total_tokens", 0))
            self.player_tokens += ptoks
            if move.error:
                status, detail = ArmStatus.PLAYER_FAILURE, f"player failed at turn {i}: {move.error}"
                break
            request_id = f"{arm_id}.t{i}"
            res = await target.send(session, move.message, request_id)
            self.summary.game_turns += 1
            turns.append(TurnRecord(
                index=i, player_message=move.message, reply=res.reply, request_id=request_id,
                latency_ms=res.latency_ms, speaker_ids=res.speaker_ids, observed=res.observed,
                usage={**{k: v for k, v in res.usage.items() if isinstance(v, (int, float))},
                       "player_tokens": ptoks},
                error=res.error,
            ))
            if res.error:
                status, detail = ArmStatus.TARGET_FAILURE, f"turn {i}: {res.error}"
                break
            history.append((move.message, res.reply))
            if res.game_ended:
                status, detail = ArmStatus.ENDED, f"game ended at turn {i}"
                break

        try:
            after = await target.identify()
        except Exception:  # noqa: BLE001
            after = None
        if after is not None and after.pin_key != pinned.pin_key:
            status, detail = ArmStatus.DRIFT, f"release changed during arm: {pinned.pin_key} -> {after.pin_key}"
        return finish(status, detail, opening.reply, opening.observed, turns, after)

    # ---- pairs -----------------------------------------------------------
    async def run_pair(self, pair: PairSpec) -> tuple[ArmTranscript, ArmTranscript]:
        order = [pair.first_side] + [s for s in SIDES if s != pair.first_side]
        first = asyncio.create_task(self.run_arm(pair, order[0]))
        await asyncio.sleep(0)                       # first_side really starts first
        second = asyncio.create_task(self.run_arm(pair, order[1]))
        a, b = await asyncio.gather(first, second)
        return (a, b) if a.side == BETA else (b, a)

    async def run(self, pairs: list[PairSpec]) -> RunSummary:
        sem = asyncio.Semaphore(self.concurrency)

        async def guarded(pair: PairSpec):
            async with sem:
                reason = self.stop_reason()
                if reason:
                    self.summary.stopped_reason = reason
                    return
                self.store.log("pair_started", pair_id=pair.pair_id)
                await self.run_pair(pair)

        await asyncio.gather(*(guarded(p) for p in pairs))
        if not self.summary.stopped_reason:
            self.summary.stopped_reason = self.stop_reason()
        self.store.log("run_finished", **self.summary.__dict__)
        return self.summary
