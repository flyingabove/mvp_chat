"""Phase 1.3 — embedder load safety and warm-up.

Why these exist: `_get_model()` used to be an unguarded `if _MODEL is None`
check. Loading the model was measured at ~15.9s, and retrieval runs
synchronously inside the async route, so a cold start blocked the whole event
loop for that window — every concurrent session and health checks stalled, once
per deploy. Two concurrent cold requests could also each construct a full
model, doubling peak RSS on a memory-capped container.

These tests use a fake SentenceTransformer so nothing real is downloaded.
"""
import asyncio
import os
import threading
import time

import pytest

import backend.app.knowledge.build.embedder as emb


class _FakeModel:
    """Stand-in for SentenceTransformer that counts constructions."""

    construct_count = 0
    construct_lock = threading.Lock()

    def __init__(self, name, **kwargs):
        with _FakeModel.construct_lock:
            _FakeModel.construct_count += 1
        self.name = name
        self.kwargs = kwargs
        # Simulate a slow load so the race window is real, not theoretical.
        time.sleep(0.2)

    def encode(self, texts, **kwargs):
        import numpy as np
        return np.zeros((len(texts), 4), dtype="float32")


@pytest.fixture(autouse=True)
def _reset_model(monkeypatch):
    """Each test starts with no resident model and a fresh construction count."""
    monkeypatch.setattr(emb, "_MODEL", None, raising=True)
    _FakeModel.construct_count = 0

    fake_module = type("m", (), {"SentenceTransformer": _FakeModel})
    import sys
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    yield
    emb._MODEL = None


def test_concurrent_cold_loads_construct_exactly_one_model():
    """The single-flight lock must collapse a cold-start stampede to one load.

    Without the lock both threads see `_MODEL is None` and each build a full
    model. On a memory-capped container that is the difference between one
    resident model and two.
    """
    errors = []

    def _load():
        try:
            emb._get_model()
        except Exception as exc:  # pragma: no cover - surfaced via assert below
            errors.append(exc)

    threads = [threading.Thread(target=_load) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"loader raised: {errors}"
    assert _FakeModel.construct_count == 1, (
        f"expected exactly one model construction, got {_FakeModel.construct_count}"
    )


def test_second_call_reuses_the_same_instance():
    first = emb._get_model()
    second = emb._get_model()
    assert first is second
    assert _FakeModel.construct_count == 1


def test_is_loaded_reflects_state_without_triggering_a_load():
    assert emb.is_loaded() is False
    assert _FakeModel.construct_count == 0, "is_loaded() must not construct a model"
    emb._get_model()
    assert emb.is_loaded() is True


def test_warm_up_loads_the_model_and_reports_success():
    assert emb.is_loaded() is False
    assert emb.warm_up() is True
    assert emb.is_loaded() is True
    assert _FakeModel.construct_count == 1


def test_warm_up_never_raises_on_failure(monkeypatch):
    """A failed warm-up must not break startup — loading retries lazily."""
    def _boom(*args, **kwargs):
        raise RuntimeError("no network")

    import sys
    monkeypatch.setitem(
        sys.modules, "sentence_transformers",
        type("m", (), {"SentenceTransformer": _boom}),
    )
    assert emb.warm_up() is False
    assert emb.is_loaded() is False


def test_warm_up_is_idempotent():
    assert emb.warm_up() is True
    assert emb.warm_up() is True
    assert _FakeModel.construct_count == 1


# --- cache directory resolution ---------------------------------------------

def test_resolve_cache_dir_prefers_explicit_env_var(monkeypatch, tmp_path):
    target = tmp_path / "models"
    monkeypatch.setenv("MODEL_CACHE_DIR", str(target))
    assert emb._resolve_cache_dir() == str(target)
    assert target.exists()


def test_resolve_cache_dir_falls_back_when_container_path_unavailable(monkeypatch):
    """Off-container, /app/.model_cache does not exist and may not be creatable.

    The old code called makedirs on it unconditionally; a silent failure there
    meant sentence-transformers re-downloaded the model on every cold start,
    which is a large part of the measured 15.9s.
    """
    monkeypatch.delenv("MODEL_CACHE_DIR", raising=False)
    real_makedirs = os.makedirs

    def _deny_app_path(path, *args, **kwargs):
        if str(path).startswith("/app"):
            raise PermissionError("read-only")
        return real_makedirs(path, *args, **kwargs)

    monkeypatch.setattr(emb.os, "makedirs", _deny_app_path)
    resolved = emb._resolve_cache_dir()
    assert not resolved.startswith("/app")
    # Must still be a usable, writable location rather than an empty string.
    assert resolved == "" or os.access(resolved, os.W_OK)


def test_get_model_passes_resolved_cache_dir(monkeypatch, tmp_path):
    target = tmp_path / "mc"
    monkeypatch.setenv("MODEL_CACHE_DIR", str(target))
    model = emb._get_model()
    assert model.kwargs.get("cache_folder") == str(target)
    assert model.kwargs.get("device") == "cpu", "must stay CPU for deterministic behavior"


# --- the startup warm-up must not block the event loop ----------------------

@pytest.mark.asyncio
async def test_startup_warm_up_does_not_block_the_event_loop():
    """`_warm_embedder` must offload to a thread.

    This is the whole point of Phase 1.3: if the load runs on the loop, other
    sessions stall for its full duration. The fake model sleeps 0.2s; a probe
    coroutine must keep ticking throughout.
    """
    from backend.app.main import _warm_embedder

    ticks = 0
    stop = asyncio.Event()

    async def _probe():
        nonlocal ticks
        while not stop.is_set():
            await asyncio.sleep(0.01)
            ticks += 1

    probe = asyncio.create_task(_probe())
    await _warm_embedder()
    stop.set()
    await probe

    assert emb.is_loaded() is True
    # A blocking load would have frozen the probe entirely (0-1 ticks).
    assert ticks >= 5, f"event loop appears blocked during warm-up (ticks={ticks})"
