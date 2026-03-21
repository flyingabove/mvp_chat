import pytest
from fastapi.testclient import TestClient


def test_stories_endpoint_is_registered(monkeypatch):
    # Prevent background warmup thread during tests.
    monkeypatch.setenv("DISABLE_INDEX_WARMUP", "1")

    from backend.app import main

    client = TestClient(main.app)
    r = client.get("/api/stories")
    assert r.status_code == 200

    data = r.json()
    assert isinstance(data, dict)
    assert "stories" in data
    assert isinstance(data["stories"], list)

    # Repo ships at least one story
    assert len(data["stories"]) > 0, "At least one story should be available"


import types

import pytest

from backend.app import main


def test_warm_indexes_uses_index_service(monkeypatch):
    # Ensure warmup is enabled
    monkeypatch.delenv("DISABLE_INDEX_WARMUP", raising=False)

    calls = []

    def fake_get(character_id=None):
        calls.append(character_id or "none")
        return "bundle"

    # Patch IndexService on the imported main module
    monkeypatch.setattr(main, "IndexService", types.SimpleNamespace(get=fake_get))

    started = []

    class DummyThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            started.append(True)

        def start(self):
            if self.target:
                self.target()

    monkeypatch.setattr(main.threading, "Thread", DummyThread)

    main.warm_indexes()

    assert started, "warm_indexes should start a background thread"
    assert calls == ["none"], "IndexService.get should be invoked once with default character"


def test_warm_indexes_respects_disable_env(monkeypatch):
    # When DISABLE_INDEX_WARMUP=1, warmup should be a no-op.
    monkeypatch.setenv("DISABLE_INDEX_WARMUP", "1")

    calls = []

    def fake_get(character_id=None):
        calls.append(character_id or "none")
        return "bundle"

    monkeypatch.setattr(main, "IndexService", types.SimpleNamespace(get=fake_get))

    started = []

    class DummyThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            started.append(True)

        def start(self):
            if self.target:
                self.target()

    monkeypatch.setattr(main.threading, "Thread", DummyThread)

    main.warm_indexes()

    assert not started, "warm_indexes should not start a thread when disabled"
    assert calls == [], "IndexService.get should not be called when warmup is disabled"


def test_startup_checks_respects_require_indexes(monkeypatch):
    calls = []

    def fake_get(character_id=None):
        calls.append(character_id or "none")
        return "bundle"

    monkeypatch.setattr(main, "IndexService", types.SimpleNamespace(get=fake_get))
    monkeypatch.setenv("REQUIRE_INDEXES", "1")

    main._startup_checks()

    assert calls == ["none"], "IndexService.get should be called during startup when REQUIRE_INDEXES=1"

    # cleanup
    monkeypatch.delenv("REQUIRE_INDEXES", raising=False)


import types

import pytest
from fastapi.testclient import TestClient

from tests.conftest import first_story_id

STORY_ID = first_story_id()


@pytest.fixture()
def client(monkeypatch):
    """Create a FastAPI TestClient with network calls mocked."""
    # Import inside fixture so our monkeypatches apply before first use.
    from backend.app.api import prompt_engine as chat_mod

    # Prevent retrieval from doing any IO during tests.
    monkeypatch.setattr(chat_mod, "retrieve_knowledge", lambda *args, **kwargs: ([], {}), raising=False)

    # Mock httpx.AsyncClient so /api/chat never hits OpenAI.

    class _FakeResp:
        status_code = 200

        def json(self):
            # Reply must include a valid [[STATE]] tag so state parsing passes.
            return {
                "choices": [{"message": {"content": "*ok*\n\n**\"hi\"**\n[[STATE]]{\"emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"}}],
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

    from backend.app import main
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
    r = client.get("/api/story/" + STORY_ID)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == STORY_ID
    assert data["title"]


