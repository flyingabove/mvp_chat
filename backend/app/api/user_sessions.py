"""Per-user game session and conversation history endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from backend.app.auth.dependencies import get_current_user_or_guest
from backend.app.db.repos import SessionRepo, ConversationRepo
from backend.app.api.prompt_engine import get_session

router = APIRouter()


@router.get("/api/user/sessions")
async def list_sessions(user: dict = Depends(get_current_user_or_guest)):
    """List all game sessions for the authenticated or guest user (newest first)."""
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
    user: dict = Depends(get_current_user_or_guest),
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


@router.get("/api/user/sessions/{session_id}/journal")
async def get_journal(session_id: str, user: dict = Depends(get_current_user_or_guest)):
    """
    Player-facing recap: NPC goal/disposition shifts over the playthrough,
    derived entirely from existing engine state (EvolvingTrait history on
    Character.goal / RelationshipEdge.disposition, plus relationship
    narrative_log). No new extraction signal — this is a read-only view
    over data Phase 3 already tracks.
    """
    user_id = user["sub"]

    # Validate session ownership the same way /history does.
    sess = await SessionRepo.get_session(session_id=session_id, user_id=user_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    loaded = get_session(session_id, user_id=user_id)
    state = loaded["state"]
    characters = getattr(state, "characters", {}) or {}
    graph = getattr(state, "character_graph", None)

    entries = []

    for key, ch in characters.items():
        goal = getattr(ch, "goal", None)
        if goal is None:
            continue
        for chunk in goal.history:
            entries.append({
                "minute": chunk.timestamp_minute or 0,
                "kind": "goal",
                "character_id": key,
                "character_name": ch.name,
                "target_id": "",
                "target_name": "",
                "text": chunk.text,
            })

    if graph is not None:
        for edge in graph.edges.values():
            disposition = getattr(edge, "disposition", None)
            if disposition is None:
                continue
            from_ch = characters.get(edge.from_id)
            to_ch = characters.get(edge.to_id)
            from_name = from_ch.name if from_ch else edge.from_id
            to_name = to_ch.name if to_ch else edge.to_id
            for chunk in disposition.history:
                entries.append({
                    "minute": chunk.timestamp_minute or 0,
                    "kind": "disposition",
                    "character_id": edge.from_id,
                    "character_name": from_name,
                    "target_id": edge.to_id,
                    "target_name": to_name,
                    "text": chunk.text,
                })
            for note in edge.narrative_log:
                entries.append({
                    "minute": 0,
                    "kind": "note",
                    "character_id": edge.from_id,
                    "character_name": from_name,
                    "target_id": edge.to_id,
                    "target_name": to_name,
                    "text": note,
                })

    entries.sort(key=lambda e: e["minute"])

    return {"entries": entries}


@router.delete("/api/user/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user_or_guest)):
    """Delete a session and its conversation log."""
    user_id = user["sub"]
    deleted = await SessionRepo.delete_session(session_id=session_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}
