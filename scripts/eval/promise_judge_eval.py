"""Measure the Jev promise-completion judge against labeled exchanges. LOCAL ONLY.

Never run this from the Dockerfile, CI, or app startup (it calls live Jev). It uses the exact
production path (promise_judge.ask -> DecisionResolver -> JevClient).

    python -m scripts.eval.promise_judge_eval [--limit N] [--runs K] [--show-misses]

Gate (owner rule, 2026-09-29, relaxed from 1% to 2% the same day): a promise that WAS carried out must
be registered as kept. The miss rate on `done` cases must be <= 2%, and nothing may be "kept" that was not
done. Above that, delete promise tracking and rely on plain conversation context (see
documentation/proposals/PROMISE_COMPLETION_JEV_2026_09_29.md).

The same measurement runs as an automated integration test that deploys never run:
    pytest -m integration tests/backend/integration/test_promise_judge_accuracy.py

Output also reports the reverse error (kept when it was not), which forgets nothing that happened
but would give unearned trust, and the share of unusable answers.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.engine.world_model import promise_judge  # noqa: E402
from backend.app.engine.world_model.model import PLAYER  # noqa: E402

SETS = {"dev": ["promise_judge_cases.json"], "holdout": ["promise_judge_holdout.json"],
        "all": ["promise_judge_cases.json", "promise_judge_holdout.json"]}
DATA = ROOT / "tests" / "data"
GATE = 0.02
RETRY_PAUSES_S = (5.0, 35.0)   # extra passes over calls Jev never answered; the 2nd outlasts the 30s breaker cooldown
NAMES = {PLAYER: "Paul", "riko": "Riko"}


def case_for(item: dict, index: int) -> promise_judge.Case:
    promiser, counterpart = (PLAYER, "riko") if item["promiser"] == "player" else ("riko", PLAYER)
    return promise_judge.Case(f"eval{index}", promiser, counterpart, item["promise"])


def state_for(case: promise_judge.Case, item: dict) -> str:
    return promise_judge.view_text(case, NAMES, None, item["prior_user"], item["prior_reply"], item["message"])


async def run(items: list[dict], concurrency: int = 2) -> list[promise_judge.Ruling]:
    resolver = promise_judge.default_resolver()
    gate = asyncio.Semaphore(concurrency)

    async def one(i: int, item: dict) -> promise_judge.Ruling:
        case = case_for(item, i)
        async with gate:
            return await promise_judge.ask(case, state_for(case, item), resolver)

    return await asyncio.gather(*[one(i, item) for i, item in enumerate(items)])


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a rate: how far the measured miss rate can be trusted at this sample size."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass
class Stats:
    total: int = 0
    done_total: int = 0
    done_missed: int = 0
    done_pending: int = 0          # missed kept promises Jev called "pending" (the risky kind)
    other_total: int = 0
    other_kept: int = 0            # marked kept although not done
    unusable: int = 0
    unreachable: int = 0           # Jev never answered: a transport fact, not a judgment
    confusion: Counter = field(default_factory=Counter)
    misses: list = field(default_factory=list)

    @property
    def miss_rate(self) -> float:
        return self.done_missed / max(1, self.done_total)

    @property
    def passed(self) -> bool:
        return self.miss_rate <= GATE and self.other_kept == 0 and self.unreachable == 0


def load(name: str = "all", limit: int = 0) -> list[dict]:
    items = [row for file in SETS[name] for row in json.loads((DATA / file).read_text(encoding="utf-8"))]
    return items[:limit] if limit else items


def judge_all(items: list[dict], pauses_s: tuple = RETRY_PAUSES_S) -> list[promise_judge.Ruling]:
    """Judge every item; ask again (after a pause) for the ones Jev never answered.

    A transport blip (HTTP error, tripped breaker) says nothing about accuracy, so it must not fail the gate
    when a retry gets a real answer. Whatever is still unanswered after the retries is reported as unreachable.
    """
    rulings = asyncio.run(run(items))
    for pause_s in pauses_s:
        pending = [i for i, r in enumerate(rulings) if r.action == "skip"]
        if not pending:
            break
        time.sleep(pause_s)
        again = asyncio.run(run([items[i] for i in pending]))
        for i, ruling in zip(pending, again):
            rulings[i] = ruling
    return rulings


def measure(items: list[dict], runs: int = 1) -> Stats:
    """Judge every labeled exchange through the production path and tally the two error directions."""
    stats = Stats()
    for _ in range(runs):
        for item, ruling in zip(items, judge_all(items)):
            stats.total += 1
            got = ruling.choice or f"({ruling.action}:{ruling.reason})"
            stats.confusion[(item["label"], got)] += 1
            stats.unusable += ruling.action == "skip" or ruling.choice is None
            if ruling.action == "skip":
                stats.unreachable += 1
                continue
            if item["label"] == "done":
                stats.done_total += 1
                if ruling.action != "kept":
                    stats.done_missed += 1
                    stats.done_pending += ruling.choice == "pending"
                    stats.misses.append((item, got, ruling.confidence))
            else:
                stats.other_total += 1
                stats.other_kept += ruling.action == "kept"
    return stats


def report(stats: Stats, runs: int = 1, show_misses: bool = False) -> None:
    print(f"cases judged: {stats.total} ({runs} run(s))")
    for (label, got), n in sorted(stats.confusion.items()):
        print(f"  labeled {label:9s} -> {got:32s} {n}")
    low, high = wilson(stats.done_missed, stats.done_total)
    print(f"MISSED KEPT PROMISES: {stats.done_missed}/{stats.done_total} = {stats.miss_rate:.1%} "
          f"(95% interval {low:.1%}-{high:.1%}; of which judged 'pending': {stats.done_pending})")
    print(f"kept when it was NOT done: {stats.other_kept}/{stats.other_total} = "
          f"{stats.other_kept / max(1, stats.other_total):.1%}")
    print(f"unusable answers: {stats.unusable}/{stats.total} = {stats.unusable / max(1, stats.total):.1%} "
          f"(unreachable, excluded above: {stats.unreachable})")
    if show_misses:
        for item, got, conf in stats.misses:
            print(f"  MISS [{item['id']}] got={got} conf={conf} | {item['promise']} | {item['message']}")
    print(f"GATE (miss rate <= {GATE:.0%}, nothing wrongly kept, every call answered): "
          f"{'PASS' if stats.passed else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=sorted(SETS), default="all",
                        help="dev = tuned against; holdout = the design was chosen after seeing it, see the proposal")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("TYPESAFE_ENABLED", "true")     # CLI only: importing this module must not change settings
    stats = measure(load(args.set, args.limit), args.runs)
    report(stats, args.runs, args.show_misses)
    return 0 if stats.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
