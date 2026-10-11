"""Operator-only routes for the Drama Theatre (BL-86, P-13): an autonomous season the admin watches, chats into and skips.

Mounted under `/beta/debug/theatre`, behind the same operator token as the rest of the debug surface; players never see
it. The page (`frontend/drama.html`, served at `/beta/drama`) drives it: `start` a session, then `step` for the next scene
(auto-play is just the page calling `step` in a loop, so closing the tab stops the spending), `say` for a typed line (a skip
command or a nudge) and `GET /{id}` to poll. Sessions live in memory (at most `MAX_SESSIONS`, oldest dropped); every beat is
also appended to a JSONL file so `sessions` and `replay` can show a finished or lost session later.

The writer is the real LLM writer on the one provider switch. A run that would resolve to OpenAI (which costs money) is
refused. Tests replace `WRITER_FACTORY` with the scripted `FakeWriter`.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.auth.dependencies import require_operator
from backend.app.sim import theatre as theatre_module
from backend.app.sim.theatre import NothingHappens, Theatre, TheatreCapReached, start_theatre

router = APIRouter(dependencies=[Depends(require_operator)])

MAX_SESSIONS = 4
MAX_CALL_CAP = 600
DEFAULT_STORY = "six_strangers"


@dataclass
class Session:
    theatre: Theatre
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created: float = field(default_factory=time.time)


SESSIONS: dict[str, Session] = {}


def _real_writer_factory(loop: asyncio.AbstractEventLoop) -> Callable[[Any, int], Any]:
    from backend.app.sim.llm_writer import LLMWriter, bridge_chat
    return lambda setup, cap: LLMWriter(bridge_chat(loop), setup, cap, tone=theatre_module.TONE)


# Tests set this to `lambda loop: lambda setup, cap: FakeWriter()`.
WRITER_FACTORY: Callable[[asyncio.AbstractEventLoop], Callable[[Any, int], Any]] = _real_writer_factory


def _provider() -> str:
    from backend.app.llm.chat import resolve_chat_config
    return resolve_chat_config(None, None).provider


class StartBody(BaseModel):
    story: str = DEFAULT_STORY
    seed: str = ""
    call_cap: int = theatre_module.DEFAULT_CALL_CAP


class SayBody(BaseModel):
    text: str
    then_step: bool = False


def _get(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="no such session (it may have been dropped: start a new one or replay it)")
    return session


@router.post("/start")
async def start(body: StartBody) -> dict[str, Any]:
    if WRITER_FACTORY is _real_writer_factory and _provider() == "openai":
        raise HTTPException(status_code=409, detail="refusing: the writer would run on OpenAI, which costs money; "
                                                    "set a Gemini key or LLM_PROVIDER=gemini")
    session_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    seed = body.seed.strip() or session_id
    cap = max(2, min(int(body.call_cap), MAX_CALL_CAP))
    try:
        theatre = await asyncio.to_thread(start_theatre, body.story, seed, WRITER_FACTORY(asyncio.get_running_loop()),
                                          session_id=session_id, call_cap=cap, log_dir=theatre_module.LOG_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    while len(SESSIONS) >= MAX_SESSIONS:
        SESSIONS.pop(next(iter(SESSIONS)))
    SESSIONS[session_id] = Session(theatre)
    return theatre.state()


@router.get("/sessions")
async def sessions() -> dict[str, Any]:
    saved = []
    if theatre_module.LOG_DIR.exists():
        for path in sorted(theatre_module.LOG_DIR.glob("*.jsonl"), reverse=True)[:30]:
            rows = _read_log(path)
            scenes = sum(1 for r in rows if r.get("type") == "scene")
            saved.append({"id": path.stem, "scenes": scenes, "beats": len(rows), "clock": rows[-1].get("clock", "") if rows else "",
                          "live": path.stem in SESSIONS})
    return {"live": [{"id": sid, "clock": s.theatre.clock()} for sid, s in SESSIONS.items()], "saved": saved}


def _read_log(path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


@router.get("/replay/{session_id}")
async def replay(session_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[\w-]{1,64}", session_id):
        raise HTTPException(status_code=400, detail="bad session id")
    path = theatre_module.LOG_DIR / f"{session_id}.jsonl"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no saved session with that id")
    return {"id": session_id, "beats": _read_log(path)}


@router.get("/{session_id}")
async def state(session_id: str, since: int = 0) -> dict[str, Any]:
    return _get(session_id).theatre.state(since)


async def _run(session: Session, work: Callable[[], Any]) -> None:
    """Run synchronous theatre work on a worker thread, one job at a time, turning failures into plain answers."""
    if session.lock.locked():
        raise HTTPException(status_code=409, detail="the last scene is still being written")
    async with session.lock:
        try:
            await asyncio.to_thread(work)
        except (TheatreCapReached, NothingHappens) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except Exception as exc:                     # the model or its provider failed; the scene is retried next step
            raise HTTPException(status_code=502, detail=f"the writer failed ({type(exc).__name__}: {exc}); try again") from None


@router.post("/{session_id}/step")
async def step(session_id: str, since: int = 0) -> dict[str, Any]:
    session = _get(session_id)
    await _run(session, session.theatre.step)
    return session.theatre.state(since)


@router.post("/{session_id}/say")
async def say(session_id: str, body: SayBody, since: int = 0) -> dict[str, Any]:
    session = _get(session_id)
    await _run(session, lambda: session.theatre.say(body.text))
    if body.then_step:
        await _run(session, session.theatre.step)
    return session.theatre.state(since)
