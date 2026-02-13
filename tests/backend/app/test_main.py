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
