"""App-side support for the local game arena: build identity for release
pinning and the read-only capabilities contract. (The arena itself lives in
.claude/skills/promote-to-prod and never runs inside a deployment.)"""
from fastapi.testclient import TestClient

from backend.app.api.eval_capabilities import EVAL_CAPABILITIES_CONTRACT, eval_capabilities
from backend.app.config.build_info import get_build_info


def test_build_info_exposes_deployment_id_for_pinning(monkeypatch):
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-123")
    assert get_build_info()["deployment_id"] == "dep-123"


def test_eval_capabilities_contract_shape():
    caps = eval_capabilities()
    assert caps["contract_version"] == EVAL_CAPABILITIES_CONTRACT
    assert caps["features"]["request_id_idempotency"] is True
    assert caps["features"]["snapshot_restore"] is False
    assert "deployment_id" in caps["build"]


def test_eval_capabilities_route_is_public_and_read_only():
    from backend.app.main import app

    client = TestClient(app)
    r = client.get("/api/eval/capabilities")
    assert r.status_code == 200 and r.json()["contract_version"] == EVAL_CAPABILITIES_CONTRACT
    assert client.post("/api/eval/capabilities").status_code == 405


def test_arena_runs_are_not_served_by_the_app():
    """The arena is local-only tooling; no deployment can start a run."""
    from backend.app.main import app

    assert "arena_runs" not in eval_capabilities()["features"]
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any(p.startswith("/api/eval/runs") for p in paths)
