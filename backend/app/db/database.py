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
"""


def init_db() -> None:
    """Create tables if they don't exist. Called once at startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA)
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
