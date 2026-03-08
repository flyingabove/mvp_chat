"""Repository classes for users, game sessions, and conversation logs."""
import json
import time
import asyncio
from pathlib import Path
from backend.app.db.database import get_connection, DATA_DIR


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
class SessionRepo:
    @staticmethod
    def _upsert(
        session_id: str, user_id: str, story_id: str, story_title: str,
        player_name: str, gender: str, state_json: str, flags_json: str,
        last_message: str = "", turns: int = 0,
    ) -> None:
        now = int(time.time())
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO game_sessions
                    (id, user_id, story_id, story_title, player_name, gender,
                     status, created_at, last_played, turns, last_message, state_json, flags_json)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    story_title  = excluded.story_title,
                    player_name  = excluded.player_name,
                    gender       = excluded.gender,
                    last_played  = excluded.last_played,
                    turns        = excluded.turns,
                    last_message = excluded.last_message,
                    state_json   = excluded.state_json,
                    flags_json   = excluded.flags_json
                """,
                (session_id, user_id, story_id, story_title, player_name, gender,
                 now, now, turns, last_message[:120], state_json, flags_json),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _get(session_id: str, user_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM game_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

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
            # Remove JSONL file
            jsonl_path = DATA_DIR / "users" / user_id / "sessions" / f"{session_id}.jsonl"
            try:
                jsonl_path.unlink(missing_ok=True)
            except Exception:
                pass

        return deleted

    @classmethod
    async def create_or_update_session(
        cls, session_id: str, user_id: str, story_id: str, story_title: str,
        player_name: str, gender: str, state_json: str, flags_json: str,
        last_message: str = "", turns: int = 0,
    ) -> None:
        await asyncio.to_thread(
            cls._upsert, session_id, user_id, story_id, story_title,
            player_name, gender, state_json, flags_json, last_message, turns,
        )

    @classmethod
    async def get_session(cls, session_id: str, user_id: str) -> dict | None:
        return await asyncio.to_thread(cls._get, session_id, user_id)

    @classmethod
    async def list_user_sessions(cls, user_id: str, limit: int = 50) -> list[dict]:
        return await asyncio.to_thread(cls._list, user_id, limit)

    @classmethod
    async def delete_session(cls, session_id: str, user_id: str) -> bool:
        return await asyncio.to_thread(cls._delete, session_id, user_id)


# ---------------------------------------------------------------------------
# ConversationRepo  (JSONL-based raw logs)
# ---------------------------------------------------------------------------
def _jsonl_path(user_id: str, session_id: str) -> Path:
    return DATA_DIR / "users" / user_id / "sessions" / f"{session_id}.jsonl"


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
