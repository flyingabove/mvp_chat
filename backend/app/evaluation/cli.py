# backend/app/evaluation/cli.py
"""Arena command line (thin wrapper: scripts/eval/arena.py).

Hosted (this machine plays the deployed beta and prod releases):
  run | judge | calibrate | report | all      stages of one experiment

Offline (nothing leaves this machine; needs a local Ollama):
  local      start the current checkout (beta slot) and --baseline-ref
             (prod slot, default origin/beta) as local servers on Ollama,
             play + judge with the Ollama judge, report + gate
  precheck   `local` with the smoke profile, then a pass/fail verdict on
             reliability + deterministic checks (exit code 1 on fail)

Cheapest first:
  tiered     precheck (free, offline); only if it passes, the hosted gate
             run (Jev + OpenAI judges; add `ollama` for a free third judge)

Release (used by .claude/skills/promote-to-prod/SKILL.md):
  wait-deploy  poll --url /api/health until it runs --commit (exit 1 on timeout)
  smoke        exercise --url like a player: health, capabilities, home page,
               new game + one turn per story (exit 1 on any failure)

Railway (the beta service runs the experiment itself):
  kickoff    POST /api/eval/runs on beta (operator token required)
  status     GET  /api/eval/runs/<id> on beta

Every mode goes through service.run_experiment(), so hosted, Railway and
offline runs share the same pairing, judging, rating and gate code.
Experiments are resumable by --experiment-id.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

from backend.app.evaluation.contracts import BETA, PROD
from backend.app.evaluation.local_release import OLLAMA_V1, LocalRelease, ensure_context_model, ollama_models
from backend.app.evaluation.players import PERSONAS
from backend.app.evaluation.report import precheck_verdict
from backend.app.evaluation.service import (
    OPENAI_V1, STAGES, ArenaConfig, ModelEndpoint, judge_specs, run_experiment,
)
from backend.app.evaluation.store import default_root
from backend.app.evaluation.suite import MIN_TURNS, PROFILES

DEFAULT_URLS = {BETA: "https://beta-api.storieschat.ai", PROD: "https://storieschat.ai"}
REPO = Path(__file__).resolve().parents[3]


def say(msg: str) -> None:
    print(f"[arena {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def hosted_config(args, ollama_model: str | None = None) -> ArenaConfig:
    from backend.app.config.settings import OPENAI_API_KEY, TYPESAFE_API_KEY

    player = ModelEndpoint(OPENAI_V1, OPENAI_API_KEY, args.player_model)
    llm = ModelEndpoint(OPENAI_V1, OPENAI_API_KEY, args.llm_judge_model)
    ollama = ModelEndpoint(args.ollama_url, "ollama", ollama_model) if ollama_model else None
    turns = args.turns or PROFILES[args.profile]["turns"]
    return ArenaConfig(
        experiment_id=args.experiment_id, root=args.root, beta_url=args.beta_url, prod_url=args.prod_url,
        player=player,
        judges=judge_specs(args.judges, turns=turns, llm=llm, jev_api_key=TYPESAFE_API_KEY,
                           jev_model=args.judge_model, jev_window_turns=args.window_turns, ollama=ollama),
        profile=args.profile, stories=args.stories, personas=args.personas, replicates=args.replicates,
        turns=args.turns, max_pairs=args.max_pairs, seed=args.seed, concurrency=args.concurrency,
        judge_concurrency=args.judge_concurrency, max_game_turns=args.max_game_turns,
        max_wall_seconds=args.max_wall_seconds, calibration_arms=args.calibration_arms,
    )


async def run_hosted(args, stages) -> dict | None:
    ollama_model = None
    if "ollama" in args.judges:
        ollama_model = await ensure_context_model(args.ollama_model, args.ollama_url)
    return await run_experiment(hosted_config(args, ollama_model), say, stages=stages, force_judge=args.force)


async def run_local(args) -> dict | None:
    models = await ollama_models(args.ollama_url)
    if args.ollama_model not in models:
        raise SystemExit(f"Ollama model {args.ollama_model!r} not available at {args.ollama_url} "
                         f"(have: {', '.join(models) or 'none - is `ollama serve` running?'})")
    model = await ensure_context_model(args.ollama_model, args.ollama_url)
    say(f"ollama model {model} (from {args.ollama_model}, larger context)")
    work = args.root / "_local"
    releases = [
        LocalRelease(BETA, args.candidate_ref, args.beta_port, REPO, work, model, args.ollama_url),
        LocalRelease(PROD, args.baseline_ref, args.prod_port, REPO, work, model, args.ollama_url),
    ]
    for rel in releases:
        rel.prepare()
        say(f"{rel.label}: {rel.ref or 'current checkout'} @ {rel.commit[:12]} -> {rel.url}")
    try:
        for rel in releases:
            rel.start()
        await asyncio.gather(*(rel.wait_healthy() for rel in releases))
        endpoint = ModelEndpoint(args.ollama_url, "ollama", model)
        turns = args.turns or PROFILES[args.profile]["turns"]
        cfg = ArenaConfig(
            experiment_id=args.experiment_id, root=args.root, beta_url=releases[0].url, prod_url=releases[1].url,
            # offline: only the local judge (Jev and OpenAI are cloud services)
            player=endpoint, judges=judge_specs(["ollama"], turns=turns, llm=None, ollama=endpoint),
            gate_judges=("ollama",),
            profile=args.profile, stories=args.stories, personas=args.personas, replicates=args.replicates,
            turns=args.turns, max_pairs=args.max_pairs, seed=args.seed, concurrency=1, judge_concurrency=1,
            max_wall_seconds=args.max_wall_seconds, calibration_arms=args.calibration_arms,
            mode="local_offline", target_timeout_s=600.0,
            extra_notes=(f"offline: both releases served locally on Ollama {model}; "
                         "no Jev judge (cloud); quality numbers reflect the local model, not production",),
        )
        return await run_experiment(cfg, say, stages=STAGES if args.calibration_arms else ("play", "judge", "report"))
    finally:
        for rel in releases:
            rel.stop()


async def precheck(args) -> bool:
    arena = await run_local(args)
    verdict = precheck_verdict(arena)
    (args.root / args.experiment_id / "precheck.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    say(f"PRECHECK {'PASS' if verdict['passed'] else 'FAIL'}: {verdict['reasons'] or verdict['rule']}")
    return verdict["passed"]


async def tiered(args) -> bool:
    """Cheapest first: free offline precheck, then the paid hosted gate."""
    base_id = args.experiment_id
    args.experiment_id, args.profile = f"{base_id}_precheck", "smoke"
    if not await precheck(args):
        say("stopping before the hosted run: fix the precheck findings first (no cloud calls were made)")
        return False
    args.experiment_id, args.profile = f"{base_id}_gate", args.hosted_profile
    arena = await run_hosted(args, STAGES)
    return bool(arena and arena["gate"]["passed"])


def operator_headers() -> dict[str, str]:
    token = os.getenv("ARENA_OPERATOR_TOKEN") or os.getenv("OPERATOR_TOKEN", "")
    if not token:
        raise SystemExit("set ARENA_OPERATOR_TOKEN (the beta service's OPERATOR_TOKEN) to use kickoff/status")
    return {"X-Operator-Token": token}


def kickoff(args) -> None:
    body = {"experiment_id": args.experiment_id, "profile": args.profile, "judges": args.judges}
    for key in ("stories", "personas", "replicates", "turns", "max_pairs"):
        if getattr(args, key):
            body[key] = getattr(args, key)
    r = httpx.post(f"{args.beta_url}/api/eval/runs", json=body, headers=operator_headers(), timeout=30.0)
    say(f"HTTP {r.status_code}: {r.text[:500]}")


def status(args) -> None:
    r = httpx.get(f"{args.beta_url}/api/eval/runs/{args.experiment_id}", headers=operator_headers(), timeout=30.0)
    say(f"HTTP {r.status_code}")
    print(json.dumps(r.json(), indent=2)[:4000] if r.headers.get("content-type", "").startswith("application/json")
          else r.text[:2000])


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="arena", description="StoriesChat game arena: beta vs prod")
    ap.add_argument("command", choices=["run", "judge", "calibrate", "report", "all", "local", "precheck", "tiered",
                                        "kickoff", "status", "wait-deploy", "smoke"])
    ap.add_argument("--url", default=DEFAULT_URLS[BETA], help="wait-deploy/smoke: service base URL")
    ap.add_argument("--commit", default="", help="wait-deploy: commit sha (prefix) to wait for")
    ap.add_argument("--timeout", type=int, default=1500, help="wait-deploy: seconds")
    ap.add_argument("--experiment-id", default=time.strftime("arena_%Y%m%d_%H%M"))
    ap.add_argument("--root", type=Path, default=default_root())
    ap.add_argument("--profile", choices=list(PROFILES), default="gate")
    ap.add_argument("--judges", nargs="+", choices=["jev", "llm", "ollama"], default=["jev", "llm"],
                    help="jev = TypeSafe Jev, llm = OpenAI, ollama = local model (free, advisory in the gate)")
    ap.add_argument("--hosted-profile", choices=list(PROFILES), default="gate", help="tiered: hosted stage size")
    ap.add_argument("--beta-url", default=DEFAULT_URLS[BETA])
    ap.add_argument("--prod-url", default=DEFAULT_URLS[PROD])
    ap.add_argument("--stories", nargs="*")
    ap.add_argument("--personas", nargs="*", choices=list(PERSONAS))
    ap.add_argument("--replicates", type=int, default=None)
    ap.add_argument("--turns", type=int, default=None)
    ap.add_argument("--window-turns", type=int, default=4, help="Jev scene window size")
    ap.add_argument("--max-pairs", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260923)
    # Players and both releases' storytellers share provider rate limits (and real
    # users' capacity); keep paired-arm concurrency low. See design §10.
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--judge-concurrency", type=int, default=2, help="cloud judges; ollama always runs 1")
    ap.add_argument("--max-game-turns", type=int, default=0, help="0 = full horizon for every pair")
    ap.add_argument("--max-wall-seconds", type=int, default=5400)
    ap.add_argument("--player-model", default="gpt-4o-mini")
    ap.add_argument("--judge-model", default="jev-1.13.0")
    ap.add_argument("--llm-judge-model", default="gpt-4o-mini")
    ap.add_argument("--calibration-arms", type=int, default=0, help="recorded arms per story to mutate (0 = skip)")
    ap.add_argument("--force", action="store_true", help="re-judge pairs even if cached")
    # offline local mode
    ap.add_argument("--baseline-ref", default="origin/beta",
                    help="local/precheck: git ref for the baseline slot (default: what is deployed on beta)")
    ap.add_argument("--candidate-ref", default=None, help="local mode: git ref for the beta slot (default: checkout)")
    ap.add_argument("--ollama-model", default="llama3.1:8b")
    ap.add_argument("--ollama-url", default=OLLAMA_V1)
    ap.add_argument("--beta-port", type=int, default=8811)
    ap.add_argument("--prod-port", type=int, default=8812)
    return ap


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.turns is not None and args.turns < MIN_TURNS:
        raise SystemExit(f"--turns must be at least {MIN_TURNS}: shorter games barely leave the opening scene")
    if args.command in ("local", "precheck"):
        if args.command == "precheck" or "--profile" not in (argv or sys.argv):
            args.profile = "smoke"          # local models are slow; smoke unless asked otherwise
        if args.command == "precheck":
            sys.exit(0 if asyncio.run(precheck(args)) else 1)
        asyncio.run(run_local(args))
        return
    if args.command == "tiered":
        sys.exit(0 if asyncio.run(tiered(args)) else 1)
    if args.command == "wait-deploy":
        from backend.app.evaluation.release import wait_for_commit

        if not args.commit:
            raise SystemExit("--commit is required")
        result = asyncio.run(wait_for_commit(args.url, args.commit, timeout_s=args.timeout))
        say(json.dumps(result))
        sys.exit(0 if result["live"] else 1)
    if args.command == "smoke":
        from backend.app.evaluation.release import smoke

        result = asyncio.run(smoke(args.url))
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)
    if args.command == "kickoff":
        return kickoff(args)
    if args.command == "status":
        return status(args)
    stages = STAGES if args.command == "all" else (
        ("play",) if args.command == "run" else (args.command,))
    asyncio.run(run_hosted(args, stages))


if __name__ == "__main__":
    main(sys.argv[1:])
