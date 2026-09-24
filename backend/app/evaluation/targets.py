# backend/app/evaluation/targets.py
"""Target adapters: how the arena talks to one deployed release (§10).

HostedTargetAdapter drives the REAL public game path (`/api/chat`), exactly
what the browser calls, so the evaluator never plays an easier simulated
game. Each arm gets its own evaluation guest identity + session id, so arms
are isolated from each other and from human users. Retries reuse the same
`request_id`, which the server's BL-02 idempotency turns into a replay rather
than a second game advance.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from backend.app.evaluation.contracts import ObservedState, TargetIdentity

# "please try again" = the game's own retry advice (e.g. an incomplete
# structured scene from a small local model); a player would resend.
TRANSIENT_ERROR_MARKERS = ("429", "rate limit", "unavailable right now", "try that again in a moment",
                           "timed out", "overloaded", "please try again")
GAME_END_MARKER = "END GAME YOU WIN"     # emitted by the engine itself (prompt_engine win path)
DEBUG_TOGGLE = "[D]"                     # player-facing toggle; returns the observational debug box


@dataclass
class ArmSession:
    session_id: str
    guest_id: str


@dataclass
class TurnResult:
    reply: str
    speaker_ids: list[str] = field(default_factory=list)
    observed: ObservedState = field(default_factory=ObservedState)
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error: str = ""

    @property
    def game_ended(self) -> bool:
        return GAME_END_MARKER in self.reply


class TargetAdapter(Protocol):
    label: str

    async def identify(self) -> TargetIdentity: ...
    async def public_story(self, story_id: str) -> dict[str, Any]: ...
    async def capabilities(self) -> dict[str, Any]: ...
    async def start(self, session: ArmSession, story_id: str, gender: str, player_name: str) -> TurnResult: ...
    async def send(self, session: ArmSession, message: str, request_id: str) -> TurnResult: ...


def is_transient(error: str) -> bool:
    low = error.lower()
    return any(m in low for m in TRANSIENT_ERROR_MARKERS)


def parse_observed(body: dict[str, Any]) -> ObservedState:
    box = body.get("debug_box") or {}
    if not isinstance(box, dict):
        return ObservedState()
    return ObservedState(
        timestamp=str(box.get("timestamp") or ""),
        location=str(box.get("location") or ""),
        location_uuid=str(box.get("location_uuid") or ""),
        speakers=tuple(str(s) for s in (box.get("speakers") or [])),
    )


def parse_speakers(body: dict[str, Any]) -> list[str]:
    out = []
    for seg in body.get("segments") or []:
        if isinstance(seg, dict) and seg.get("kind") == "dialogue" and seg.get("speaker_id"):
            if seg["speaker_id"] not in out:
                out.append(str(seg["speaker_id"]))
    return out


def new_arm_session(experiment_id: str, arm_id: str) -> ArmSession:
    return ArmSession(session_id=f"arena_{experiment_id}_{arm_id}".replace(".", "_")[:120],
                      guest_id=str(uuid.uuid4()))


class HostedTargetAdapter:
    def __init__(self, label: str, base_url: str, client: httpx.AsyncClient, *,
                 turn_timeout_s: float = 150.0, max_attempts: int = 5, backoff_s: float = 8.0) -> None:
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.turn_timeout_s = turn_timeout_s
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s

    async def identify(self) -> TargetIdentity:
        r = await self.client.get(f"{self.base_url}/api/health", timeout=30.0)
        r.raise_for_status()
        body = r.json()
        jev = body.get("jev") or {}
        return TargetIdentity(
            label=self.label,
            base_url=self.base_url,
            commit=str(body.get("commit") or "unknown"),
            environment=str(body.get("environment") or ""),
            deployment_id=str(body.get("deployment_id") or ""),
            content_schema_version=body.get("content_schema_version"),
            extractor_model=str(jev.get("model") or "") if jev.get("enabled") else "",
        )

    async def capabilities(self) -> dict[str, Any]:
        """GET /api/eval/capabilities; {} when the release predates it."""
        try:
            r = await self.client.get(f"{self.base_url}/api/eval/capabilities", timeout=30.0)
            body = r.json() if r.status_code == 200 else {}
            return body if isinstance(body, dict) and body.get("contract_version") else {}
        except (httpx.HTTPError, ValueError):
            return {}

    async def public_story(self, story_id: str) -> dict[str, Any]:
        r = await self.client.get(f"{self.base_url}/api/story/{story_id}", timeout=30.0)
        r.raise_for_status()
        return r.json()

    async def post_chat(self, session: ArmSession, message: str, request_id: str = "") -> TurnResult:
        payload: dict[str, Any] = {"session_id": session.session_id, "message": message}
        if request_id:
            payload["request_id"] = request_id
        headers = {"X-Guest-Id": session.guest_id, "Content-Type": "application/json"}
        last_error = ""
        for attempt in range(1, self.max_attempts + 1):
            t0 = time.perf_counter()
            try:
                r = await self.client.post(f"{self.base_url}/api/chat", json=payload, headers=headers,
                                           timeout=self.turn_timeout_s)
                latency = int((time.perf_counter() - t0) * 1000)
                if r.status_code >= 500 or r.status_code == 429:
                    last_error = f"HTTP {r.status_code}"
                elif r.status_code >= 400:
                    return TurnResult(reply="", latency_ms=latency, error=f"HTTP {r.status_code}: {r.text[:200]}")
                else:
                    body = r.json()
                    if not isinstance(body, dict):
                        return TurnResult(reply="", latency_ms=latency, error="non-object response")
                    if body.get("error"):
                        err = str(body["error"])[:300]
                        # A failed turn never commits state (atomic turn commit) and the
                        # dedupe token is written only on success, so resending the same
                        # request_id after an upstream capacity error is safe.
                        if not (request_id and is_transient(err)):
                            return TurnResult(reply="", latency_ms=latency, error=err)
                        last_error = err
                    else:
                        return TurnResult(
                            reply=str(body.get("reply") or ""),
                            speaker_ids=parse_speakers(body),
                            observed=parse_observed(body),
                            usage=dict(body.get("usage") or {}),
                            latency_ms=latency,
                        )
            except httpx.TimeoutException:
                last_error = f"timeout after {self.turn_timeout_s:.0f}s"
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            # Only retry when the server can dedupe the resend (request_id);
            # otherwise a retry could advance the game twice (§10).
            if not request_id or attempt == self.max_attempts:
                break
            await asyncio.sleep(self.backoff_s * (2 ** (attempt - 1)))
        return TurnResult(reply="", error=last_error or "request failed")

    async def start(self, session: ArmSession, story_id: str, gender: str, player_name: str) -> TurnResult:
        opening = await self.post_chat(session, f"__cmd_newgame__:{story_id}|{gender}|{player_name}")
        if opening.error:
            return opening
        toggle = await self.post_chat(session, DEBUG_TOGGLE)
        if toggle.error:
            return TurnResult(reply=opening.reply, error=f"debug toggle failed: {toggle.error}")
        return opening

    async def send(self, session: ArmSession, message: str, request_id: str) -> TurnResult:
        return await self.post_chat(session, message, request_id)
