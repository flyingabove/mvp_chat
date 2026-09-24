# backend/app/evaluation/cli.py
"""Arena command line (thin wrapper: scripts/eval/arena.py).

  run        preflight both releases, freeze the manifest, play paired games
  judge      judge every finished pair (cached; judge failures retried)
  calibrate  mutation/A-A sensitivity on recorded arms
  report     aggregate -> report.json + report.html
  all        run + judge + calibrate + report

Experiments are resumable: rerunning any command with the same
--experiment-id continues from the stored artifacts. A different manifest
under the same id is refused.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

from backend.app.evaluation.calibration import CALIBRATION_VERSION, run_calibration
from backend.app.evaluation.contracts import (
    BETA, PROD, Budget, ExperimentManifest, ExperimentMode, TargetIdentity, from_dict,
)
from backend.app.evaluation.judge import DEFAULT_JUDGE_MODEL, JevPairwiseJudge
from backend.app.evaluation.knowledge import load_bundles
from backend.app.evaluation.pipeline import JudgePipeline
from backend.app.evaluation.players import PERSONAS, PLAYER_PROMPT_VERSION, LLMPlayer
from backend.app.evaluation.report import build_report, render_html
from backend.app.evaluation.rubric import DEFAULT_RUBRIC
from backend.app.evaluation.runner import ArenaRunner, build_pairs
from backend.app.evaluation.store import ArtifactStore, default_root
from backend.app.evaluation.suite import SUITE_VERSION, default_scenarios
from backend.app.evaluation.targets import HostedTargetAdapter

DEFAULT_URLS = {BETA: "https://beta-api.storieschat.ai", PROD: "https://storieschat.ai"}


def say(msg: str) -> None:
    print(f"[arena {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def evaluator_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def targets_for(args, client: httpx.AsyncClient) -> dict[str, HostedTargetAdapter]:
    return {BETA: HostedTargetAdapter(BETA, args.beta_url, client),
            PROD: HostedTargetAdapter(PROD, args.prod_url, client)}


async def preflight(targets) -> tuple[dict[str, TargetIdentity], dict[str, dict]]:
    ids, caps = {}, {}
    for side, t in targets.items():
        ident = await t.identify()
        ids[side] = ident
        caps[side] = await t.capabilities()
        say(f"{side}: {ident.base_url} commit={ident.commit[:12]} deployment={ident.deployment_id[:12] or '-'} "
            f"env={ident.environment} pinnable={ident.is_pinnable} "
            f"capabilities={caps[side].get('contract_version') or 'none (observational only)'}")
    return ids, caps


def build_manifest(args, ids: dict[str, TargetIdentity], caps: dict[str, dict]) -> ExperimentManifest:
    scenarios = [s for s in default_scenarios(args.turns) if not args.stories or s.story_id in args.stories]
    personas = [PERSONAS[p] for p in (args.personas or list(PERSONAS))]
    pairs = build_pairs(scenarios, personas, args.replicates, args.seed)
    if args.max_pairs:
        pairs = pairs[:args.max_pairs]
    bundles = load_bundles(sorted({s.story_id for s in scenarios}))
    notes = [
        f"suite {SUITE_VERSION}",
        "observational: public /api/chat + player-facing [D] debug box; no server receipts/snapshots, "
        "so capacity/RNG/state-transition checks are not measured",
        "content judged against the evaluator checkout's authored story files; if prod content differs "
        "this is a product comparison, not an engine comparison",
    ]
    for side, ident in ids.items():
        if not ident.is_pinnable:
            notes.append(f"{side} reports no commit or deployment id: release drift cannot be detected")
    return ExperimentManifest(
        experiment_id=args.experiment_id,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        mode=ExperimentMode.AS_DEPLOYED_PRODUCT.value,
        targets={k: v.__dict__ for k, v in ids.items()},
        judge_model=args.judge_model,
        rubric_version=DEFAULT_RUBRIC.version,
        rubric_hash=DEFAULT_RUBRIC.rubric_hash,
        evaluator_commit=evaluator_commit(),
        player_model=args.player_model,
        player_prompt_version=PLAYER_PROMPT_VERSION,
        knowledge_bundles={k: b.bundle_hash for k, b in bundles.items()},
        pairs=[{"pair_id": p.pair_id, "scenario": p.scenario.__dict__, "persona": p.persona.__dict__,
                "replicate": p.replicate, "seed": p.seed, "first_side": p.first_side} for p in pairs],
        seed=args.seed,
        window_turns=args.window_turns,
        budget=Budget(
            # 0 = exactly enough for every arm's horizon (2 arms per pair); a
            # fixed default silently starved the last pairs of the first pilot.
            max_game_turns=args.max_game_turns or 2 * sum(p.scenario.max_player_turns for p in pairs),
            max_wall_seconds=args.max_wall_seconds,
        ).__dict__,
        capabilities=caps,
        notes=tuple(notes),
    )


async def cmd_run(args) -> None:
    from backend.app.config.settings import OPENAI_API_KEY

    store = ArtifactStore(args.root, args.experiment_id)
    async with httpx.AsyncClient() as client:
        targets = targets_for(args, client)
        ids, caps = await preflight(targets)
        if store.manifest_path.exists():
            manifest = store.load_manifest()
            pinned = {k: from_dict(TargetIdentity, v) for k, v in manifest.targets.items()}
            for side in (BETA, PROD):
                if pinned[side].pin_key != ids[side].pin_key:
                    raise SystemExit(f"{side} changed since this experiment started "
                                     f"({pinned[side].pin_key} -> {ids[side].pin_key}); start a new experiment id")
            say(f"resuming {args.experiment_id}")
        else:
            manifest = build_manifest(args, ids, caps)
            store.save_manifest(manifest)
            pinned = ids
            say(f"manifest {manifest.manifest_hash[:12]} with {len(manifest.pairs)} pairs")
        player = LLMPlayer(client, api_key=OPENAI_API_KEY, model=manifest.player_model)
        budget = Budget(**manifest.budget)
        runner = ArenaRunner(experiment_id=args.experiment_id, store=store, targets=targets, pinned=pinned,
                             player=player, budget=budget, concurrency=args.concurrency)
        summary = await runner.run(manifest.pair_specs())
        say(f"play finished: {summary.__dict__}")


def jev_judge(client: httpx.AsyncClient, model: str) -> JevPairwiseJudge:
    from backend.app.config.settings import TYPESAFE_API_KEY
    from backend.app.llm.providers.jev import JevClient

    if not TYPESAFE_API_KEY:
        raise SystemExit("TYPESAFE_API_KEY is not configured (.env.test or environment)")
    return JevPairwiseJudge(JevClient(client, api_key=TYPESAFE_API_KEY, model=model), DEFAULT_RUBRIC, model=model)


async def cmd_judge(args) -> None:
    store = ArtifactStore(args.root, args.experiment_id)
    manifest = store.load_manifest()
    pairs = manifest.pair_specs()
    bundles = load_bundles(sorted({p.scenario.story_id for p in pairs}))
    async with httpx.AsyncClient() as client:
        pipe = JudgePipeline(store=store, bundles=bundles, judge=jev_judge(client, manifest.judge_model),
                             rubric=DEFAULT_RUBRIC, window_turns=manifest.window_turns,
                             concurrency=args.judge_concurrency,
                             max_judge_input_tokens=manifest.budget.get("max_judge_input_tokens", 5_000_000))
        results = await pipe.run(pairs, force=args.force)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    say(f"judged {len(results)} pairs: {counts}; judge input tokens this pass {pipe.tokens_used:,}")


async def cmd_calibrate(args) -> None:
    store = ArtifactStore(args.root, args.experiment_id)
    manifest = store.load_manifest()
    pairs = manifest.pair_specs()
    bundles = load_bundles(sorted({p.scenario.story_id for p in pairs}))
    picked, seen_stories = [], {}
    for p in pairs:
        arm = store.load_arm(p.arm_id(BETA))
        if arm and arm.scorable and len(arm.turns) >= 2 and seen_stories.get(p.scenario.story_id, 0) < args.calibration_arms:
            picked.append((bundles[p.scenario.story_id], arm))
            seen_stories[p.scenario.story_id] = seen_stories.get(p.scenario.story_id, 0) + 1
    async with httpx.AsyncClient() as client:
        result = await run_calibration(picked, jev_judge(client, manifest.judge_model), DEFAULT_RUBRIC,
                                       manifest.window_turns, log=say)
    (store.dir / "calibration.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    say(f"calibration {CALIBRATION_VERSION}: {json.dumps(result['summary'])}")


def not_run(pair) -> dict:
    """A planned pair with no stored judgment is reported, never silently dropped."""
    return {"pair_id": pair.pair_id, "story_id": pair.scenario.story_id, "scenario_id": pair.scenario.scenario_id,
            "persona": pair.persona.id, "replicate": pair.replicate, "first_side": pair.first_side,
            "outcome": "invalid", "reason": "not played or not judged (budget, cancel or judge failure)"}


def cmd_report(args) -> dict:
    store = ArtifactStore(args.root, args.experiment_id)
    manifest = store.load_manifest()
    pairs = manifest.pair_specs()
    arms = {}
    for p in pairs:
        for side in (BETA, PROD):
            arm = store.load_arm(p.arm_id(side))
            if arm:
                arms[arm.arm_id] = arm
    judgments = [store.load_judgment(p.pair_id) or not_run(p) for p in pairs]
    cal_path = store.dir / "calibration.json"
    calibration = json.loads(cal_path.read_text(encoding="utf-8")) if cal_path.exists() else None
    report = build_report(manifest, arms, judgments, DEFAULT_RUBRIC, calibration=calibration)
    store.save_report(report, render_html(report, arms))
    # Skeleton-less variant for hosts that wrap pages themselves (shareable artifact pages).
    (store.dir / "report_fragment.html").write_text(render_html(report, arms, fragment=True), encoding="utf-8")
    say(report["headline"])
    say(f"report: {store.dir / 'report.html'}")
    return report


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="arena", description="Jev game arena: beta vs prod")
    ap.add_argument("command", choices=["run", "judge", "calibrate", "report", "all"])
    ap.add_argument("--experiment-id", default=time.strftime("arena_%Y%m%d_%H%M"))
    ap.add_argument("--root", type=Path, default=default_root())
    ap.add_argument("--beta-url", default=DEFAULT_URLS[BETA])
    ap.add_argument("--prod-url", default=DEFAULT_URLS[PROD])
    ap.add_argument("--stories", nargs="*")
    ap.add_argument("--personas", nargs="*", choices=list(PERSONAS))
    ap.add_argument("--replicates", type=int, default=1)
    ap.add_argument("--turns", type=int, default=8)
    ap.add_argument("--window-turns", type=int, default=4)
    ap.add_argument("--max-pairs", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260923)
    # Players and both releases' storytellers share provider rate limits (and real
    # users' capacity); keep paired-arm concurrency low. See design §10.
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--judge-concurrency", type=int, default=4)
    ap.add_argument("--max-game-turns", type=int, default=0, help="0 = full horizon for every pair")
    ap.add_argument("--max-wall-seconds", type=int, default=5400)
    ap.add_argument("--player-model", default="gpt-4o-mini")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    ap.add_argument("--calibration-arms", type=int, default=2, help="recorded arms per story to mutate")
    ap.add_argument("--force", action="store_true", help="re-judge pairs even if cached")
    return ap


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    say(f"experiment {args.experiment_id} -> {args.root / args.experiment_id}")
    if args.command in ("run", "all"):
        asyncio.run(cmd_run(args))
    if args.command in ("judge", "all"):
        asyncio.run(cmd_judge(args))
    if args.command in ("calibrate", "all"):
        asyncio.run(cmd_calibrate(args))
    if args.command in ("report", "all"):
        cmd_report(args)


if __name__ == "__main__":
    main(sys.argv[1:])
