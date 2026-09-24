# backend/app/evaluation/release.py
"""Release helpers used by the promote-to-prod skill
(.claude/skills/promote-to-prod/SKILL.md).

  wait_for_commit(url, sha)  poll /api/health until the service runs `sha`
  smoke(url)                 exercise a live service the way a player would:
                             health, capabilities, home page, and a new game
                             + one real turn in every active story, through
                             the arena's own HostedTargetAdapter (guest
                             session, same /api/chat path as the browser)

Both return plain dicts so the CLI can print them and the skill can decide.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import httpx

from backend.app.evaluation.targets import HostedTargetAdapter, new_arm_session

SMOKE_STORIES = (("iu_murder_mystery", "M", "Alex"), ("six_strangers", "F", "Jamie"))
SMOKE_MESSAGE = "Hi, I just got here. What's going on?"


async def wait_for_commit(url: str, sha: str, *, timeout_s: float = 1500.0, interval_s: float = 30.0,
                          client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """True once /api/health reports a commit starting with `sha`."""
    own = client is None
    client = client or httpx.AsyncClient()
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    try:
        while True:
            try:
                r = await client.get(f"{url.rstrip('/')}/api/health", timeout=20.0)
                last = r.json() if r.status_code == 200 else {"status": r.status_code}
            except (httpx.HTTPError, ValueError) as exc:
                last = {"error": f"{type(exc).__name__}: {exc}"}
            if str(last.get("commit", "")).startswith(sha):
                return {"live": True, "commit": last.get("commit"), "deployment_id": last.get("deployment_id", "")}
            if time.monotonic() >= deadline:
                return {"live": False, "last": last}
            await asyncio.sleep(interval_s)
    finally:
        if own:
            await client.aclose()


async def smoke(url: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    own = client is None
    client = client or httpx.AsyncClient()
    target = HostedTargetAdapter("smoke", url, client, turn_timeout_s=120.0)
    checks: dict[str, Any] = {}
    try:
        ident = await target.identify()
        checks["health"] = {"ok": True, "commit": ident.commit, "environment": ident.environment}
        caps = await target.capabilities()
        checks["capabilities"] = {"ok": bool(caps), "contract": caps.get("contract_version")}
        home = await client.get(url.rstrip("/") + "/", timeout=30.0)
        checks["home_page"] = {"ok": home.status_code == 200, "status": home.status_code}
        for story_id, gender, name in SMOKE_STORIES:
            session = new_arm_session("smoke", f"{story_id}.{uuid.uuid4().hex[:6]}")
            opening = await target.start(session, story_id, gender, name)
            turn = await target.send(session, SMOKE_MESSAGE, f"smoke-{uuid.uuid4().hex[:8]}") \
                if not opening.error else opening
            checks[story_id] = {
                "ok": not opening.error and not turn.error and bool(opening.reply) and bool(turn.reply),
                "error": opening.error or turn.error,
                "reply_chars": len(turn.reply),
                "markdown_in_reply": "**" in turn.reply,
            }
    except (httpx.HTTPError, ValueError) as exc:
        checks["health"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if own:
            await client.aclose()
    passed = all(v.get("ok") for v in checks.values()) and "health" in checks
    return {"url": url, "passed": passed, "checks": checks}
