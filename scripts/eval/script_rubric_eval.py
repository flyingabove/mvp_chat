"""Measure the Jev script rubric against human labels, and build the candidate scenes the owner labels. LOCAL ONLY.

Never run this from the Dockerfile, CI or app startup: `--run` calls live Jev (free, but a network call). It uses
the production path (`sim.rubric.judge_items` -> DecisionResolver -> JevClient).

    python -m scripts.eval.script_rubric_eval --build-candidates     # free: extract scenes from local arena transcripts
    python -m scripts.eval.script_rubric_eval --anchors              # free: print the 1-5 anchors to label against
    python -m scripts.eval.script_rubric_eval --status               # free: how many scenes are labelled
    python -m scripts.eval.script_rubric_eval --run --set dev        # LIVE Jev: agreement per item on labelled scenes

Cases live in tests/eval_cases/script_rubric/{dev,holdout}.json. A case is
`{"id", "source", "setting", "text", "labels"}` where `labels` is null until the owner fills it with
`{"S1": 1-5, ... "S8": 1-5}` (see that folder's README). Tune against `dev` only; `holdout` is read once at the end.

Agreement bar (stated before any label exists, so it cannot be fitted to results): per item, at least `WITHIN_ONE_BAR`
of scenes where Jev is within one point of the human, and at least `VERDICT_BAR` agreement on the scene verdict.
Until `rubric.LABELS_REQUIRED` scenes are labelled the rubric stays advisory (`rubric.CALIBRATED`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.sim import rubric  # noqa: E402

DATA = ROOT / "tests" / "eval_cases" / "script_rubric"
SETS = {"dev": ["dev.json"], "holdout": ["holdout.json"], "all": ["dev.json", "holdout.json"]}
WITHIN_ONE_BAR = 0.80
VERDICT_BAR = 0.70
SCENE_ITEMS = [item.id for item in rubric.items_for("scene")]
ARENA_GLOB = "arena_six*/arms/*.json"
NL = "\n"
REPLY_CHARS = (400, 2200)      # shorter is a stub, longer is clipped away by the rubric view anyway


def load(name: str = "all") -> list[dict]:
    return [row for file in SETS[name] for row in json.loads((DATA / file).read_text(encoding="utf-8"))]


def labelled(cases: list[dict]) -> list[dict]:
    return [c for c in cases if isinstance(c.get("labels"), dict) and all(
        isinstance(c["labels"].get(i), int) and 1 <= c["labels"][i] <= 5 for i in SCENE_ITEMS)]


def human_verdict(labels: dict) -> str:
    scores = [2 * labels[i] for i in SCENE_ITEMS]
    return rubric.verdict_for(sum(scores) / len(scores), min(scores), 2 * labels[rubric.PLAUSIBILITY_ITEM])


# ------------------------------------------------------------------------------------------- build candidates
def build_candidates(source: Path, dev: int = 40, holdout: int = 20, seed: int = 20261001) -> tuple[list, list]:
    """Unlabelled scenes from real hosted-Terrace transcripts (one player line plus the storyteller's reply),
    spread across runs (at most two per transcript) and shuffled with a fixed seed."""
    rng = random.Random(seed)
    pool, seen = [], set()
    for path in sorted(source.glob(ARENA_GLOB)):
        arm = json.loads(path.read_text(encoding="utf-8"))
        turns = [t for t in arm.get("turns", []) if REPLY_CHARS[0] <= len(str(t.get("reply") or "")) <= REPLY_CHARS[1]
                 and not t.get("error")]
        rng.shuffle(turns)
        for turn in turns[:2]:
            reply = str(turn["reply"]).strip()
            if reply in seen:
                continue
            seen.add(reply)
            pool.append({"id": f"{path.parent.parent.name}.{arm['arm_id']}.t{turn['index']}", "source": f"arena:{path.parent.parent.name}:{arm['arm_id']}:turn{turn['index']}",
                         "setting": "a shared house where strangers live together under cameras",
                         "text": f"Player: {str(turn.get('player_message') or '').strip()}\n\n{reply}", "labels": None})
    rng.shuffle(pool)
    if len(pool) < dev + holdout:
        raise SystemExit(f"only {len(pool)} candidate scenes under {source}; need {dev + holdout}")
    return pool[:dev], pool[dev:dev + holdout]


def anchor_sheet() -> str:
    """The scene items with their five anchors, exactly as Jev is asked, for the owner to label against."""
    blocks = []
    for item in rubric.items_for("scene"):
        lines = [f"{item.id}  {item.title}", f"    {item.question}"]
        lines += [f"    {n}  {anchor}" for n, anchor in enumerate(item.anchors, 1)]
        blocks.append(NL.join(lines))
    return (NL + NL).join(blocks)


# --------------------------------------------------------------------------------------------- measurement
@dataclass
class Agreement:
    scenes: int = 0
    unanswered: int = 0
    exact: dict = field(default_factory=lambda: {i: 0 for i in SCENE_ITEMS})
    within_one: dict = field(default_factory=lambda: {i: 0 for i in SCENE_ITEMS})
    answered: dict = field(default_factory=lambda: {i: 0 for i in SCENE_ITEMS})
    verdict_match: int = 0
    verdict_scored: int = 0

    def rate(self, table: dict, item: str) -> Optional[float]:
        return table[item] / self.answered[item] if self.answered[item] else None

    @property
    def verdict_rate(self) -> Optional[float]:
        return self.verdict_match / self.verdict_scored if self.verdict_scored else None

    def passes(self) -> bool:
        """The stated bar on every item AND on the verdict; an item nobody could answer fails it."""
        rates = [self.rate(self.within_one, i) for i in SCENE_ITEMS]
        return all(r is not None and r >= WITHIN_ONE_BAR for r in rates) \
            and self.verdict_rate is not None and self.verdict_rate >= VERDICT_BAR


def tally(cases: list[dict], results: list[rubric.LevelScore]) -> Agreement:
    out = Agreement()
    for case, result in zip(cases, results):
        out.scenes += 1
        got = {i.item_id: i.choice for i in result.items}
        for item in SCENE_ITEMS:
            if got.get(item) is None:
                out.unanswered += 1
                continue
            human = case["labels"][item]
            out.answered[item] += 1
            out.exact[item] += got[item] == human
            out.within_one[item] += abs(got[item] - human) <= 1
        if result.complete:
            out.verdict_scored += 1
            out.verdict_match += result.verdict == human_verdict(case["labels"])
    return out


async def judge_cases(cases: list[dict], concurrency: int = 2) -> list[rubric.LevelScore]:
    gate = asyncio.Semaphore(concurrency)

    async def one(case: dict) -> rubric.LevelScore:
        async with gate:
            return await rubric.judge_level("scene", rubric.scene_view(case["text"], case.get("setting", "")))

    return list(await asyncio.gather(*[one(c) for c in cases]))


def report(agreement: Agreement, label: str) -> None:
    print(f"{label}: {agreement.scenes} labelled scene(s); unanswered item calls: {agreement.unanswered}")
    for item in SCENE_ITEMS:
        exact, near = agreement.rate(agreement.exact, item), agreement.rate(agreement.within_one, item)
        fmt = lambda v: "n/a" if v is None else f"{v:.0%}"
        flag = "" if near is not None and near >= WITHIN_ONE_BAR else "   <-- below bar"
        print(f"  {item} {rubric.BY_ID[item].title:32s} exact {fmt(exact):>4}  within one {fmt(near):>4}{flag}")
    rate = agreement.verdict_rate
    print(f"  verdict agreement {'n/a' if rate is None else f'{rate:.0%}'} (bar {VERDICT_BAR:.0%}); "
          f"per-item within-one bar {WITHIN_ONE_BAR:.0%}")
    print(f"BAR: {'MET' if agreement.passes() else 'NOT MET'} (advisory until {rubric.LABELS_REQUIRED} scenes are labelled)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=sorted(SETS), default="dev")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build-candidates", action="store_true", help="free; writes unlabelled dev.json/holdout.json")
    mode.add_argument("--anchors", action="store_true", help="free; prints every scene item with its five anchors")
    mode.add_argument("--status", action="store_true", help="free; counts labelled scenes")
    mode.add_argument("--run", action="store_true", help="LIVE Jev (free): agreement on the labelled scenes")
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "eval_arena")
    args = parser.parse_args()
    if args.build_candidates:
        existing = [f for f in ("dev.json", "holdout.json") if (DATA / f).exists()]
        if existing:
            raise SystemExit(f"{existing} already exist: refusing to overwrite (labels would be lost). Delete them first.")
        dev, holdout = build_candidates(args.source)
        DATA.mkdir(parents=True, exist_ok=True)
        for name, rows in (("dev.json", dev), ("holdout.json", holdout)):
            (DATA / name).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {len(dev)} dev and {len(holdout)} holdout candidate scenes under {DATA}")
        return 0
    if args.anchors:
        print(anchor_sheet())
        return 0
    cases = load(args.set)
    ready = labelled(cases)
    if args.status:
        print(f"{len(ready)}/{len(cases)} scenes labelled in '{args.set}' (rubric needs {rubric.LABELS_REQUIRED} overall)")
        return 0
    if not ready:
        raise SystemExit("no labelled scenes yet: fill `labels` in the case files first (see the folder README)")
    os.environ.setdefault("TYPESAFE_ENABLED", "true")     # CLI only: importing this module must not change settings
    report(tally(ready, asyncio.run(judge_cases(ready))), args.set)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
