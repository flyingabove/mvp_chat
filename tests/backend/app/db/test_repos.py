"""Unit tests for SQLite repos using an in-memory DB."""
import sqlite3
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------
# Schema is created via the real init_db() against a patched DB_PATH, rather
# than a hand-copied schema string, so this fixture can never silently drift
# from database.py's actual schema (it drifted twice - BL-02's dedup columns,
# then BL-01b's fact_extraction_outbox table - before being fixed this way).


@pytest.fixture()
def tmp_data_dir(tmp_path):
    """Patch DATA_DIR and DB_PATH to use a temp directory."""
    db_path = tmp_path / "storieschat.db"

    with patch("backend.app.db.database.DATA_DIR", tmp_path), \
         patch("backend.app.db.database.DB_PATH", db_path), \
         patch("backend.app.db.repos.DATA_DIR", tmp_path):
        from backend.app.db.database import init_db
        init_db()

        # Also patch get_connection to use our db_path
        def patched_conn():
            c = sqlite3.connect(str(db_path), check_same_thread=False)
            c.row_factory = sqlite3.Row
            return c

        with patch("backend.app.db.database.get_connection", patched_conn), \
             patch("backend.app.db.repos.get_connection", patched_conn):
            yield tmp_path


# ---------------------------------------------------------------------------
# UserRepo tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_and_get_user(tmp_data_dir):
    from backend.app.db.repos import UserRepo
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", "https://pic.url/a.png")
    user = await UserRepo.get_user("uid1")
    assert user is not None
    assert user["email"] == "a@b.com"
    assert user["name"] == "Alice"
    assert user["avatar_url"] == "https://pic.url/a.png"


@pytest.mark.asyncio
async def test_upsert_updates_existing_user(tmp_data_dir):
    from backend.app.db.repos import UserRepo
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", None)
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice Updated", "https://new.url/a.png")
    user = await UserRepo.get_user("uid1")
    assert user["name"] == "Alice Updated"
    assert user["avatar_url"] == "https://new.url/a.png"


@pytest.mark.asyncio
async def test_get_nonexistent_user_returns_none(tmp_data_dir):
    from backend.app.db.repos import UserRepo
    user = await UserRepo.get_user("doesnotexist")
    assert user is None


# ---------------------------------------------------------------------------
# SessionRepo tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_and_get_session(tmp_data_dir):
    from backend.app.db.repos import UserRepo, SessionRepo
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", None)
    await SessionRepo.create_or_update_session(
        session_id="sess1", user_id="uid1", story_id="story_abc",
        story_title="The Mystery", player_name="Alex", gender="M",
        state_json='{"story":"story_abc"}', flags_json="{}",
        last_message="Hello world", turns=5,
    )
    sess = await SessionRepo.get_session("sess1", "uid1")
    assert sess is not None
    assert sess["story_id"] == "story_abc"
    assert sess["turns"] == 5
    assert sess["player_name"] == "Alex"


@pytest.mark.asyncio
async def test_session_ownership_isolation(tmp_data_dir):
    """A user cannot access another user's session."""
    from backend.app.db.repos import UserRepo, SessionRepo
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", None)
    await UserRepo.upsert_user("uid2", "b@b.com", "Bob", None)
    await SessionRepo.create_or_update_session(
        session_id="sess1", user_id="uid1", story_id="s1",
        story_title="T", player_name="A", gender="M",
        state_json="{}", flags_json="{}", turns=0,
    )
    sess = await SessionRepo.get_session("sess1", "uid2")
    assert sess is None


@pytest.mark.asyncio
async def test_upsert_rejects_cross_owner_overwrite(tmp_data_dir):
    """A02/A01: SQL upsert must not let a different owner overwrite an
    existing session's state_json just because the session id collides.
    Regression test for the finding that ON CONFLICT(id) DO UPDATE had no
    owner condition, so a caller who knows/guesses another owner's session_id
    could silently clobber that owner's saved state."""
    from backend.app.db.repos import UserRepo, SessionRepo, SessionOwnershipError
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", None)
    await UserRepo.upsert_user("uid2", "b@b.com", "Bob", None)
    await SessionRepo.create_or_update_session(
        session_id="shared_id", user_id="uid1", story_id="s1",
        story_title="Alice's Story", player_name="Alice", gender="F",
        state_json='{"owner":"alice"}', flags_json="{}", turns=10,
    )

    with pytest.raises(SessionOwnershipError):
        await SessionRepo.create_or_update_session(
            session_id="shared_id", user_id="uid2", story_id="s1",
            story_title="Bob's Story", player_name="Bob", gender="M",
            state_json='{"owner":"bob"}', flags_json="{}", turns=1,
        )

    # Alice's original row must be untouched.
    sess = await SessionRepo.get_session("shared_id", "uid1")
    assert sess is not None
    assert sess["state_json"] == '{"owner":"alice"}'
    assert sess["turns"] == 10


@pytest.mark.asyncio
async def test_list_user_sessions(tmp_data_dir):
    from backend.app.db.repos import UserRepo, SessionRepo
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", None)
    for i in range(3):
        await SessionRepo.create_or_update_session(
            session_id=f"sess{i}", user_id="uid1", story_id="story_abc",
            story_title="T", player_name="A", gender="M",
            state_json="{}", flags_json="{}", turns=i,
        )
    sessions = await SessionRepo.list_user_sessions("uid1")
    assert len(sessions) == 3


@pytest.mark.asyncio
async def test_delete_session(tmp_data_dir):
    from backend.app.db.repos import UserRepo, SessionRepo
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", None)
    await SessionRepo.create_or_update_session(
        session_id="sess1", user_id="uid1", story_id="s1",
        story_title="T", player_name="A", gender="M",
        state_json="{}", flags_json="{}", turns=0,
    )
    deleted = await SessionRepo.delete_session("sess1", "uid1")
    assert deleted is True
    sess = await SessionRepo.get_session("sess1", "uid1")
    assert sess is None


@pytest.mark.asyncio
async def test_delete_other_users_session_returns_false(tmp_data_dir):
    from backend.app.db.repos import UserRepo, SessionRepo
    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", None)
    await UserRepo.upsert_user("uid2", "b@b.com", "Bob", None)
    await SessionRepo.create_or_update_session(
        session_id="sess1", user_id="uid1", story_id="s1",
        story_title="T", player_name="A", gender="M",
        state_json="{}", flags_json="{}", turns=0,
    )
    deleted = await SessionRepo.delete_session("sess1", "uid2")
    assert deleted is False


# ---------------------------------------------------------------------------
# ConversationRepo tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_append_and_load_recent(tmp_data_dir):
    from backend.app.db.repos import ConversationRepo
    await ConversationRepo.append_turns("uid1", "sess1", "Hello", "Hi there!", turn=1)
    await ConversationRepo.append_turns("uid1", "sess1", "How are you?", "Fine.", turn=2)

    entries = await ConversationRepo.load_recent("uid1", "sess1", limit=10)
    assert len(entries) == 4  # 2 turns × 2 entries each
    roles = [e["role"] for e in entries]
    assert roles == ["user", "assistant", "user", "assistant"]


@pytest.mark.asyncio
async def test_load_page_before_turn(tmp_data_dir):
    from backend.app.db.repos import ConversationRepo
    for i in range(1, 6):
        await ConversationRepo.append_turns("uid1", "sess1", f"msg {i}", f"reply {i}", turn=i)

    # Load turns before turn 3
    entries = await ConversationRepo.load_page("uid1", "sess1", before_turn=3, limit=10)
    turns = set(e["turn"] for e in entries)
    assert 3 not in turns
    assert 4 not in turns
    assert 1 in turns or 2 in turns


@pytest.mark.asyncio
async def test_append_turns_rejects_path_traversal_session_id(tmp_data_dir):
    """A02 regression: a traversal-style session_id must not be able to
    resolve a JSONL path outside the caller's own session directory."""
    from backend.app.db.repos import ConversationRepo, SessionPathError

    with pytest.raises(SessionPathError):
        await ConversationRepo.append_turns(
            "uid1", "../../../evil", "hello", "hi", turn=1
        )

    # Nothing should have been written outside the intended sessions tree.
    escaped = tmp_data_dir / "evil.jsonl"
    assert not escaped.exists()


def test_jsonl_path_rejects_traversal_and_stays_contained(tmp_data_dir):
    """A02 regression: direct unit check on the repository-boundary guard."""
    from backend.app.db.repos import _jsonl_path, SessionPathError

    for bad_id in ["../evil", "..\\evil", "a/../../b", "/etc/passwd", "a/b", ""]:
        with pytest.raises(SessionPathError):
            _jsonl_path("uid1", bad_id)

    # A normal, generated-style id resolves inside the session directory.
    good = _jsonl_path("uid1", "abc123-DEF_456")
    expected_base = (tmp_data_dir / "users" / "uid1" / "sessions").resolve()
    assert good.parent == expected_base


@pytest.mark.asyncio
async def test_upsert_rejects_unsafe_session_id(tmp_data_dir):
    """A02 regression: unsafe session_ids must be rejected before ever being
    persisted, so they can never later be turned into a filesystem path."""
    from backend.app.db.repos import UserRepo, SessionRepo, SessionPathError

    await UserRepo.upsert_user("uid1", "a@b.com", "Alice", None)
    with pytest.raises(SessionPathError):
        await SessionRepo.create_or_update_session(
            session_id="../../etc/passwd", user_id="uid1", story_id="s1",
            story_title="T", player_name="A", gender="M",
            state_json="{}", flags_json="{}", turns=0,
        )


@pytest.mark.asyncio
async def test_load_recent_on_missing_file_returns_empty(tmp_data_dir):
    from backend.app.db.repos import ConversationRepo
    entries = await ConversationRepo.load_recent("uid1", "nonexistent_sess", limit=10)
    assert entries == []


# ---------------------------------------------------------------------------
# Guest session transfer tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transfer_sessions_moves_db_rows(tmp_data_dir):
    """Transferring sessions updates user_id in DB."""
    from backend.app.db.repos import SessionRepo
    guest_uid = "guest:aaa-bbb-ccc"
    real_uid = "google_user_123"

    await SessionRepo.create_or_update_session(
        session_id="gs1", user_id=guest_uid, story_id="s1",
        story_title="T", player_name="A", gender="M",
        state_json="{}", flags_json="{}", turns=3,
    )
    await SessionRepo.create_or_update_session(
        session_id="gs2", user_id=guest_uid, story_id="s2",
        story_title="T2", player_name="B", gender="F",
        state_json="{}", flags_json="{}", turns=1,
    )

    count = await SessionRepo.transfer_sessions(guest_uid, real_uid)
    assert count == 2

    # Old guest user_id should have nothing
    assert await SessionRepo.list_user_sessions(guest_uid) == []
    # New user should own both sessions
    sessions = await SessionRepo.list_user_sessions(real_uid)
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_transfer_sessions_moves_jsonl_files(tmp_data_dir):
    """Transferring sessions moves JSONL conversation log files."""
    from backend.app.db.repos import SessionRepo, ConversationRepo
    guest_uid = "guest:ddd-eee-fff"
    real_uid = "google_user_456"

    await SessionRepo.create_or_update_session(
        session_id="gs3", user_id=guest_uid, story_id="s1",
        story_title="T", player_name="A", gender="M",
        state_json="{}", flags_json="{}", turns=1,
    )
    await ConversationRepo.append_turns(guest_uid, "gs3", "Hello", "Hi", turn=1)

    # _safe_dir_name replaces ":" with "_" for filesystem safety (Windows)
    safe_guest = guest_uid.replace(":", "_")
    safe_real = real_uid
    old_path = tmp_data_dir / "users" / safe_guest / "sessions" / "gs3.jsonl"
    assert old_path.exists()

    await SessionRepo.transfer_sessions(guest_uid, real_uid)

    new_path = tmp_data_dir / "users" / safe_real / "sessions" / "gs3.jsonl"
    assert new_path.exists()
    assert not old_path.exists()


def test_session_get_bootstraps_missing_schema(tmp_path):
    """SessionRepo._get should auto-init schema when game_sessions table is missing."""
    db_path = tmp_path / "storieschat.db"
    # Create an empty DB file with no schema.
    sqlite3.connect(str(db_path)).close()

    import backend.app.db.database as db_module
    import backend.app.db.repos as repos_module

    with patch.object(db_module, "DB_PATH", db_path), \
         patch.object(db_module, "DATA_DIR", tmp_path), \
         patch.object(repos_module, "DATA_DIR", tmp_path):
        # First call should not raise even though table is initially missing.
        assert repos_module.SessionRepo._get("missing", "uid1") is None

        # Verify schema now exists by inserting a row and reading it back.
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            now = 1700000000
            conn.execute(
                "INSERT INTO users (id, email, name, avatar_url, created_at, last_login) VALUES (?, ?, ?, ?, ?, ?)",
                ("uid1", "u@example.com", "User", None, now, now),
            )
            conn.execute(
                "INSERT INTO game_sessions (id, user_id, story_id, story_title, player_name, gender, status, created_at, last_played, turns, last_message, state_json, flags_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("sess1", "uid1", "story", "Story", "Alex", "M", "active", now, now, 1, "hi", "{}", "{}"),
            )
            conn.commit()
        finally:
            conn.close()

        row = repos_module.SessionRepo._get("sess1", "uid1")
        assert row is not None
        assert row["id"] == "sess1"


@pytest.mark.asyncio
async def test_transfer_sessions_returns_zero_when_no_sessions(tmp_data_dir):
    from backend.app.db.repos import SessionRepo
    count = await SessionRepo.transfer_sessions("guest:nonexistent", "real_user")
    assert count == 0


# ---------------------------------------------------------------------------
# Guest session expiry/cleanup tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_expired_guest_sessions(tmp_data_dir):
    """Delete guest sessions older than cutoff timestamp."""
    import time as _time
    from backend.app.db.repos import SessionRepo

    now = int(_time.time())
    old_ts = now - 90000  # > 24 hours ago

    # Create an old guest session (manually set last_played)
    await SessionRepo.create_or_update_session(
        session_id="old_gs", user_id="guest:old-uuid", story_id="s1",
        story_title="T", player_name="A", gender="M",
        state_json="{}", flags_json="{}", turns=1,
    )
    # Manually backdate last_played
    from backend.app.db.repos import get_connection
    conn = get_connection()
    conn.execute("UPDATE game_sessions SET last_played = ? WHERE id = ?", (old_ts, "old_gs"))
    conn.commit()
    conn.close()

    # Create a recent guest session (should survive)
    await SessionRepo.create_or_update_session(
        session_id="new_gs", user_id="guest:new-uuid", story_id="s2",
        story_title="T2", player_name="B", gender="F",
        state_json="{}", flags_json="{}", turns=2,
    )

    # Create a non-guest session with old timestamp (should survive — not a guest)
    await SessionRepo.create_or_update_session(
        session_id="real_sess", user_id="real_user", story_id="s3",
        story_title="T3", player_name="C", gender="M",
        state_json="{}", flags_json="{}", turns=5,
    )
    conn = get_connection()
    conn.execute("UPDATE game_sessions SET last_played = ? WHERE id = ?", (old_ts, "real_sess"))
    conn.commit()
    conn.close()

    cutoff = now - 86400  # 24 hours ago
    deleted = await SessionRepo.delete_expired_guest_sessions(cutoff)
    assert deleted == 1  # Only the old guest session

    # Verify old guest is gone
    assert await SessionRepo.get_session("old_gs", "guest:old-uuid") is None
    # Recent guest still exists
    assert await SessionRepo.get_session("new_gs", "guest:new-uuid") is not None
    # Real user's old session still exists
    assert await SessionRepo.get_session("real_sess", "real_user") is not None


# ---------------------------------------------------------------------------
# BL-02: turn-retry idempotency dedup token (last_request_id/last_reply_json)
# ---------------------------------------------------------------------------

_OLD_SCHEMA_BEFORE_DEDUP_COLUMNS = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    avatar_url TEXT,
    created_at INTEGER NOT NULL,
    last_login INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS game_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    story_id TEXT NOT NULL,
    story_title TEXT,
    player_name TEXT,
    gender TEXT,
    status TEXT DEFAULT 'active',
    created_at INTEGER NOT NULL,
    last_played INTEGER NOT NULL,
    turns INTEGER DEFAULT 0,
    last_message TEXT,
    state_json TEXT,
    flags_json TEXT
);
"""


def test_init_db_adds_dedup_columns_to_existing_database(tmp_path):
    """init_db() must be safe to run against an existing on-disk DB that
    predates the last_request_id/last_reply_json columns (e.g. the Railway
    persistent volume before this change deploys) - additive ALTER, no
    destructive migration, no crash on repeat calls."""
    from backend.app.db import database as db_mod

    db_path = tmp_path / "storieschat.db"
    with patch("backend.app.db.database.DATA_DIR", tmp_path), \
         patch("backend.app.db.database.DB_PATH", db_path):
        # Simulate the pre-existing schema (no dedup columns) as it would
        # have existed on disk before this change.
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_OLD_SCHEMA_BEFORE_DEDUP_COLUMNS)
        conn.commit()
        conn.close()

        cols_before = {
            row[1] for row in sqlite3.connect(str(db_path)).execute(
                "PRAGMA table_info(game_sessions)"
            ).fetchall()
        }
        assert "last_request_id" not in cols_before

        # init_db() must add the columns without raising, and be idempotent.
        db_mod.init_db()
        db_mod.init_db()

        cols_after = {
            row[1] for row in sqlite3.connect(str(db_path)).execute(
                "PRAGMA table_info(game_sessions)"
            ).fetchall()
        }
        assert "last_request_id" in cols_after
        assert "last_reply_json" in cols_after


@pytest.mark.asyncio
async def test_get_last_request_returns_none_for_new_session(tmp_data_dir):
    from backend.app.db.repos import UserRepo, SessionRepo

    await UserRepo.upsert_user("uid_dedup", "d@b.com", "Dana", None)
    await SessionRepo.create_or_update_session(
        session_id="sess_dedup", user_id="uid_dedup", story_id="s1",
        story_title="T", player_name="Dana", gender="F",
        state_json="{}", flags_json="{}", turns=0,
    )
    req_id, reply_json = await SessionRepo.get_last_request("sess_dedup", "uid_dedup")
    assert req_id is None
    assert reply_json is None


@pytest.mark.asyncio
async def test_update_and_get_last_request_round_trips(tmp_data_dir):
    from backend.app.db.repos import UserRepo, SessionRepo

    await UserRepo.upsert_user("uid_dedup2", "d2@b.com", "Deja", None)
    await SessionRepo.create_or_update_session(
        session_id="sess_dedup2", user_id="uid_dedup2", story_id="s1",
        story_title="T", player_name="Deja", gender="F",
        state_json="{}", flags_json="{}", turns=1,
    )
    await SessionRepo.update_last_request("sess_dedup2", "uid_dedup2", "req-abc", '{"reply":"x"}')

    req_id, reply_json = await SessionRepo.get_last_request("sess_dedup2", "uid_dedup2")
    assert req_id == "req-abc"
    assert reply_json == '{"reply":"x"}'


@pytest.mark.asyncio
async def test_create_or_update_session_without_request_id_preserves_prior_dedup_token(tmp_data_dir):
    """The COALESCE in the upsert's ON CONFLICT clause must not clobber a
    previously stored dedup token when a later save (e.g. a different code
    path) doesn't pass one."""
    from backend.app.db.repos import UserRepo, SessionRepo

    await UserRepo.upsert_user("uid_dedup3", "d3@b.com", "Drew", None)
    await SessionRepo.create_or_update_session(
        session_id="sess_dedup3", user_id="uid_dedup3", story_id="s1",
        story_title="T", player_name="Drew", gender="M",
        state_json="{}", flags_json="{}", turns=1,
        last_request_id="req-xyz", last_reply_json='{"reply":"y"}',
    )
    # A subsequent save with no dedup fields (matches the main session-save
    # call site in prompt_engine.py, which passes them as None/omits them).
    await SessionRepo.create_or_update_session(
        session_id="sess_dedup3", user_id="uid_dedup3", story_id="s1",
        story_title="T", player_name="Drew", gender="M",
        state_json='{"turns":2}', flags_json="{}", turns=2,
    )
    req_id, reply_json = await SessionRepo.get_last_request("sess_dedup3", "uid_dedup3")
    assert req_id == "req-xyz"
    assert reply_json == '{"reply":"y"}'


# ---------------------------------------------------------------------------
# BL-01b: durable fact-extraction outbox (remainder of Six Strangers Phase 1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enqueue_creates_pending_row(tmp_data_dir):
    from backend.app.db.repos import FactExtractionOutboxRepo

    row_id = await FactExtractionOutboxRepo.enqueue(
        session_id="sess1", user_id="uid1", user_msg="hello",
        user_msg_id="umsg1", ai_reply="hi there", ai_msg_id="aimsg1",
        character_id="mizuki",
    )
    assert isinstance(row_id, int)

    pending = await FactExtractionOutboxRepo.fetch_pending()
    assert len(pending) == 1
    assert pending[0]["id"] == row_id
    assert pending[0]["status"] == "pending"
    assert pending[0]["session_id"] == "sess1"
    assert pending[0]["user_msg"] == "hello"
    assert pending[0]["ai_reply"] == "hi there"
    assert pending[0]["completed_at"] is None
    assert pending[0]["attempts"] == 0


@pytest.mark.asyncio
async def test_mark_done_removes_row_from_pending(tmp_data_dir):
    from backend.app.db.repos import FactExtractionOutboxRepo

    row_id = await FactExtractionOutboxRepo.enqueue(
        session_id="sess1", user_id="uid1", user_msg="hello",
        user_msg_id="umsg1", ai_reply="hi", ai_msg_id="aimsg1",
        character_id="mizuki",
    )
    await FactExtractionOutboxRepo.mark_done(row_id)

    pending = await FactExtractionOutboxRepo.fetch_pending()
    assert pending == []


@pytest.mark.asyncio
async def test_mark_failed_increments_attempts_and_stores_error(tmp_data_dir):
    from backend.app.db.repos import FactExtractionOutboxRepo, get_connection

    row_id = await FactExtractionOutboxRepo.enqueue(
        session_id="sess1", user_id="uid1", user_msg="hello",
        user_msg_id="umsg1", ai_reply="hi", ai_msg_id="aimsg1",
        character_id="mizuki",
    )
    await FactExtractionOutboxRepo.mark_failed(row_id, "boom: connection refused")

    conn = get_connection()
    row = conn.execute("SELECT * FROM fact_extraction_outbox WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row["status"] == "failed"
    assert row["attempts"] == 1
    assert "boom" in row["last_error"]
    # A failed row is not "pending" - it must not be picked up by the same
    # fetch_pending() the recovery sweep uses (failed rows are surfaced for
    # manual diagnosis via last_error, not silently auto-retried forever).
    pending = await FactExtractionOutboxRepo.fetch_pending()
    assert pending == []


@pytest.mark.asyncio
async def test_prune_done_older_than_removes_only_old_done_rows(tmp_data_dir):
    """Pruning must only remove 'done' rows older than the cutoff - never
    'pending' rows (still awaiting recovery) or 'failed' rows (kept for
    diagnosis)."""
    import time as _time
    from backend.app.db.repos import FactExtractionOutboxRepo, get_connection

    old_done_id = await FactExtractionOutboxRepo.enqueue(
        session_id="s1", user_id="u1", user_msg="a", user_msg_id="m1",
        ai_reply="b", ai_msg_id="a1", character_id="c1",
    )
    await FactExtractionOutboxRepo.mark_done(old_done_id)
    old_cutoff_ts = int(_time.time()) - 1000
    conn = get_connection()
    conn.execute(
        "UPDATE fact_extraction_outbox SET completed_at = ? WHERE id = ?",
        (old_cutoff_ts, old_done_id),
    )
    conn.commit()
    conn.close()

    recent_done_id = await FactExtractionOutboxRepo.enqueue(
        session_id="s1", user_id="u1", user_msg="c", user_msg_id="m2",
        ai_reply="d", ai_msg_id="a2", character_id="c1",
    )
    await FactExtractionOutboxRepo.mark_done(recent_done_id)

    still_pending_id = await FactExtractionOutboxRepo.enqueue(
        session_id="s1", user_id="u1", user_msg="e", user_msg_id="m3",
        ai_reply="f", ai_msg_id="a3", character_id="c1",
    )

    still_failed_id = await FactExtractionOutboxRepo.enqueue(
        session_id="s1", user_id="u1", user_msg="g", user_msg_id="m4",
        ai_reply="h", ai_msg_id="a4", character_id="c1",
    )
    await FactExtractionOutboxRepo.mark_failed(still_failed_id, "err")
    conn = get_connection()
    conn.execute(
        "UPDATE fact_extraction_outbox SET created_at = ? WHERE id IN (?, ?)",
        (int(_time.time()) - 2000, still_failed_id, still_failed_id),
    )
    conn.commit()
    conn.close()

    cutoff = int(_time.time()) - 500
    pruned = await FactExtractionOutboxRepo.prune_done_older_than(cutoff)
    assert pruned == 1

    conn = get_connection()
    remaining_ids = {r["id"] for r in conn.execute("SELECT id FROM fact_extraction_outbox").fetchall()}
    conn.close()
    assert old_done_id not in remaining_ids
    assert recent_done_id in remaining_ids
    assert still_pending_id in remaining_ids
    assert still_failed_id in remaining_ids
