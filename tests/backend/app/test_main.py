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
    # Build identity (audit P2: no way to confirm what commit a live
    # deployment is serving) - must be present and non-empty.
    assert data["commit"]
    assert data["environment"]
    assert isinstance(data["content_schema_version"], int)


def test_version_json_endpoints_expose_build_identity(client):
    for path in ("/version.json", "/beta/version.json"):
        r = client.get(path)
        assert r.status_code == 200
        data = r.json()
        assert data["commit"]
        assert data["environment"]
        assert isinstance(data["content_schema_version"], int)


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "php" in data
    assert data["commit"]
    assert data["environment"]
    assert isinstance(data["content_schema_version"], int)


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


# ---------------------------------------------------------------------------
# BL-01b: startup recovery sweep for the fact-extraction outbox (final
# remaining piece of Six Strangers audit Phase 1).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fact_extraction_recovery_sweep_reprocesses_pending_row(monkeypatch):
    """Simulates the exact failure mode BL-01b closes: a row left 'pending'
    by a prior process crash (enqueued, but the in-process extraction task
    never got to run/complete). The startup sweep must reprocess it and mark
    it done."""
    from backend.app import main
    from backend.app.db.database import init_db
    from backend.app.db.repos import FactExtractionOutboxRepo

    init_db()
    row_id = await FactExtractionOutboxRepo.enqueue(
        session_id="crash_recovery_sess", user_id="guest:recovery-uuid",
        user_msg="what happened here?", user_msg_id="umsg-r1",
        ai_reply="A story unfolds...", ai_msg_id="aimsg-r1",
        character_id="mizuki",
    )

    extract_calls = []

    async def _fake_extract(text, role, msg_id, char_id):
        extract_calls.append((text, role, msg_id, char_id))
        return []

    monkeypatch.setattr(
        "backend.app.api.prompt_engine.extract_facts_from_message", _fake_extract, raising=False,
    )

    await main._fact_extraction_recovery_sweep()

    assert len(extract_calls) == 2, "recovery sweep must extract from both the stored user_msg and ai_reply"
    assert extract_calls[0] == ("what happened here?", "user", "umsg-r1", "mizuki")
    assert extract_calls[1] == ("A story unfolds...", "assistant", "aimsg-r1", "mizuki")

    pending_after = await FactExtractionOutboxRepo.fetch_pending()
    assert not any(row["id"] == row_id for row in pending_after), (
        "recovered row must no longer be 'pending' after the sweep"
    )


@pytest.mark.asyncio
async def test_fact_extraction_recovery_sweep_marks_row_failed_on_error(monkeypatch):
    from backend.app import main
    from backend.app.db.database import init_db
    from backend.app.db.repos import FactExtractionOutboxRepo, get_connection

    init_db()
    row_id = await FactExtractionOutboxRepo.enqueue(
        session_id="crash_recovery_fail_sess", user_id="guest:recovery-uuid-2",
        user_msg="a message", user_msg_id="umsg-r2",
        ai_reply="a reply", ai_msg_id="aimsg-r2",
        character_id="mizuki",
    )

    async def _raising_extract(*args, **kwargs):
        raise RuntimeError("recovery extraction failed")

    monkeypatch.setattr(
        "backend.app.api.prompt_engine.extract_facts_from_message", _raising_extract, raising=False,
    )

    await main._fact_extraction_recovery_sweep()

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM fact_extraction_outbox WHERE id = ?", (row_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["status"] == "failed"
    assert "recovery extraction failed" in row["last_error"]


@pytest.mark.asyncio
async def test_fact_extraction_recovery_sweep_prunes_old_done_rows(monkeypatch):
    import time as _time
    from backend.app import main
    from backend.app.db.database import init_db
    from backend.app.db.repos import FactExtractionOutboxRepo, get_connection

    init_db()
    old_row_id = await FactExtractionOutboxRepo.enqueue(
        session_id="prune_sess", user_id="guest:prune-uuid",
        user_msg="m", user_msg_id="u1", ai_reply="r", ai_msg_id="a1",
        character_id="c1",
    )
    await FactExtractionOutboxRepo.mark_done(old_row_id)
    old_cutoff = int(_time.time()) - main.FACT_EXTRACTION_OUTBOX_RETENTION_SECONDS - 1000
    conn = get_connection()
    conn.execute(
        "UPDATE fact_extraction_outbox SET completed_at = ? WHERE id = ?",
        (old_cutoff, old_row_id),
    )
    conn.commit()
    conn.close()

    await main._fact_extraction_recovery_sweep()

    conn = get_connection()
    try:
        remaining = conn.execute(
            "SELECT id FROM fact_extraction_outbox WHERE id = ?", (old_row_id,)
        ).fetchall()
    finally:
        conn.close()
    assert remaining == [], "a 'done' row older than the retention window must be pruned by the sweep"


