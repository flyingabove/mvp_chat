# backend/app/api/debug_inspect.py
"""Operator debug inspection: a probe and a read-only session inspector.

- GET /api/debug/ping: public, never raises, no secrets. Tells an agent in one call whether operator tools are
  enabled on this host and whether the token it sent is accepted, so it knows which debug surface it can use.
- GET /api/debug/session/{session_id}: operator only. The live (or persisted) game state and full world model.
  Read-only: it never creates, restores into the cache, or mutates a session.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.auth.dependencies import (
    _debug_tools_enabled, _operator_token_configured, is_operator_request, require_operator,
)

router = APIRouter()


@router.get("/debug/ping")
async def debug_ping(request: Request):
    return {
        "debug_tools_enabled": _debug_tools_enabled(),
        "operator_configured": bool(_operator_token_configured()),
        "operator_token_ok": is_operator_request(request),
    }


@router.get("/debug/session/{session_id}", dependencies=[Depends(require_operator)])
async def debug_session(session_id: str, user_id: str = "anon"):
    """`user_id` is `guest:<uuid>` for guests; it is only needed when the session is not in the memory cache."""
    from backend.app.api import prompt_engine as pe

    sess = pe.SESSIONS.get(session_id)
    source = "memory"
    if sess is None:
        sess = pe._try_load_session_from_db(session_id, user_id)
        source = "database"
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found (pass ?user_id= for a persisted session)")
    state = sess["state"]
    snapshot = json.loads(pe._serialize_state(state, []))
    snapshot.pop("log", None)
    return {
        "session_id": session_id,
        "source": source,
        "owner": sess.get("user_id"),
        "revision": sess.get("_db_revision"),
        "flags": {k: bool(sess.get(k)) for k in ("debug_mode", "chinese_mode", "epistemic_state", "truth_mode")},
        "log_entries": len(sess.get("log") or []),
        "state": snapshot,
    }
