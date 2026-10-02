"""Tests for backend/app/api/season_debug.py: the operator-only FakeWriter season debug viewer (BL-86)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from backend.app.main import app
    return TestClient(app)


def _enable_operator(monkeypatch, token: str = "s3cret") -> dict:
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", token)
    return {"X-Operator-Token": token}


# ---------------------------------------------------------------------------
# Operator gating
# ---------------------------------------------------------------------------

def test_run_rejects_when_debug_tools_disabled(monkeypatch):
    monkeypatch.delenv("DEBUG_TOOLS_ENABLED", raising=False)
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    resp = _client().post("/beta/debug/season/run", json={})
    assert resp.status_code == 403


def test_run_rejects_wrong_token(monkeypatch):
    _enable_operator(monkeypatch)
    resp = _client().post("/beta/debug/season/run", json={}, headers={"X-Operator-Token": "nope"})
    assert resp.status_code == 401


def test_fixtures_list_is_also_operator_gated(monkeypatch):
    monkeypatch.delenv("DEBUG_TOOLS_ENABLED", raising=False)
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    assert _client().get("/beta/debug/season/fixtures").status_code == 403


def test_run_refuses_token_in_query_string(monkeypatch):
    """REST never accepts the operator token as a query param (it would end up in access logs)."""
    _enable_operator(monkeypatch)
    resp = _client().post("/beta/debug/season/run?operator_token=s3cret", json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# A valid operator request runs a real season and returns its shape
# ---------------------------------------------------------------------------

def test_fixtures_list_with_valid_token(monkeypatch):
    headers = _enable_operator(monkeypatch)
    resp = _client().get("/beta/debug/season/fixtures", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == "terrace_fake_writer"
    assert any(f["id"] == "terrace_fake_writer" for f in body["fixtures"])


def test_run_default_season_matches_seasonrunner_shape(monkeypatch):
    headers = _enable_operator(monkeypatch)
    resp = _client().post("/beta/debug/season/run", json={"days": 2}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["fixture"] == "terrace_fake_writer"
    assert body["days_requested"] == 2
    assert body["completed_days"] == 2
    assert body["calls_used"] > 0
    assert body["stopped_early"] is False
    assert len(body["days"]) == 2

    day = body["days"][0]
    assert day["day"] == 0
    assert day["scenes_written"] >= 1
    assert day["invariants_ok"] is True
    assert day["violations"] == []

    scene = day["scenes"][0]
    assert set(scene["participants"]) <= {"ava", "ben", "cleo", "drew", "eli", "player"}
    assert "spent time together" in scene["summary"]
    assert isinstance(scene["relationship_deltas"], list)
    assert isinstance(scene["movements"], list)


def test_run_is_repeatable_given_the_same_seed(monkeypatch):
    headers = _enable_operator(monkeypatch)
    payload = {"days": 2, "seed": "same-seed"}
    first = _client().post("/beta/debug/season/run", json=payload, headers=headers).json()
    second = _client().post("/beta/debug/season/run", json=payload, headers=headers).json()
    assert first["calls_used"] == second["calls_used"]
    assert [d["scenes_written"] for d in first["days"]] == [d["scenes_written"] for d in second["days"]]


def test_run_respects_scenes_per_day_cap(monkeypatch):
    headers = _enable_operator(monkeypatch)
    resp = _client().post("/beta/debug/season/run", json={"days": 1, "scenes_per_day": 1}, headers=headers)
    body = resp.json()
    assert body["days"][0]["scenes_written"] <= 1
    assert body["days"][0]["scenes_summarized"] > 0


def test_run_rejects_unknown_fixture(monkeypatch):
    headers = _enable_operator(monkeypatch)
    resp = _client().post("/beta/debug/season/run", json={"fixture": "not_a_thing"}, headers=headers)
    assert resp.status_code == 400


def test_run_rejects_out_of_range_days(monkeypatch):
    headers = _enable_operator(monkeypatch)
    resp = _client().post("/beta/debug/season/run", json={"days": 999}, headers=headers)
    assert resp.status_code == 400
