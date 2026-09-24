# backend/app/evaluation/service.py
"""One orchestration path for every way an arena run starts.

The CLI (local machine), the operator API (Railway beta service) and the
offline local mode (Ollama) all build an ArenaConfig and call
run_experiment(). Stages: play -> judge -> calibrate -> report.

Games are PLAYED ONCE and judged by every configured judge (Jev and/or an
OpenAI-compatible LLM), so adding a judge adds only judge calls, never game
or player calls. The report carries the release gate
(aggregate.release_gate): every game must be won by beta under at least one
judge, with no critical regression.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

from backend.app.evaluation.calibration import CALIBRATION_VERSION, run_calibration
from backend.app.evaluation.contracts import (
    BETA, PROD, Budget, ExperimentManifest, ExperimentMode, TargetIdentity, from_dict,
)
from backend.app.evaluation.judge import DEFAULT_JUDGE_MODEL, JevPairwiseJudge
from backend.app.evaluation.knowledge import load_bundles
from backend.app.evaluation.pipeline import JudgePipeline
from backend.app.evaluation.players import PERSONAS, PLAYER_PROMPT_VERSION, LLMPlayer
from backend.app.evaluation.report import build_arena_report, render_arena_html
from backend.app.evaluation.rubric import DEFAULT_RUBRIC
from backend.app.evaluation.runner import ArenaRunner, RunSummary, build_pairs
from backend.app.evaluation.store import ArtifactStore
from backend.app.evaluation.suite import PROFILES, SUITE_VERSION, profile_scenarios
from backend.app.evaluation.targets import HostedTargetAdapter

Log = Callable[[str], None]
STAGES = ("play", "judge", "calibrate", "report")
OPENAI_V1 = "https://api.openai.com/v1"


@dataclass(frozen=True)
class ModelEndpoint:
    """Any OpenAI-compatible chat endpoint: OpenAI, or Ollama at
    http://127.0.0.1:11434/v1 (api_key is ignored by Ollama)."""
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class JudgeSpec:
    name: str                          # store namespace + report label
    kind: str                          # "jev" | "llm"
    model: str
    window_turns: int                  # 0 = one window per episode (fewest calls)
    endpoint: ModelEndpoint | None = None
    api_key: str = ""                  # jev only

    @property
    def namespace(self) -> str:
        # Jev judgments keep the original judgments/ path so older
        # experiments stay readable.
        return "" if self.name == "jev" else self.name


@dataclass
class ArenaConfig:
    experiment_id: str
    root: Path
    beta_url: str
    prod_url: str
    player: ModelEndpoint
    judges: list[JudgeSpec]
    profile: str = "gate"
    stories: list[str] | None = None
    personas: list[str] | None = None
    replicates: int | None = None
    turns: int | None = None
    max_pairs: int = 0
    seed: int = 20260923
    concurrency: int = 2
    judge_concurrency: int = 4
    max_game_turns: int = 0
    max_wall_seconds: int = 5400
    calibration_arms: int = 0
    mode: str = ExperimentMode.AS_DEPLOYED_PRODUCT.value
    extra_notes: tuple[str, ...] = ()
    target_timeout_s: float = 150.0

    @property
    def store(self) -> ArtifactStore:
        return ArtifactStore(self.root, self.experiment_id)


def judge_specs(names: list[str], *, turns: int, llm: ModelEndpoint | None, jev_api_key: str = "",
                jev_model: str = DEFAULT_JUDGE_MODEL, jev_window_turns: int = 4) -> list[JudgeSpec]:
    """Jev judges scene windows; the LLM judge sees the whole episode in one
    window (2 calls per pair: A/B then B/A) to keep API calls low."""
    specs = []
    for name in names:
        if name == "jev":
            specs.append(JudgeSpec("jev", "jev", jev_model, jev_window_turns, api_key=jev_api_key))
        elif name == "llm":
            if llm is None:
                raise ValueError("llm judge requested without an endpoint")
            specs.append(JudgeSpec("llm", "llm", llm.model, turns, endpoint=llm))
        else:
            raise ValueError(f"unknown judge: {name}")
    return specs


def evaluator_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def targets_for(cfg: ArenaConfig, client: httpx.AsyncClient) -> dict[str, HostedTargetAdapter]:
    return {BETA: HostedTargetAdapter(BETA, cfg.beta_url, client, turn_timeout_s=cfg.target_timeout_s),
            PROD: HostedTargetAdapter(PROD, cfg.prod_url, client, turn_timeout_s=cfg.target_timeout_s)}


async def preflight(targets, log: Log) -> tuple[dict[str, TargetIdentity], dict[str, dict]]:
    ids, caps = {}, {}
    for side, t in targets.items():
        ids[side] = await t.identify()
        caps[side] = await t.capabilities()
        i = ids[side]
        log(f"{side}: {i.base_url} commit={i.commit[:12]} deployment={i.deployment_id[:12] or '-'} "
            f"env={i.environment} pinnable={i.is_pinnable} "
            f"capabilities={caps[side].get('contract_version') or 'none (observational only)'}")
    return ids, caps


def build_manifest(cfg: ArenaConfig, ids: dict[str, TargetIdentity], caps: dict[str, dict]) -> ExperimentManifest:
    spec = PROFILES[cfg.profile]
    turns = cfg.turns or spec["turns"]
    scenarios = profile_scenarios(cfg.profile, turns, cfg.stories)
    persona_ids = cfg.personas or list(spec["personas"] or PERSONAS)
    pairs = build_pairs(scenarios, [PERSONAS[p] for p in persona_ids],
                        cfg.replicates or spec["replicates"], cfg.seed)
    if cfg.max_pairs:
        pairs = pairs[:cfg.max_pairs]
    bundles = load_bundles(sorted({s.story_id for s in scenarios}))
    notes = [
        f"suite {SUITE_VERSION}, profile {cfg.profile}",
        "observational: public /api/chat + player-facing [D] debug box; no server receipts/snapshots, "
        "so capacity/RNG/state-transition checks are not measured",
        "content judged against the evaluator checkout's authored story files; if prod content differs "
        "this is a product comparison, not an engine comparison",
        *cfg.extra_notes,
    ]
    for side, ident in ids.items():
        if not ident.is_pinnable:
            notes.append(f"{side} reports no commit or deployment id: release drift cannot be detected")
    primary = cfg.judges[0]
    return ExperimentManifest(
        experiment_id=cfg.experiment_id,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        mode=cfg.mode,
        targets={k: asdict(v) for k, v in ids.items()},
        judge_model=primary.model,
        rubric_version=DEFAULT_RUBRIC.version,
        rubric_hash=DEFAULT_RUBRIC.rubric_hash,
        evaluator_commit=evaluator_commit(),
        player_model=cfg.player.model,
        player_prompt_version=PLAYER_PROMPT_VERSION,
        knowledge_bundles={k: b.bundle_hash for k, b in bundles.items()},
        pairs=[{"pair_id": p.pair_id, "scenario": asdict(p.scenario), "persona": asdict(p.persona),
                "replicate": p.replicate, "seed": p.seed, "first_side": p.first_side} for p in pairs],
        seed=cfg.seed,
        window_turns=primary.window_turns or turns,
        budget=asdict(Budget(
            max_game_turns=cfg.max_game_turns or 2 * sum(p.scenario.max_player_turns for p in pairs),
            max_wall_seconds=cfg.max_wall_seconds,
        )),
        capabilities=caps,
        judges={j.name: {"kind": j.kind, "model": j.model, "window_turns": j.window_turns or turns,
                         "base_url": j.endpoint.base_url if j.endpoint else ""} for j in cfg.judges},
        notes=tuple(notes),
    )


async def play(cfg: ArenaConfig, client: httpx.AsyncClient, log: Log) -> RunSummary:
    store = cfg.store
    targets = targets_for(cfg, client)
    ids, caps = await preflight(targets, log)
    if store.manifest_path.exists():
        manifest = store.load_manifest()
        pinned = {k: from_dict(TargetIdentity, v) for k, v in manifest.targets.items()}
        for side in (BETA, PROD):
            if pinned[side].pin_key != ids[side].pin_key:
                raise RuntimeError(f"{side} changed since this experiment started "
                                   f"({pinned[side].pin_key} -> {ids[side].pin_key}); start a new experiment id")
        log(f"resuming {cfg.experiment_id}")
    else:
        manifest = build_manifest(cfg, ids, caps)
        store.save_manifest(manifest)
        pinned = ids
        log(f"manifest {manifest.manifest_hash[:12]} with {len(manifest.pairs)} pairs")
    player = LLMPlayer(client, api_key=cfg.player.api_key, model=cfg.player.model, base_url=cfg.player.base_url)
    runner = ArenaRunner(experiment_id=cfg.experiment_id, store=store, targets=targets, pinned=pinned,
                         player=player, budget=Budget(**manifest.budget), concurrency=cfg.concurrency)
    summary = await runner.run(manifest.pair_specs())
    log(f"play finished: {summary.__dict__}")
    return summary


def make_judge(spec: JudgeSpec, client: httpx.AsyncClient) -> JevPairwiseJudge:
    """Both kinds share JevPairwiseJudge; only the decision client differs."""
    if spec.kind == "jev":
        from backend.app.llm.providers.jev import JevClient

        if not spec.api_key:
            raise RuntimeError("jev judge needs TYPESAFE_API_KEY")
        return JevPairwiseJudge(JevClient(client, api_key=spec.api_key, model=spec.model), DEFAULT_RUBRIC,
                                model=spec.model)
    from backend.app.llm.providers.llm_decisions import LLMDecisionClient

    ep = spec.endpoint
    return JevPairwiseJudge(LLMDecisionClient(client, base_url=ep.base_url, api_key=ep.api_key, model=ep.model),
                            DEFAULT_RUBRIC, model=ep.model, timeout_ms=300_000)


async def judge(cfg: ArenaConfig, client: httpx.AsyncClient, log: Log, *, force: bool = False) -> dict[str, list]:
    store = cfg.store
    manifest = store.load_manifest()
    pairs = manifest.pair_specs()
    bundles = load_bundles(sorted({p.scenario.story_id for p in pairs}))
    out = {}
    for spec in cfg.judges:
        window = manifest.judges.get(spec.name, {}).get("window_turns") or spec.window_turns or manifest.window_turns
        pipe = JudgePipeline(store=store, bundles=bundles, judge=make_judge(spec, client), rubric=DEFAULT_RUBRIC,
                             window_turns=window, concurrency=cfg.judge_concurrency, judge_name=spec.namespace,
                             max_judge_input_tokens=manifest.budget.get("max_judge_input_tokens", 5_000_000))
        results = await pipe.run(pairs, force=force)
        counts: dict[str, int] = {}
        for r in results:
            counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
        log(f"judge {spec.name} ({spec.model}, window {window}): {counts}; input tokens {pipe.tokens_used:,}")
        out[spec.name] = results
    return out


async def calibrate(cfg: ArenaConfig, client: httpx.AsyncClient, log: Log) -> dict | None:
    if not cfg.calibration_arms:
        return None
    store = cfg.store
    manifest = store.load_manifest()
    pairs = manifest.pair_specs()
    bundles = load_bundles(sorted({p.scenario.story_id for p in pairs}))
    picked, per_story = [], {}
    for p in pairs:
        arm = store.load_arm(p.arm_id(BETA))
        sid = p.scenario.story_id
        if arm and arm.scorable and len(arm.turns) >= 2 and per_story.get(sid, 0) < cfg.calibration_arms:
            picked.append((bundles[sid], arm))
            per_story[sid] = per_story.get(sid, 0) + 1
    spec = cfg.judges[0]
    result = await run_calibration(picked, make_judge(spec, client), DEFAULT_RUBRIC,
                                   spec.window_turns or manifest.window_turns, log=log)
    result["judge"] = spec.name
    (store.dir / "calibration.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    log(f"calibration {CALIBRATION_VERSION} ({spec.name}): {json.dumps(result['summary'])}")
    return result


def not_run(pair) -> dict:
    """A planned pair with no stored judgment is reported, never silently dropped."""
    return {"pair_id": pair.pair_id, "story_id": pair.scenario.story_id, "scenario_id": pair.scenario.scenario_id,
            "persona": pair.persona.id, "replicate": pair.replicate, "first_side": pair.first_side,
            "outcome": "invalid", "reason": "not played or not judged (budget, cancel or judge failure)"}


def report(cfg: ArenaConfig, log: Log) -> dict[str, Any]:
    store = cfg.store
    manifest = store.load_manifest()
    pairs = manifest.pair_specs()
    arms = {}
    for p in pairs:
        for side in (BETA, PROD):
            arm = store.load_arm(p.arm_id(side))
            if arm:
                arms[arm.arm_id] = arm
    by_judge = {spec.name: [store.load_judgment(p.pair_id, spec.namespace) or not_run(p) for p in pairs]
                for spec in cfg.judges}
    cal_path = store.dir / "calibration.json"
    calibration = json.loads(cal_path.read_text(encoding="utf-8")) if cal_path.exists() else None
    arena = build_arena_report(manifest, arms, by_judge, DEFAULT_RUBRIC, calibration=calibration)
    store.save_report(arena, render_arena_html(arena, arms))
    (store.dir / "report_fragment.html").write_text(render_arena_html(arena, arms, fragment=True), encoding="utf-8")
    (store.dir / "gate.json").write_text(json.dumps(arena["gate"], indent=2), encoding="utf-8")
    for name, rep in arena["judges"].items():
        log(f"[{name}] {rep['headline']}")
    log(f"release gate: {'PASS' if arena['gate']['passed'] else 'FAIL'} {arena['gate']['reasons']}")
    log(f"report: {store.dir / 'report.html'}")
    return arena


async def run_experiment(cfg: ArenaConfig, log: Log, stages: tuple[str, ...] = STAGES,
                         *, force_judge: bool = False) -> dict[str, Any] | None:
    log(f"experiment {cfg.experiment_id} -> {cfg.store.dir} (stages: {', '.join(stages)})")
    async with httpx.AsyncClient() as client:
        if "play" in stages:
            await play(cfg, client, log)
        if "judge" in stages:
            await judge(cfg, client, log, force=force_judge)
        if "calibrate" in stages:
            await calibrate(cfg, client, log)
    return report(cfg, log) if "report" in stages else None
