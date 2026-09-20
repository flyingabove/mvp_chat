"""Repository classes for users, game sessions, and conversation logs."""
import json
import re
import time
import asyncio
import sqlite3
from pathlib import Path
from backend.app.db.database import get_connection, DATA_DIR, init_db


class SessionPathError(ValueError):
    """Raised when a session_id is not safe to use in a filesystem path
    (A02: path traversal via session IDs)."""


# Session IDs are always server-generated (uuid4 hex or similar). Reject
# anything outside a conservative safe charset before it ever reaches a
# filesystem path — this blocks "../", absolute paths, null bytes, etc.
_SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def validate_session_id(session_id: str) -> str:
    """Request-boundary + repository-boundary guard for session_id values
    that get turned into filesystem paths. Raises SessionPathError if the
    id contains anything other than alphanumerics/hyphen/underscore."""
    if not isinstance(session_id, str) or not _SAFE_SESSION_ID_RE.match(session_id):
        raise SessionPathError(f"unsafe session_id: {session_id!r}")
    return session_id


# ---------------------------------------------------------------------------
# UserRepo
# ---------------------------------------------------------------------------
class UserRepo:
    @staticmethod
    def _upsert(user_id: str, email: str, name: str, avatar_url: str | None) -> None:
        now = int(time.time())
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO users (id, email, name, avatar_url, created_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    email      = excluded.email,
                    name       = excluded.name,
                    avatar_url = excluded.avatar_url,
                    last_login = excluded.last_login
                """,
                (user_id, email, name, avatar_url, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _get(user_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    async def upsert_user(cls, user_id: str, email: str, name: str, avatar_url: str | None = None) -> None:
        await asyncio.to_thread(cls._upsert, user_id, email, name, avatar_url)

    @classmethod
    async def get_user(cls, user_id: str) -> dict | None:
        return await asyncio.to_thread(cls._get, user_id)


# ---------------------------------------------------------------------------
# SessionRepo
# ---------------------------------------------------------------------------
class SessionOwnershipError(Exception):
    """Raised when a caller attempts to upsert a session_id that already
    belongs to a different owner. Callers must never silently overwrite
    another owner's row (A01)."""


class SessionRepo:
    @staticmethod
    def _upsert(
        session_id: str, user_id: str, story_id: str, story_title: str,
        player_name: str, gender: str, state_json: str, flags_json: str,
        last_message: str = "", turns: int = 0,
        last_request_id: str | None = None, last_reply_json: str | None = None,
    ) -> None:
        # A02 fix: reject unsafe session_ids before they can ever be stored
        # and later turned into a filesystem path elsewhere in this class.
        validate_session_id(session_id)
        now = int(time.time())
        conn = get_connection()
        try:
            # A01 fix: ON CONFLICT(id) DO UPDATE previously had no owner
            # condition, so a caller who knew/guessed another owner's
            # session_id could overwrite that owner's state_json/flags_json
            # in place (the user_id column itself was left unchanged, which
            # made the corruption easy to miss). Check current ownership
            # first and refuse the write outright on a mismatch instead of
            # silently clobbering the existing owner's row.
            existing = conn.execute(
                "SELECT user_id FROM game_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if existing is not None and existing["user_id"] != user_id:
                raise SessionOwnershipError(
                    f"session {session_id!r} is owned by a different user; refusing upsert"
                )

            conn.execute(
                """
                INSERT INTO game_sessions
                    (id, user_id, story_id, story_title, player_name, gender,
                     status, created_at, last_played, turns, last_message, state_json, flags_json,
                     last_request_id, last_reply_json)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    story_title      = excluded.story_title,
                    player_name      = excluded.player_name,
                    gender           = excluded.gender,
                    last_played      = excluded.last_played,
                    turns            = excluded.turns,
                    last_message     = excluded.last_message,
                    state_json       = excluded.state_json,
                    flags_json       = excluded.flags_json,
                    last_request_id  = COALESCE(excluded.last_request_id, game_sessions.last_request_id),
                    last_reply_json  = COALESCE(excluded.last_reply_json, game_sessions.last_reply_json)
                WHERE game_sessions.user_id = excluded.user_id
                """,
                (session_id, user_id, story_id, story_title, player_name, gender,
                 now, now, turns, last_message[:120], state_json, flags_json,
                 last_request_id, last_reply_json),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _get_last_request(session_id: str, user_id: str) -> tuple[str | None, str | None]:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT last_request_id, last_reply_json FROM game_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
            if row is None:
                return None, None
            return row["last_request_id"], row["last_reply_json"]
        finally:
            conn.close()

    @staticmethod
    def _update_last_request(session_id: str, user_id: str, request_id: str, reply_json: str) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE game_sessions SET last_request_id = ?, last_reply_json = ? WHERE id = ? AND user_id = ?",
                (request_id, reply_json, session_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _get(session_id: str, user_id: str) -> dict | None:
        def _query_once() -> dict | None:
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM game_sessions WHERE id = ? AND user_id = ?",
                    (session_id, user_id),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        try:
            return _query_once()
        except sqlite3.OperationalError as exc:
            # If DB file exists without schema yet, bootstrap then retry once.
            if "no such table" in str(exc).lower() and "game_sessions" in str(exc).lower():
                init_db()
                return _query_once()
            raise

    @staticmethod
    def _list(user_id: str, limit: int = 50) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM game_sessions WHERE user_id = ? ORDER BY last_played DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _delete(session_id: str, user_id: str) -> bool:
        conn = get_connection()
        try:
            cur = conn.execute(
                "DELETE FROM game_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            )
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()

        if deleted:
            # Remove JSONL file (routed through _jsonl_path for the same
            # traversal-containment guard used on every other write/read).
            try:
                jsonl_path = _jsonl_path(user_id, session_id)
                jsonl_path.unlink(missing_ok=True)
            except Exception:
                pass

        return deleted

    @classmethod
    async def create_or_update_session(
        cls, session_id: str, user_id: str, story_id: str, story_title: str,
        player_name: str, gender: str, state_json: str, flags_json: str,
        last_message: str = "", turns: int = 0,
        last_request_id: str | None = None, last_reply_json: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            cls._upsert, session_id, user_id, story_id, story_title,
            player_name, gender, state_json, flags_json, last_message, turns,
            last_request_id, last_reply_json,
        )

    @classmethod
    async def get_last_request(cls, session_id: str, user_id: str) -> tuple[str | None, str | None]:
        """BL-02: fetch the dedup token + replayed reply from the most
        recently completed turn for this session, without loading the full
        state_json blob."""
        return await asyncio.to_thread(cls._get_last_request, session_id, user_id)

    @classmethod
    async def update_last_request(cls, session_id: str, user_id: str, request_id: str, reply_json: str) -> None:
        """BL-02: record the dedup token for the turn that was just
        completed, after `result` (the client-facing reply) is fully built.
        Kept as a separate lightweight UPDATE (rather than folding into the
        main create_or_update_session save) so the existing atomic-turn-save
        ordering discipline at that call site is untouched."""
        await asyncio.to_thread(cls._update_last_request, session_id, user_id, request_id, reply_json)

    @classmethod
    async def get_session(cls, session_id: str, user_id: str) -> dict | None:
        return await asyncio.to_thread(cls._get, session_id, user_id)

    @classmethod
    async def list_user_sessions(cls, user_id: str, limit: int = 50) -> list[dict]:
        return await asyncio.to_thread(cls._list, user_id, limit)

    @classmethod
    async def delete_session(cls, session_id: str, user_id: str) -> bool:
        return await asyncio.to_thread(cls._delete, session_id, user_id)

    @staticmethod
    def _transfer(from_user_id: str, to_user_id: str) -> int:
        """Transfer all sessions from one user_id to another. Returns count."""
        conn = get_connection()
        try:
            cur = conn.execute(
                "UPDATE game_sessions SET user_id = ? WHERE user_id = ?",
                (to_user_id, from_user_id),
            )
            conn.commit()
            count = cur.rowcount
        finally:
            conn.close()

        # Move JSONL files from old user dir to new user dir
        if count > 0:
            src_dir = DATA_DIR / "users" / _safe_dir_name(from_user_id) / "sessions"
            dst_dir = DATA_DIR / "users" / _safe_dir_name(to_user_id) / "sessions"
            if src_dir.exists():
                dst_dir.mkdir(parents=True, exist_ok=True)
                for f in src_dir.iterdir():
                    try:
                        f.rename(dst_dir / f.name)
                    except Exception:
                        pass
                # Clean up empty source directory
                try:
                    src_dir.rmdir()
                    src_dir.parent.rmdir()
                except Exception:
                    pass

        return count

    @staticmethod
    def _delete_expired_guests(cutoff_ts: int) -> int:
        """Delete all guest sessions older than cutoff_ts (Unix seconds).
        Returns number of sessions deleted."""
        conn = get_connection()
        try:
            # Find sessions to delete (need IDs for JSONL cleanup)
            rows = conn.execute(
                "SELECT id, user_id FROM game_sessions "
                "WHERE user_id LIKE 'guest:%' AND last_played < ?",
                (cutoff_ts,),
            ).fetchall()

            if not rows:
                return 0

            ids = [r["id"] for r in rows]
            user_ids = {r["user_id"] for r in rows}

            # Delete from DB
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM game_sessions WHERE id IN ({placeholders})",
                ids,
            )
            conn.commit()
        finally:
            conn.close()

        # Clean up JSONL files (routed through _jsonl_path for the same
        # traversal-containment guard used on every other write/read).
        for row in rows:
            try:
                jsonl_path = _jsonl_path(row["user_id"], row["id"])
                jsonl_path.unlink(missing_ok=True)
            except Exception:
                pass

        # Clean up empty guest user directories
        for uid in user_ids:
            sessions_dir = DATA_DIR / "users" / _safe_dir_name(uid) / "sessions"
            try:
                if sessions_dir.exists() and not any(sessions_dir.iterdir()):
                    sessions_dir.rmdir()
                    sessions_dir.parent.rmdir()
            except Exception:
                pass

        return len(ids)

    @classmethod
    async def transfer_sessions(cls, from_user_id: str, to_user_id: str) -> int:
        return await asyncio.to_thread(cls._transfer, from_user_id, to_user_id)

    @classmethod
    async def delete_expired_guest_sessions(cls, cutoff_ts: int) -> int:
        return await asyncio.to_thread(cls._delete_expired_guests, cutoff_ts)


# ---------------------------------------------------------------------------
# ConversationRepo  (JSONL-based raw logs)
# ---------------------------------------------------------------------------
def _safe_dir_name(user_id: str) -> str:
    """Sanitize user_id for use as a directory name (Windows forbids ':')."""
    return user_id.replace(":", "_")


def _jsonl_path(user_id: str, session_id: str) -> Path:
    # A02 fix: validate at the repository boundary (charset) AND resolve the
    # final path to assert it is still contained within the caller's own
    # session directory before any file I/O touches it.
    validate_session_id(session_id)
    base_dir = (DATA_DIR / "users" / _safe_dir_name(user_id) / "sessions").resolve()
    candidate = (base_dir / f"{session_id}.jsonl").resolve()
    if candidate.parent != base_dir:
        raise SessionPathError(
            f"session_id path escaped the session directory: {session_id!r}"
        )
    return candidate


class FactExtractionOutboxRepo:
    """BL-01b: durable queue for background dialogue fact-extraction.

    `_extract_and_store` (backend/app/api/prompt_engine.py) used to fire via
    a bare `asyncio.ensure_future(...)`, fully unawaited, with no record it
    had even been attempted. A crash between the turn's session save and that
    background task completing silently dropped the turn's extracted facts
    forever. This repo gives each extraction attempt a durable row: enqueued
    (status='pending') before the in-process task starts, marked done/failed
    after — so a startup recovery sweep (backend/app/main.py) can find and
    reprocess anything left pending from a prior crash."""

    @staticmethod
    def _enqueue(
        session_id: str, user_id: str, user_msg: str, user_msg_id: str,
        ai_reply: str, ai_msg_id: str, character_id: str,
    ) -> int:
        now = int(time.time())
        conn = get_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO fact_extraction_outbox
                    (session_id, user_id, user_msg, user_msg_id, ai_reply, ai_msg_id,
                     character_id, status, created_at, attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, 0)
                """,
                (session_id, user_id, user_msg, user_msg_id, ai_reply, ai_msg_id, character_id, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    @staticmethod
    def _mark_done(row_id: int) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE fact_extraction_outbox SET status = 'done', completed_at = ? WHERE id = ?",
                (int(time.time()), row_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _mark_failed(row_id: int, error: str) -> None:
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE fact_extraction_outbox
                   SET status = 'failed', attempts = attempts + 1, last_error = ?
                   WHERE id = ?""",
                (error[:500], row_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _fetch_pending(limit: int = 200) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM fact_extraction_outbox WHERE status = 'pending' "
                "ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _prune_done_older_than(cutoff_ts: int) -> int:
        """Delete 'done' rows completed before cutoff_ts. 'failed' rows are
        kept indefinitely for diagnosis (low volume, one row per failed
        extraction) - only successfully completed rows accumulate unbounded
        over a long-running deploy."""
        conn = get_connection()
        try:
            cur = conn.execute(
                "DELETE FROM fact_extraction_outbox WHERE status = 'done' AND completed_at < ?",
                (cutoff_ts,),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    @classmethod
    async def enqueue(
        cls, session_id: str, user_id: str, user_msg: str, user_msg_id: str,
        ai_reply: str, ai_msg_id: str, character_id: str,
    ) -> int:
        return await asyncio.to_thread(
            cls._enqueue, session_id, user_id, user_msg, user_msg_id, ai_reply, ai_msg_id, character_id,
        )

    @classmethod
    async def mark_done(cls, row_id: int) -> None:
        await asyncio.to_thread(cls._mark_done, row_id)

    @classmethod
    async def mark_failed(cls, row_id: int, error: str) -> None:
        await asyncio.to_thread(cls._mark_failed, row_id, error)

    @classmethod
    async def fetch_pending(cls, limit: int = 200) -> list[dict]:
        return await asyncio.to_thread(cls._fetch_pending, limit)

    @classmethod
    async def prune_done_older_than(cls, cutoff_ts: int) -> int:
        return await asyncio.to_thread(cls._prune_done_older_than, cutoff_ts)


class ConversationRepo:
    @staticmethod
    def _append(
        user_id: str, session_id: str, user_msg: str, assistant_reply: str, turn: int,
        user_msg_id: str = "", ai_msg_id: str = "",
    ) -> None:
        path = _jsonl_path(user_id, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        with path.open("a", encoding="utf-8") as f:
            user_entry: dict = {"turn": turn, "role": "user", "content": user_msg, "ts": ts}
            if user_msg_id:
                user_entry["msg_id"] = user_msg_id
            f.write(json.dumps(user_entry) + "\n")
            ai_entry: dict = {"turn": turn, "role": "assistant", "content": assistant_reply, "ts": ts}
            if ai_msg_id:
                ai_entry["msg_id"] = ai_msg_id
            f.write(json.dumps(ai_entry) + "\n")

    @staticmethod
    def _load_recent(user_id: str, session_id: str, limit: int = 20) -> list[dict]:
        path = _jsonl_path(user_id, session_id)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        # Each turn writes 2 lines (user + assistant). Take last limit*2 lines then parse.
        recent_lines = lines[-(limit * 2):]
        result = []
        for line in recent_lines:
            try:
                result.append(json.loads(line))
            except Exception:
                pass
        return result

    @staticmethod
    def _load_page(user_id: str, session_id: str, before_turn: int, limit: int = 20) -> list[dict]:
        path = _jsonl_path(user_id, session_id)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        all_entries = []
        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("turn", 0) < before_turn:
                    all_entries.append(entry)
            except Exception:
                pass
        # Return last `limit*2` entries before the cutoff
        return all_entries[-(limit * 2):]

    @classmethod
    async def append_turns(
        cls, user_id: str, session_id: str, user_msg: str, assistant_reply: str, turn: int,
        user_msg_id: str = "", ai_msg_id: str = "",
    ) -> None:
        await asyncio.to_thread(
            cls._append, user_id, session_id, user_msg, assistant_reply, turn,
            user_msg_id, ai_msg_id,
        )

    @classmethod
    async def load_recent(cls, user_id: str, session_id: str, limit: int = 20) -> list[dict]:
        return await asyncio.to_thread(cls._load_recent, user_id, session_id, limit)

    @classmethod
    async def load_page(cls, user_id: str, session_id: str, before_turn: int, limit: int = 20) -> list[dict]:
        return await asyncio.to_thread(cls._load_page, user_id, session_id, before_turn, limit)
