"""Shared fixtures for the API tests."""
import pytest


@pytest.fixture(autouse=True)
def no_real_embedder_warmup(monkeypatch):
    """BL-62: `with client:` runs the app lifespan, which fires `_warm_embedder` and would build the real
    SentenceTransformer (10-15 s, plus a download on a cold cache). API tests never need the model; the warm-up
    itself is covered with a fake model in tests/backend/app/knowledge/test_embedder_warmup.py."""
    async def _skip() -> None:
        return None

    monkeypatch.setattr("backend.app.main._warm_embedder", _skip)
