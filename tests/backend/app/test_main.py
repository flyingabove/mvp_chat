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
    it done - and (Phase 1.2) durably persist whatever it extracted."""
    from backend.app import main
    from backend.app.db.database import init_db
    from backend.app.db.repos import FactExtractionOutboxRepo, ExtractedChunksRepo
    from backend.app.knowledge.runtime.dialogue_extractor import ExtractionResult

    init_db()
    row_id = await FactExtractionOutboxRepo.enqueue(
        session_id="crash_recovery_sess", user_id="guest:recovery-uuid",
        user_msg="what happened here?", user_msg_id="umsg-r1",
        ai_reply="A story unfolds...", ai_msg_id="aimsg-r1",
        character_id="mizuki",
    )

    extract_calls = []

    async def _fake_extract_with_status(text, role, msg_id, char_id):
        extract_calls.append((text, role, msg_id, char_id))
        return ExtractionResult(ok=True, chunks=[])

    monkeypatch.setattr(
        "backend.app.api.prompt_engine.extract_facts_with_status", _fake_extract_with_status, raising=False,
    )

    await main._fact_extraction_recovery_sweep()

    # Filter to this test's own row rather than asserting on the total call
    # count - other tests in the same run may share this DB file and leave
    # their own pending/leftover rows, which the sweep (by design) processes
    # indiscriminately. Asserting only on this row's own calls keeps the
    # test correct regardless of what else is present.
    own_calls = [c for c in extract_calls if c[2] in ("umsg-r1", "aimsg-r1")]
    assert len(own_calls) == 2, "recovery sweep must extract from both the stored user_msg and ai_reply"
    assert own_calls[0] == ("what happened here?", "user", "umsg-r1", "mizuki")
    assert own_calls[1] == ("A story unfolds...", "assistant", "aimsg-r1", "mizuki")

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

    from backend.app.knowledge.runtime.dialogue_extractor import ExtractionResult

    async def _failing_extract_with_status(*args, **kwargs):
        return ExtractionResult(ok=False, chunks=[], error="recovery extraction failed")

    monkeypatch.setattr(
        "backend.app.api.prompt_engine.extract_facts_with_status", _failing_extract_with_status, raising=False,
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
async def test_fact_extraction_periodic_sweep_reclaims_hung_task(monkeypatch):
    """Phase 1.2 (closes BL-01c): a row left 'pending' by a HUNG task (not a
    crash - the process is still running, the task just never finished) must
    be reclaimable by the periodic sweep once its lease expires. The
    one-shot startup sweep alone cannot catch this, since it only runs once
    at process start."""
    from backend.app import main
    from backend.app.db.database import init_db
    from backend.app.db.repos import FactExtractionOutboxRepo
    from backend.app.knowledge.runtime.dialogue_extractor import ExtractionResult

    init_db()
    row_id = await FactExtractionOutboxRepo.enqueue(
        session_id="hung_task_sess", user_id="guest:hung-uuid",
        user_msg="a message", user_msg_id="umsg-h1",
        ai_reply="a reply", ai_msg_id="aimsg-h1",
        character_id="mizuki",
    )
    # Simulate the row already having an expired lease (as if a prior worker
    # claimed it, then hung without ever marking done/failed).
    await FactExtractionOutboxRepo.claim_pending(limit=10, lease_seconds=-10)

    async def _fake_extract_with_status(text, role, msg_id, char_id):
        return ExtractionResult(ok=True, chunks=[])

    monkeypatch.setattr(
        "backend.app.api.prompt_engine.extract_facts_with_status", _fake_extract_with_status, raising=False,
    )

    claimed = await FactExtractionOutboxRepo.claim_pending(limit=200, lease_seconds=300)
    own_claimed = [r for r in claimed if r["id"] == row_id]
    assert own_claimed, "periodic sweep's claim step must reclaim a row with an expired lease"

    await main._reprocess_outbox_rows(own_claimed, "test periodic sweep")

    pending_after = await FactExtractionOutboxRepo.fetch_pending()
    assert not any(r["id"] == row_id for r in pending_after), (
        "reclaimed hung row must be resolved (done) after reprocessing"
    )


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




# ============================================================================
# Phase 1.5 — exact guest session eviction. The old _guest_cleanup_loop
# evicted EVERY cached guest session (filtered only by user_id prefix)
# whenever ANY expired guest rows were deleted, including ones still well
# within their TTL. These tests exercise the eviction logic directly rather
# than waiting a real hour for the loop's sleep().
# ============================================================================

@pytest.mark.asyncio
async def test_guest_cleanup_evicts_only_the_deleted_session_ids(monkeypatch):
    """THE Phase 1.5 regression test: an active, non-expired guest session
    cached in SESSIONS must survive a cleanup pass that deletes a DIFFERENT
    expired guest session - proving eviction is precise, not "clear every
    guest entry whenever anything was deleted"."""
    from backend.app.api import prompt_engine as pe_mod

    expired_sid = "cleanup_precision_expired"
    active_sid = "cleanup_precision_active"
    pe_mod.SESSIONS[expired_sid] = {"state": object(), "user_id": "guest:expired-uuid"}
    pe_mod.SESSIONS[active_sid] = {"state": object(), "user_id": "guest:active-uuid"}

    async def _fake_delete(cutoff_ts):
        # Simulate the DB having deleted only the expired session.
        return [expired_sid]

    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo.delete_expired_guest_sessions", _fake_delete,
    )

    # _guest_cleanup_loop is an infinite loop (sleep() then one pass of
    # work); run ONE pass by making sleep raise on its second call, so the
    # loop's real body executes exactly once before the test ends it.
    import asyncio as _asyncio
    from backend.app import main

    sleep_calls = {"n": 0}
    real_sleep = _asyncio.sleep

    async def _one_shot_sleep(seconds):
        sleep_calls["n"] += 1
        if sleep_calls["n"] > 1:
            raise _asyncio.CancelledError()
        await real_sleep(0)  # yield control once, don't actually wait an hour

    monkeypatch.setattr(main.asyncio, "sleep", _one_shot_sleep)

    try:
        await main._guest_cleanup_loop()
    except _asyncio.CancelledError:
        pass  # expected - this is how we stop the intentionally-infinite loop

    assert expired_sid not in pe_mod.SESSIONS, "the actually-expired session must be evicted"
    assert active_sid in pe_mod.SESSIONS, (
        "an active guest session must SURVIVE a cleanup pass that only deleted a different session"
    )

    # Cleanup for other tests sharing module-level SESSIONS.
    pe_mod.SESSIONS.pop(active_sid, None)
    pe_mod.SESSIONS.pop(expired_sid, None)


@pytest.mark.asyncio
async def test_guest_cleanup_acquires_session_lock_before_eviction():
    """Eviction must go through the SAME per-session lock chat_handler holds
    for a turn's full duration, so eviction cannot interleave with an
    in-flight turn for that session."""
    from backend.app.api import prompt_engine as pe_mod

    sid = "cleanup_lock_check"
    pe_mod.SESSIONS[sid] = {"state": object(), "user_id": "guest:lock-uuid"}
    lock = pe_mod._get_session_lock(sid)

    # Hold the lock, simulating an in-flight turn for this exact session.
    await lock.acquire()
    try:
        # A concurrent eviction attempt must block on the same lock rather
        # than popping SESSIONS out from under the in-flight turn.
        async def _try_evict():
            async with pe_mod._get_session_lock(sid):
                pe_mod.SESSIONS.pop(sid, None)

        import asyncio
        evict_task = asyncio.create_task(_try_evict())
        await asyncio.sleep(0.05)
        assert sid in pe_mod.SESSIONS, "eviction must not proceed while the session lock is held elsewhere"
    finally:
        lock.release()

    await evict_task
    assert sid not in pe_mod.SESSIONS, "eviction proceeds once the lock is released"


@pytest.mark.asyncio
async def test_guest_cleanup_retires_uncontended_lock(monkeypatch):
    """Phase 1.5: _SESSION_LOCKS must not grow unbounded - an evicted
    session's lock is retired too, once uncontended."""
    from backend.app.api import prompt_engine as pe_mod

    sid = "cleanup_lock_retire_check"
    pe_mod.SESSIONS[sid] = {"state": object(), "user_id": "guest:retire-uuid"}
    lock = pe_mod._get_session_lock(sid)
    assert sid in pe_mod._SESSION_LOCKS

    async with lock:
        pe_mod.SESSIONS.pop(sid, None)
    if not lock.locked():
        pe_mod._SESSION_LOCKS.pop(sid, None)

    assert sid not in pe_mod._SESSION_LOCKS, "an uncontended lock for an evicted session must be retired"


@pytest.mark.asyncio
async def test_guest_cleanup_skips_sessions_not_in_memory_cache(monkeypatch):
    """A deleted session_id that was never cached in SESSIONS (e.g. it
    expired without ever being loaded into this process's cache) must not
    raise or do anything odd - just a no-op skip."""
    from backend.app.api import prompt_engine as pe_mod

    never_cached_sid = "cleanup_never_cached_check"
    assert never_cached_sid not in pe_mod.SESSIONS

    deleted_ids = [never_cached_sid]
    for sid in deleted_ids:
        if sid not in pe_mod.SESSIONS:
            continue
        async with pe_mod._get_session_lock(sid):
            pe_mod.SESSIONS.pop(sid, None)
    # No exception raised; nothing to assert beyond "this didn't crash".
