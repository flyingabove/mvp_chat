import os
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
