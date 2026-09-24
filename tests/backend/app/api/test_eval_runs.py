"""Tests for the operator-only arena run endpoints (Railway kickoff)."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import backend.app.api.eval_runs as eval_runs

TOKEN = "op-secret"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.app.main import app

    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "true")
    monkeypatch.setenv("OPERATOR_TOKEN", TOKEN)
    monkeypatch.setenv("ARENA_BETA_URL", "https://beta.example")
    monkeypatch.setattr(eval_runs, "arena_root", lambda: tmp_path)
    eval_runs.RUNS.clear()
    eval_runs.LOGS.clear()
    # context manager = one persistent event loop, like uvicorn in production,
    # so background run tasks survive between requests
    with TestClient(app) as c:
        yield c


def auth():
    return {"X-Operator-Token": TOKEN}


def test_runs_require_operator_token(client):
    assert client.post("/api/eval/runs", json={}).status_code == 401
    assert client.get("/api/eval/runs").status_code == 401


def test_runs_fail_closed_when_debug_tools_disabled(client, monkeypatch):
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "")
    assert client.post("/api/eval/runs", json={}, headers=auth()).status_code == 403


def test_refused_on_the_prod_service(client, monkeypatch):
    monkeypatch.setattr(eval_runs, "get_build_info", lambda: {"environment": "prod"})
    r = client.post("/api/eval/runs", json={"profile": "smoke"}, headers=auth())
    assert r.status_code == 403


@pytest.mark.parametrize("bad", ["../etc", "a/b", ".hidden", "x" * 81])
def test_experiment_ids_cannot_escape_the_artifact_dir(client, bad):
    r = client.post("/api/eval/runs", json={"experiment_id": bad, "profile": "smoke"}, headers=auth())
    assert r.status_code in (400, 404)


def test_unknown_profile_and_judge_rejected(client):
    assert client.post("/api/eval/runs", json={"profile": "huge"}, headers=auth()).status_code == 400
    assert client.post("/api/eval/runs", json={"profile": "smoke", "judges": ["gpt"]},
                       headers=auth()).status_code == 400


def test_start_runs_in_background_one_at_a_time_and_reports_status(client, monkeypatch):
    started = []

    async def fake_execute(cfg):
        started.append(cfg)
        eval_runs.write_run_state(cfg.experiment_id, status="running")
        await asyncio.sleep(3600)

    monkeypatch.setattr(eval_runs, "execute", fake_execute)
    r = client.post("/api/eval/runs", json={"experiment_id": "gate_1", "profile": "smoke", "judges": ["llm"]},
                    headers=auth())
    assert r.status_code == 202 and r.json()["experiment_id"] == "gate_1"
    cfg = started[0] if started else None
    busy = client.post("/api/eval/runs", json={"experiment_id": "gate_2", "profile": "smoke"}, headers=auth())
    assert busy.status_code == 409
    status = client.get("/api/eval/runs/gate_1", headers=auth()).json()
    assert status["experiment_id"] == "gate_1"
    assert client.get("/api/eval/runs", headers=auth()).json()["runs"][0]["experiment_id"] == "gate_1"
    for task in eval_runs.RUNS.values():
        task.cancel()
    if cfg is not None:
        assert cfg.beta_url == "https://beta.example" and cfg.prod_url == "https://storieschat.ai"
        assert [j.name for j in cfg.judges] == ["llm"] and cfg.concurrency == 2


def test_run_left_running_by_a_restart_reports_interrupted(client, tmp_path):
    (tmp_path / "old_run").mkdir()
    (tmp_path / "old_run" / "run.json").write_text(json.dumps({"status": "running"}))
    assert client.get("/api/eval/runs/old_run", headers=auth()).json()["status"] == "interrupted"


def test_report_and_cancel(client, tmp_path):
    exp = tmp_path / "done_run"
    exp.mkdir()
    (exp / "report.html").write_text("<p>Release gate: PASS</p>", encoding="utf-8")
    r = client.get("/api/eval/runs/done_run/report", params={"operator_token": TOKEN})
    assert r.status_code == 200 and "Release gate" in r.text
    assert client.post("/api/eval/runs/done_run/cancel", headers=auth()).status_code == 200
    assert (exp / "STOP").exists()
    assert client.get("/api/eval/runs/missing/report", headers=auth()).status_code == 404
