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
    last_error   TEXT,
    lease_until  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_outbox_status ON fact_extraction_outbox(status, created_at);

-- Phase 1.2: durable extraction OUTPUT, not just the input the old outbox
-- table recorded. Previously `mark_done` was written after the extracted
-- chunks were only stored in the in-memory SessionChunkStore, which itself
-- is only persisted into game_sessions.state_json on a LATER turn's save
-- (the save for THIS turn happens before the background extraction task
-- even starts) - so a crash between mark_done and the next save silently
-- lost the facts despite the outbox correctly saying "done". This table
-- makes the extraction's actual output durable in the same write as the
-- outbox row being marked done (single connection, single transaction —
-- see FactExtractionOutboxRepo.mark_done_with_chunks).
--
-- Keyed by (session_id, source_msg_id, extractor_version) rather than just
-- source_msg_id: an extractor prompt/schema change bumps extractor_version,
-- so old and new extractions of the same message coexist instead of the new
-- one silently overwriting a differently-shaped old one.
CREATE TABLE IF NOT EXISTS extracted_chunks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL,
    user_id           TEXT NOT NULL,
    source_msg_id     TEXT NOT NULL,
    extractor_version INTEGER NOT NULL,
    chunk_id          TEXT NOT NULL,
    chunk_json        TEXT NOT NULL,
    created_at        INTEGER NOT NULL,
    UNIQUE(session_id, chunk_id, extractor_version)
);

CREATE INDEX IF NOT EXISTS idx_extracted_chunks_session
    ON extracted_chunks(session_id, source_msg_id, extractor_version);
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
    # Phase 1.2: lease for reclaiming a HUNG (not crashed) extraction task —
    # the existing table predates this column on any already-deployed DB.
    _ensure_column(conn, "fact_extraction_outbox", "lease_until", "INTEGER")
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
