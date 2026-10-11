"""BL-90/BL-92: the operator probe, constant-time token check, REST header-only tokens."""
from fastapi.testclient import TestClient

from backend.app.api.eval_capabilities import eval_capabilities
from backend.app.auth import dependencies as deps


def _client():
    from backend.app.main import app
    return TestClient(app)


def test_ping_reports_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DEBUG_TOOLS_ENABLED", raising=False)
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    assert _client().get("/api/debug/ping").json() == {
        "debug_tools_enabled": False, "operator_configured": False, "operator_token_ok": False}


def test_ping_tells_a_valid_token_from_an_invalid_one_and_leaks_nothing(monkeypatch):
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "s3cret-value")
    client = _client()
    ok = client.get("/api/debug/ping", headers={"X-Operator-Token": "s3cret-value"})
    bad = client.get("/api/debug/ping", headers={"X-Operator-Token": "nope"})
    assert ok.json()["operator_token_ok"] is True and bad.json()["operator_token_ok"] is False
    assert "s3cret-value" not in ok.text + bad.text


def test_rest_refuses_the_token_in_the_query_string(monkeypatch):
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "tok")
    client = _client()
    assert client.get("/beta/debug/scores?operator_token=tok").status_code == 401
    assert client.get("/api/debug/ping?operator_token=tok").json()["operator_token_ok"] is False
    assert client.get("/beta/debug/scores", headers={"X-Operator-Token": "tok"}).status_code == 200


def test_token_comparison_is_constant_time(monkeypatch):
    calls = []
    real = deps.hmac.compare_digest
    monkeypatch.setattr(deps.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert deps._token_matches("abc", "abc") is True
    assert deps._token_matches("abd", "abc") is False
    assert deps._token_matches("", "abc") is False and deps._token_matches("abc", "") is False
    assert deps._token_matches("é", "é") is True  # non-ASCII must not raise
    assert len(calls) == 3


def test_capabilities_advertise_the_new_surfaces():
    features = eval_capabilities()["features"]
    assert features["operator_turn_trace"] is True and features["operator_session_inspector"] is True
