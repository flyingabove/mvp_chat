import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def ui_module(tmp_path, monkeypatch):
    ui = importlib.import_module("scripts.scorer.story_agent_ui")
    monkeypatch.setattr(ui, "SCORES_CSV", tmp_path / "scores.csv")
    monkeypatch.setattr(ui, "TEST_CASES_FILE", tmp_path / "test_cases.json")
    monkeypatch.setattr(ui, "SCORER_INSTRUCTIONS_FILE", tmp_path / "scorer_instructions.md")
    return ui


@pytest.fixture
def client(ui_module, monkeypatch):
    async def fake_check_ollama():
        return {"available": True, "models": ["model-a", "model-b"]}

    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            return FakeResp({"stories": [{"id": "s1", "title": "Story 1"}]})

        async def post(self, url, json=None):
            return FakeResp({})

    monkeypatch.setattr(ui_module, "check_ollama", fake_check_ollama)
    monkeypatch.setattr(ui_module.httpx, "AsyncClient", FakeAsyncClient)
    return TestClient(ui_module.app)


def test_append_and_read_scores(ui_module):
    ui_module._append_score_csv({
        "timestamp": "now",
        "run_id": "run1",
        "story_id": "story-a",
        "player_name": "Alex",
        "chatter_model": "chat-a",
        "rater_model": "rate-b",
        "eval_persona": "curious_rookie",
        "turns": 3,
        "canon_fidelity": 5,
    })

    rows = ui_module._read_scores_csv()
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run1"
    assert rows[0]["canon_fidelity"] == "5"


def test_save_and_load_test_cases(ui_module):
    cases = [{"id": "tc1", "name": "Case 1", "messages": ["hello", "bye"]}]
    ui_module._save_test_cases(cases)
    assert ui_module._load_test_cases() == cases


def test_load_scorer_instructions_missing_returns_empty(ui_module):
    ui_module.SCORER_INSTRUCTIONS_FILE.unlink(missing_ok=True)
    assert ui_module._load_scorer_instructions() == ""


def test_status_endpoint_uses_mocked_clients(client):
    resp = client.get("/api/status")
    data = resp.json()
    assert data["ollama"]["available"] is True
    assert data["stories"] == [{"id": "s1", "title": "Story 1"}]


def test_test_cases_api_round_trip(client):
    payload = {"test_cases": [{"id": "tc", "messages": ["hi"]}]}
    post_resp = client.post("/api/test-cases", json=payload)
    assert post_resp.status_code == 200

    get_resp = client.get("/api/test-cases")
    assert get_resp.status_code == 200
    assert get_resp.json() == payload["test_cases"]


def test_scores_endpoint_reads_csv(ui_module, client):
    ui_module._append_score_csv({
        "timestamp": "now",
        "run_id": "run2",
        "story_id": "story-b",
        "player_name": "Alex",
        "chatter_model": "chat-a",
        "rater_model": "rate-b",
        "eval_persona": "curious_rookie",
        "turns": 2,
        "canon_fidelity": 4,
    })

    resp = client.get("/api/scores")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run2"
    assert rows[0]["canon_fidelity"] == "4"
