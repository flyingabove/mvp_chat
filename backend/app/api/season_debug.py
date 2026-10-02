"""Operator-only debug viewer for the headless `SeasonRunner` (BL-86, P-04).

This is deliberately thin and scoped to exactly what `backend/app/sim/` can do today: run a season on the
deterministic `FakeWriter` against the fixed Terrace-shaped fixture used by the P-04 unit tests, and return
the real day-by-day log the run produced (who was in each scene, what the fake writer wrote, which
relationship deltas and movements were applied or rejected, and the invariant-check result for that day).

It is NOT the admin-only "season camera" watch mode (P-13, blocked behind P-07 through P-11 -- goals,
stances, mind/fog-of-war, NPC-driven extraction, scene dynamics -- none of which exist yet). There is no
real writer hookup here and nothing is persisted beyond the single synchronous response: a `FakeWriter`
season completes in well under a second (see `tests/backend/app/sim/test_runner.py`), so a plain POST that
runs the whole season and returns the log is simpler than streaming and is sufficient for this purpose.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import require_operator
from backend.app.sim.fixtures import build_story
from backend.app.sim.runner import DayReport, SceneRecord, SeasonResult, SeasonRunner
from backend.app.sim.writer import FakeWriter

# A03: every route here runs the sim (cheap, but still a server-side compute call) and should stay behind
# the same operator gate as the rest of the debug surface -- never reachable by an ordinary player.
router = APIRouter(dependencies=[Depends(require_operator)])

# The only fixture on offer today, on purpose (BL-86/P-04 scope): a general story picker belongs to P-13,
# once there is a real writer and more than one offline fixture worth picking between.
FIXTURES = {
    "terrace_fake_writer": "Terrace fixture (5 NPCs + player, shared living room) -- same one P-04's tests use.",
}
DEFAULT_FIXTURE = "terrace_fake_writer"

MAX_DAYS = 30
MAX_SCENES_PER_DAY = 20
MAX_BUDGET = 2000


@router.get("/fixtures")
async def list_fixtures() -> dict[str, Any]:
    return {"fixtures": [{"id": fid, "description": desc} for fid, desc in FIXTURES.items()],
            "default": DEFAULT_FIXTURE}


def _scene_to_dict(record: SceneRecord) -> dict[str, Any]:
    return {
        "minute": record.encounter.minute,
        "duration": record.encounter.duration,
        "place": record.encounter.place,
        "participants": [record.encounter.a, record.encounter.b],
        "summary": record.update.summary,
        "relationship_deltas": [asdict(d) for d in record.update.relationship_deltas],
        "movements": [list(m) for m in record.update.movements],
        "rejections": list(record.rejections),
    }


def _day_to_dict(report: DayReport) -> dict[str, Any]:
    return {
        "day": report.day,
        "scenes_written": report.scenes_written,
        "scenes_summarized": report.scenes_summarized,
        "scenes": [_scene_to_dict(s) for s in report.scenes],
        "rejections": list(report.rejections),
        "violations": list(report.violations),
        "invariants_ok": not report.violations,
    }


def _result_to_dict(result: SeasonResult) -> dict[str, Any]:
    return {
        "completed_days": result.completed_days,
        "calls_used": result.calls_used,
        "stopped_early": result.stopped_early,
        "all_violations": list(result.all_violations),
        "all_rejections": list(result.all_rejections),
        "days": [_day_to_dict(d) for d in result.days],
    }


@router.post("/run")
async def run_season(body: dict) -> dict[str, Any]:
    fixture = body.get("fixture") or DEFAULT_FIXTURE
    if fixture not in FIXTURES:
        raise HTTPException(status_code=400, detail=f"Unknown fixture {fixture!r}. Known: {sorted(FIXTURES)}")

    seed = str(body.get("seed") or "season-seed")

    def _bounded_int(key: str, default: int, maximum: int) -> int:
        try:
            value = int(body.get(key, default))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{key!r} must be an integer")
        if value < 1 or value > maximum:
            raise HTTPException(status_code=400, detail=f"{key!r} must be between 1 and {maximum}")
        return value

    days = _bounded_int("days", 5, MAX_DAYS)
    scenes_per_day = _bounded_int("scenes_per_day", 3, MAX_SCENES_PER_DAY)
    budget = _bounded_int("budget", 1000, MAX_BUDGET)

    story = build_story(seed)
    writer = FakeWriter()
    runner = SeasonRunner(story, seed=seed, writer=writer, days=days,
                           scenes_per_day=scenes_per_day, budget=budget)
    result = runner.run()

    return {
        "fixture": fixture,
        "seed": seed,
        "days_requested": days,
        "scenes_per_day": scenes_per_day,
        "budget": budget,
        **_result_to_dict(result),
    }
