"""Tests for the debug system — now in backend/app/api/debug_engine.py.

story_agent_ui.py is now a thin launcher only; all logic moved to debug_engine.
These tests exercise the debug_engine functions directly.
"""
from __future__ import annotations

import importlib

import pytest

from backend.app.api import debug_engine


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """Patch debug_engine storage paths to a temp dir."""
    monkeypatch.setattr(debug_engine, "SCORES_CSV", tmp_path / "debug_scores.csv")
    monkeypatch.setattr(debug_engine, "TEST_CASES_FILE", tmp_path / "test_cases.json")
    monkeypatch.setattr(
        debug_engine, "_SCORER_INSTRUCTIONS_PATH", tmp_path / "scorer_instructions.md"
    )
    return debug_engine


def test_append_and_read_scores(engine, tmp_path):
    engine._append_score_csv({
        "timestamp": "2026-01-01 00:00:00",
        "run_id": "run1",
        "story_id": "story-a",
        "player_name": "Alex",
        "player_model": "llama3.1:8b",
        "grader_model": "gemma3:12b",
        "player_persona": "curious_rookie",
        "grader_persona": "expert_llm_grader",
        "eval_persona": "expert_llm_grader",
        "turns": 3,
        "canon_fidelity": 5,
    })

    rows = engine._read_scores_csv()
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run1"
    assert rows[0]["canon_fidelity"] == "5"
    assert rows[0]["player_persona"] == "curious_rookie"
    assert rows[0]["grader_persona"] == "expert_llm_grader"


def test_save_and_load_test_cases(engine):
    cases = [{"name": "Confusing IU #1", "messages": ["what happened to the previous tenant?"], "strategy": ""}]
    engine._save_test_cases(cases)
    assert engine._load_test_cases() == cases


def test_load_scorer_instructions_missing_returns_empty(engine):
    result = engine._load_scorer_instructions()
    assert result == ""


def test_load_scorer_instructions_reads_file(engine, tmp_path):
    instructions_file = tmp_path / "scorer_instructions.md"
    instructions_file.write_text("# Score rubric\nBe accurate.", encoding="utf-8")
    import backend.app.api.debug_engine as de
    from unittest.mock import patch
    with patch.object(de, "_SCORER_INSTRUCTIONS_PATH", instructions_file):
        result = de._load_scorer_instructions()
    assert "Score rubric" in result


def test_scores_endpoint_reads_csv(engine, tmp_path, monkeypatch):
    """GET /beta/debug/scores returns CSV rows as JSON.

    A03: this route is operator-gated, so the test authenticates with the
    same DEBUG_TOOLS_ENABLED / OPERATOR_TOKEN env vars + X-Operator-Token
    header a real operator would use.
    """
    engine._append_score_csv({
        "timestamp": "2026-01-01 00:00:00",
        "run_id": "run2",
        "story_id": "story-b",
        "player_name": "Alex",
        "player_model": "llama3.1:8b",
        "grader_model": "gemma3:12b",
        "player_persona": "curious_rookie",
        "grader_persona": "curious_rookie",
        "eval_persona": "curious_rookie",
        "turns": 2,
        "canon_fidelity": 4,
    })

    from fastapi.testclient import TestClient
    from backend.app.main import app

    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "test-operator-token")

    client = TestClient(app)
    # Patch scores path on the module before reading
    import backend.app.api.debug_engine as de
    from unittest.mock import patch
    with patch.object(de, "SCORES_CSV", tmp_path / "debug_scores.csv"):
        resp = client.get(
            "/beta/debug/scores",
            headers={"X-Operator-Token": "test-operator-token"},
        )

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run2"
    assert rows[0]["canon_fidelity"] == "4"


def test_test_cases_api_round_trip(engine, tmp_path, monkeypatch):
    """POST + GET /beta/debug/test-cases should round-trip correctly.

    A03: authenticate as operator (see test_scores_endpoint_reads_csv).
    """
    from fastapi.testclient import TestClient
    from backend.app.main import app
    import backend.app.api.debug_engine as de
    from unittest.mock import patch

    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "test-operator-token")
    op_headers = {"X-Operator-Token": "test-operator-token"}

    payload = {"test_cases": [{"name": "Case 1", "messages": ["hi"], "strategy": ""}]}

    with patch.object(de, "TEST_CASES_FILE", tmp_path / "test_cases.json"):
        client = TestClient(app)
        post_resp = client.post("/beta/debug/test-cases", json=payload, headers=op_headers)
        assert post_resp.status_code == 200

        get_resp = client.get("/beta/debug/test-cases", headers=op_headers)
        assert get_resp.status_code == 200
        assert get_resp.json() == payload["test_cases"]


def test_launcher_has_no_old_attributes():
    """story_agent_ui.py is now a thin launcher — it must NOT have old logic attributes."""
    ui = importlib.import_module("scripts.scorer.story_agent_ui")
    assert not hasattr(ui, "HTML_PAGE"), "HTML_PAGE should be in frontend/debug.html, not the launcher"
    assert not hasattr(ui, "SCORES_CSV"), "SCORES_CSV should be in debug_engine, not the launcher"
    assert not hasattr(ui, "_append_score_csv"), "CSV logic should be in debug_engine, not the launcher"


def test_debug_ui_route_serves_html(tmp_path):
    """GET /beta/debug must return 200 with HTML content.

    Mocks _DEBUG_HTML_PATH to a temp file so the test is filesystem-independent
    and passes both locally and in Railway (where frontend/ path layout may differ).
    """
    from fastapi.testclient import TestClient
    import backend.app.main as main_module

    fake_html = "<html><body><h1>Debug UI</h1></body></html>"
    fake_path = tmp_path / "debug.html"
    fake_path.write_text(fake_html, encoding="utf-8")

    original = main_module._DEBUG_HTML_PATH
    main_module._DEBUG_HTML_PATH = fake_path
    try:
        client = TestClient(main_module.app)
        resp = client.get("/beta/debug")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Debug UI" in resp.text
    finally:
        main_module._DEBUG_HTML_PATH = original


def test_prod_debug_route_serves_html(tmp_path):
    """GET /debug (prod debug URL) must serve the same debug HTML."""
    from fastapi.testclient import TestClient
    import backend.app.main as main_module

    fake_html = "<html><body><h1>Debug UI</h1></body></html>"
    fake_path = tmp_path / "debug.html"
    fake_path.write_text(fake_html, encoding="utf-8")

    original = main_module._DEBUG_HTML_PATH
    main_module._DEBUG_HTML_PATH = fake_path
    try:
        client = TestClient(main_module.app)
        resp = client.get("/debug")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Debug UI" in resp.text
    finally:
        main_module._DEBUG_HTML_PATH = original


def test_game_ui_root_serves_html(tmp_path):
    """GET / must serve index.html (prod game UI)."""
    from fastapi.testclient import TestClient
    import backend.app.main as main_module

    fake_html = "<html><body><h1>Game UI</h1></body></html>"
    fake_path = tmp_path / "index.html"
    fake_path.write_text(fake_html, encoding="utf-8")

    original = main_module._INDEX_HTML_PATH
    # The shell now fingerprints its delivered resources as one deployment.
    for name in ("sw.js", "manifest.json", *main_module._SHELL_ASSETS):
        (tmp_path / name).write_bytes((original.parent / name).read_bytes())
    main_module._INDEX_HTML_PATH = fake_path
    try:
        client = TestClient(main_module.app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Game UI" in resp.text
    finally:
        main_module._INDEX_HTML_PATH = original


def test_beta_game_ui_route_serves_html(tmp_path):
    """GET /beta/ must serve index.html (beta game UI, path triggers isBeta in JS)."""
    from fastapi.testclient import TestClient
    import backend.app.main as main_module

    fake_html = "<html><body><h1>Game UI</h1></body></html>"
    fake_path = tmp_path / "index.html"
    fake_path.write_text(fake_html, encoding="utf-8")

    original = main_module._INDEX_HTML_PATH
    # The shell now fingerprints its delivered resources as one deployment.
    for name in ("sw.js", "manifest.json", *main_module._SHELL_ASSETS):
        (tmp_path / name).write_bytes((original.parent / name).read_bytes())
    main_module._INDEX_HTML_PATH = fake_path
    try:
        client = TestClient(main_module.app)
        resp = client.get("/beta/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Game UI" in resp.text
    finally:
        main_module._INDEX_HTML_PATH = original
