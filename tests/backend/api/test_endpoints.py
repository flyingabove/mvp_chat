import types

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """Create a FastAPI TestClient with network calls mocked."""
    # Import inside fixture so our monkeypatches apply before first use.
    from app.engine import prompt_builder as pb

    # Prevent prompt_builder from performing any retrieval during tests.
    monkeypatch.setattr(pb, "_retrieve_memory", lambda *args, **kwargs: {"chunks": []}, raising=False)

    # Mock httpx.AsyncClient so /api/chat never hits OpenAI.
    import app.api.chat as chat_mod

    class _FakeResp:
        status_code = 200

        def json(self):
            # Reply must include a valid [[STATE]] tag so state parsing passes.
            return {
                "choices": [{"message": {"content": "*ok*\n\n**\"hi\"**\n[[STATE]]{\"iu_emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"}}],
                "usage": {"total_tokens": 1},
            }

        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return _FakeResp()

    monkeypatch.setattr(chat_mod.httpx, "AsyncClient", _FakeAsyncClient)

    from app import main
    return TestClient(main.app)


def test_version_endpoint(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "php" in data


def test_echo_endpoint(client):
    r = client.post("/api/echo", json={"x": 1})
    assert r.status_code == 200
    data = r.json()
    assert data["method"] == "POST"
    assert data["json"] == {"x": 1}


def test_story_endpoint_existing(client):
    r = client.get("/api/story/iu_murder_mystery")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "iu_murder_mystery"
    assert data["title"]


def test_chat_newgame_and_turn(client):
    # Start a new game
    r = client.post("/api/chat", json={"session_id": "s1", "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"})
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data

    # Do a turn (will use mocked OpenAI response)
    r2 = client.post("/api/chat", json={"session_id": "s1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "reply" in data2
    assert "[[STATE]]" not in data2["reply"]  # tag should be stripped


def test_game_logic_router_not_included_in_main(client):
    # /api/game-logic is defined but not included in main.py
    r = client.get("/api/game-logic")
    assert r.status_code == 404
