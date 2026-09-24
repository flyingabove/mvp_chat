# backend/app/api/eval_runs.py
"""Operator-only arena runs on the deployed beta service (Railway).

Opt-in, never part of a deploy: an operator starts a run, the service plays
its own public URL against production, judges, and stores the report on the
Railway volume (/data/eval_arena). Same code path as the CLI
(evaluation.service.run_experiment).

  POST /api/eval/runs                 start {experiment_id?, profile, judges, ...}
  GET  /api/eval/runs                 list experiments with status + gate
  GET  /api/eval/runs/{id}            status, recent log lines, gate, headlines
  GET  /api/eval/runs/{id}/report     HTML report (?operator_token=... works in a browser)
  POST /api/eval/runs/{id}/cancel     cooperative stop (STOP file)

Guards: require_operator (DEBUG_TOOLS_ENABLED + OPERATOR_TOKEN, fail
closed); one run at a time; refused on the prod service; experiment ids are
validated so they can never escape the artifact directory. A redeploy kills
an in-flight run; it then reports "interrupted" and a new experiment id is
needed (the release it pinned is gone).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.app.auth.dependencies import require_operator
from backend.app.config.build_info import get_build_info

router = APIRouter()

ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
RUNS: dict[str, asyncio.Task] = {}
LOGS: dict[str, deque] = {}


class RunRequest(BaseModel):
    experiment_id: str | None = None
    profile: str = "gate"
    judges: list[str] = Field(default_factory=lambda: ["jev", "llm"])
    stories: list[str] | None = None
    personas: list[str] | None = None
    replicates: int | None = Field(default=None, ge=1, le=4)
    turns: int | None = Field(default=None, ge=10, le=16)          # suite.MIN_TURNS
    max_pairs: int = Field(default=0, ge=0, le=60)
    calibration_arms: int = Field(default=0, ge=0, le=3)


def arena_root() -> Path:
    from backend.app.evaluation.store import default_root

    return default_root()


def checked_id(experiment_id: str) -> str:
    if not ID_RE.fullmatch(experiment_id or "") or experiment_id.startswith("."):
        raise HTTPException(status_code=400, detail="invalid experiment id")
    return experiment_id


def self_url() -> str:
    if os.getenv("ARENA_BETA_URL"):
        return os.environ["ARENA_BETA_URL"].rstrip("/")
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if not domain:
        raise HTTPException(status_code=503, detail="cannot determine this service's public URL (set ARENA_BETA_URL)")
    return f"https://{domain}"


def running() -> str | None:
    return next((k for k, t in RUNS.items() if not t.done()), None)


def build_config(req: RunRequest, experiment_id: str):
    from backend.app.config.settings import OPENAI_API_KEY, TYPESAFE_API_KEY
    from backend.app.evaluation.service import OPENAI_V1, ArenaConfig, ModelEndpoint, judge_specs
    from backend.app.evaluation.suite import PROFILES

    if req.profile not in PROFILES:
        raise HTTPException(status_code=400, detail=f"unknown profile (use one of {sorted(PROFILES)})")
    endpoint = ModelEndpoint(OPENAI_V1, OPENAI_API_KEY, os.getenv("ARENA_LLM_MODEL", "gpt-4o-mini"))
    turns = req.turns or PROFILES[req.profile]["turns"]
    try:
        judges = judge_specs(req.judges, turns=turns, llm=endpoint, jev_api_key=TYPESAFE_API_KEY)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ArenaConfig(
        experiment_id=experiment_id, root=arena_root(), beta_url=self_url(),
        prod_url=os.getenv("ARENA_PROD_URL", "https://storieschat.ai").rstrip("/"),
        player=ModelEndpoint(OPENAI_V1, OPENAI_API_KEY, os.getenv("ARENA_PLAYER_MODEL", "gpt-4o-mini")),
        judges=judges, profile=req.profile, stories=req.stories, personas=req.personas,
        replicates=req.replicates, turns=req.turns, max_pairs=req.max_pairs,
        calibration_arms=req.calibration_arms, concurrency=2,
    )


def write_run_state(experiment_id: str, **fields: Any) -> None:
    path = arena_root() / experiment_id / "run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    state.update(fields)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def execute(cfg) -> None:
    from backend.app.evaluation.service import run_experiment

    lines = LOGS.setdefault(cfg.experiment_id, deque(maxlen=200))
    log_path = cfg.store.dir / "run.log"

    def log(msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        lines.append(line)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    write_run_state(cfg.experiment_id, status="running", started_at=time.time(), build=get_build_info())
    try:
        await run_experiment(cfg, log)
        write_run_state(cfg.experiment_id, status="done", finished_at=time.time())
    except Exception as exc:  # noqa: BLE001 - recorded, surfaced via status
        log(f"FAILED: {type(exc).__name__}: {exc}")
        write_run_state(cfg.experiment_id, status="failed", error=f"{type(exc).__name__}: {exc}"[:500],
                        finished_at=time.time())


def status_of(experiment_id: str) -> dict[str, Any]:
    exp_dir = arena_root() / experiment_id
    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="unknown experiment")
    state_path, gate_path, report_path = exp_dir / "run.json", exp_dir / "gate.json", exp_dir / "report.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state.get("status") == "running" and experiment_id not in RUNS:
        state["status"] = "interrupted"          # process restarted (e.g. redeploy) mid-run
    out: dict[str, Any] = {"experiment_id": experiment_id, **state}
    if gate_path.exists():
        out["gate"] = json.loads(gate_path.read_text(encoding="utf-8"))
    if report_path.exists():
        rep = json.loads(report_path.read_text(encoding="utf-8"))
        out["headlines"] = {k: v.get("headline") for k, v in (rep.get("judges") or {}).items()}
    out["log_tail"] = list(LOGS.get(experiment_id, []))[-40:]
    return out


@router.post("/eval/runs", status_code=202)
async def start_run(req: RunRequest, _op: dict = Depends(require_operator)):
    if get_build_info().get("environment") == "prod" and os.getenv("ARENA_ALLOW_PROD_RUNS") != "1":
        raise HTTPException(status_code=403, detail="arena runs are started from the beta service")
    busy = running()
    if busy:
        raise HTTPException(status_code=409, detail=f"run {busy} is still in progress")
    experiment_id = checked_id(req.experiment_id or time.strftime("rw_%Y%m%d_%H%M%S"))
    cfg = build_config(req, experiment_id)
    RUNS[experiment_id] = asyncio.create_task(execute(cfg))
    return {"experiment_id": experiment_id, "status": "running", "profile": req.profile, "judges": req.judges}


@router.get("/eval/runs")
async def list_runs(_op: dict = Depends(require_operator)):
    root = arena_root()
    if not root.exists():
        return {"runs": []}
    ids = sorted((p.name for p in root.iterdir() if p.is_dir() and ID_RE.fullmatch(p.name)), reverse=True)
    runs = []
    for eid in ids[:50]:
        s = status_of(eid)
        runs.append({"experiment_id": eid, "status": s.get("status", "unknown"),
                     "gate_passed": (s.get("gate") or {}).get("passed")})
    return {"runs": runs}


@router.get("/eval/runs/{experiment_id}")
async def get_run(experiment_id: str, _op: dict = Depends(require_operator)):
    return status_of(checked_id(experiment_id))


@router.get("/eval/runs/{experiment_id}/report", response_class=HTMLResponse)
async def get_report(experiment_id: str, _op: dict = Depends(require_operator)):
    path = arena_root() / checked_id(experiment_id) / "report.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="report not ready")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.post("/eval/runs/{experiment_id}/cancel")
async def cancel_run(experiment_id: str, _op: dict = Depends(require_operator)):
    exp_dir = arena_root() / checked_id(experiment_id)
    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="unknown experiment")
    (exp_dir / "STOP").write_text("", encoding="utf-8")
    return {"experiment_id": experiment_id, "status": "stopping"}
