"""SQLite database initialization and connection helpers."""
import sqlite3
import asyncio
from pathlib import Path

# Railway provides /data as a persistent volume; fall back to ./data for local dev.
DATA_DIR = Path("/data") if Path("/data").exists() else Path("./data")
DB_PATH = DATA_DIR / "storieschat.db"

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    avatar_url  TEXT,
    created_at  INTEGER NOT NULL,
    last_login  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS game_sessions (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id),
    story_id     TEXT NOT NULL,
    story_title  TEXT,
    player_name  TEXT,
    gender       TEXT,
    status       TEXT DEFAULT 'active',
    created_at   INTEGER NOT NULL,
    last_played  INTEGER NOT NULL,
    turns        INTEGER DEFAULT 0,
    last_message TEXT,
    state_json   TEXT,
    flags_json   TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON game_sessions(user_id, last_played DESC);

CREATE TABLE IF NOT EXISTS fact_extraction_outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    user_msg     TEXT NOT NULL,
    user_msg_id  TEXT NOT NULL,
    ai_reply     TEXT NOT NULL,
    ai_msg_id    TEXT NOT NULL,
    character_id TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   INTEGER NOT NULL,
    completed_at INTEGER,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbox_status ON fact_extraction_outbox(status, created_at);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """Add `column` to `table` if it doesn't already exist. SQLite has no
    `ADD COLUMN IF NOT EXISTS`, so guard manually via PRAGMA table_info —
    this keeps schema changes additive/backward-compatible against an
    existing on-disk DB (e.g. Railway's persistent volume) with no
    migration framework and no destructive ALTER."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db() -> None:
    """Create tables if they don't exist. Called once at startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA)
    # BL-02: per-session turn-retry dedup token + replayed reply (see
    # SessionRepo.get_last_request/update_last_request in repos.py).
    _ensure_column(conn, "game_sessions", "last_request_id", "TEXT")
    _ensure_column(conn, "game_sessions", "last_reply_json", "TEXT")
    conn.commit()
    conn.close()


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection. Caller is responsible for closing."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


async def run_sync(fn, *args):
    """Run a synchronous SQLite function in a thread pool."""
    return await asyncio.to_thread(fn, *args)
