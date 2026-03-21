"""Per-user game session and conversation history endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from backend.app.auth.dependencies import get_current_user
from backend.app.db.repos import SessionRepo, ConversationRepo

router = APIRouter()


@router.get("/api/user/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    """List all game sessions for the authenticated user (newest first)."""
    user_id = user["sub"]
    sessions = await SessionRepo.list_user_sessions(user_id=user_id, limit=50)
    # Expose session_id alongside id for frontend consistency
    for s in sessions:
        if "id" in s and "session_id" not in s:
            s["session_id"] = s["id"]
    return {"sessions": sessions}


@router.get("/api/user/sessions/{session_id}/history")
async def get_history(
    session_id: str,
    before_turn: int = 9999,
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """
    Return paginated conversation history from the JSONL log.
    - Default: last 20 turns (before_turn=9999 means 'most recent')
    - For 'Load earlier messages': pass before_turn=N to get turns before turn N
    Returns: {"entries": [...], "has_more": bool, "oldest_turn": int}
    """
    user_id = user["sub"]

    # Validate session ownership
    sess = await SessionRepo.get_session(session_id=session_id, user_id=user_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    entries = await ConversationRepo.load_page(
        user_id=user_id,
        session_id=session_id,
        before_turn=before_turn,
        limit=limit,
    )

    oldest_turn = entries[0]["turn"] if entries else 0
    return {
        "entries": entries,
        "has_more": oldest_turn > 1,
        "oldest_turn": oldest_turn,
    }


@router.delete("/api/user/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    """Delete a session and its conversation log."""
    user_id = user["sub"]
    deleted = await SessionRepo.delete_session(session_id=session_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}
