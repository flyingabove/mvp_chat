"""Unit tests for SQLite repos using an in-memory DB."""
import json
import sqlite3
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------

_SCHEMA = """
PRAGMA journal_mode=WAL;

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

CREATE INDEX IF NOT EXISTS idx_sessions_user ON game_sessions(user_id, last_played DESC);
"""


@pytest.fixture()
def tmp_data_dir(tmp_path):
    """Patch DATA_DIR and DB_PATH to use a temp directory."""
    db_path = tmp_path / "storieschat.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

    with patch("backend.app.db.database.DATA_DIR", tmp_path), \
         patch("backend.app.db.database.DB_PATH", db_path), \
         patch("backend.app.db.repos.DATA_DIR", tmp_path):
        # Also patch get_connection to use our db_path
        orig_get_conn = None
        import backend.app.db.database as _db
        orig_get_conn = _db.get_connection

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
async def test_load_recent_on_missing_file_returns_empty(tmp_data_dir):
    from backend.app.db.repos import ConversationRepo
    entries = await ConversationRepo.load_recent("uid1", "nonexistent_sess", limit=10)
    assert entries == []
