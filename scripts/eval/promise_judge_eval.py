"""Measure the Jev promise-completion judge against labeled exchanges. LOCAL ONLY.

Never run this from the Dockerfile, CI, or app startup (it calls live Jev). It uses the exact
production path (promise_judge.ask -> DecisionResolver -> JevClient).

    python -m scripts.eval.promise_judge_eval [--limit N] [--runs K] [--show-misses]

Gate (owner rule, 2026-09-29): a promise that WAS carried out must be registered as kept.
The miss rate on `done` cases must be <= 1%. Below that, delete promise tracking and rely on
plain conversation context (see documentation/proposals/PROMISE_COMPLETION_JEV_2026_09_29.md).

Output also reports the reverse error (kept when it was not), which forgets nothing that happened
but would give unearned trust, and the share of unusable answers.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TYPESAFE_ENABLED", "true")

from backend.app.engine.world_model import promise_judge  # noqa: E402
from backend.app.engine.world_model.model import PLAYER  # noqa: E402

SETS = {"dev": ["promise_judge_cases.json"], "holdout": ["promise_judge_holdout.json"],
        "all": ["promise_judge_cases.json", "promise_judge_holdout.json"]}
DATA = ROOT / "tests" / "data"
GATE = 0.01
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=sorted(SETS), default="all",
                        help="dev = tuned against; holdout = never tuned against (the honest number)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args()
    items = [row for name in SETS[args.set] for row in json.loads((DATA / name).read_text(encoding="utf-8"))]
    if args.limit:
        items = items[:args.limit]
    done_total = done_missed = done_pending = other_total = other_kept = unusable = unreachable = total = 0
    confusion: Counter = Counter()
    misses = []
    for _ in range(args.runs):
        for item, ruling in zip(items, asyncio.run(run(items))):
            total += 1
            got = ruling.choice or f"({ruling.action}:{ruling.reason})"
            confusion[(item["label"], got)] += 1
            unusable += ruling.action == "skip" or ruling.choice is None
            if ruling.action == "skip":       # Jev never answered (breaker/HTTP): a transport fact, not a judgment
                unreachable += 1
                continue
            if item["label"] == "done":
                done_total += 1
                if ruling.action != "kept":
                    done_missed += 1
                    done_pending += ruling.choice == "pending"
                    misses.append((item, got, ruling.confidence))
            else:
                other_total += 1
                other_kept += ruling.action == "kept"
    miss_rate = done_missed / max(1, done_total)
    print(f"cases judged: {total} ({args.runs} run(s))")
    for (label, got), n in sorted(confusion.items()):
        print(f"  labeled {label:9s} -> {got:32s} {n}")
    low, high = wilson(done_missed, done_total)
    print(f"MISSED KEPT PROMISES: {done_missed}/{done_total} = {miss_rate:.1%} (95% interval {low:.1%}-{high:.1%}; "
          f"of which judged 'pending': {done_pending})")
    print(f"kept when it was NOT done: {other_kept}/{other_total} = {other_kept / max(1, other_total):.1%}")
    print(f"unusable answers: {unusable}/{total} = {unusable / max(1, total):.1%} (unreachable, excluded above: {unreachable})")
    if args.show_misses:
        for item, got, conf in misses:
            print(f"  MISS [{item['id']}] got={got} conf={conf} | {item['promise']} | {item['message']}")
    ok = miss_rate <= GATE and unreachable == 0
    print(f"GATE (miss rate <= {GATE:.0%}, every call answered): {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
