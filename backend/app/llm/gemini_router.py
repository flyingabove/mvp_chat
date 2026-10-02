"""`call_gemini`: spend every free Gemini text model's quota, and never run into a limit.

The free tier gives each text model its own requests-per-minute (RPM), tokens-per-minute (TPM) and requests-per-day (RPD)
(the AI Studio "Rate limits by model" page), so the whole key can serve far more than the default model's 20 requests a
day. The router keeps the models in quality order and, for each call, picks the best one that still has room in all
three budgets, spills to the next when it does not, and waits a little rather than fail when every model is momentarily
full. Capacity is therefore used from the best model downwards until the day's budget is gone, which is the goal.

How it learns what is free:
- It counts its own calls per model (a sliding 60 s window for RPM and TPM, a per-day counter that resets at midnight
  Pacific, which is when Google resets), and persists the day counters so a restart does not forget them.
- It also reads what Google says: a 429 naming a per-day quota blocks that model until the reset; a 429 with a
  `retryDelay` blocks it for that long; a 5xx cools it for a short while; a 404 turns it off for an hour. This corrects the
  counts when other processes (beta, prod, a local script) share the same key.
- Token use is estimated before the call (prompt size plus `max_tokens`) and corrected with the real `usage` after it.

Callers pass the model they would have used; it only decides where in the quality order to start (a request for a lite
model never climbs to a bigger one). Anything that is not a Gemini URL is untouched. `GEMINI_ROUTER=off` switches it off.
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

GEMINI_HOST = "generativelanguage.googleapis.com"
MAX_WAIT_S = 10.0              # most a call will pause for a free slot before it reports the limit
MINUTE_S = 60.0
TOKEN_CHARS = 3.5              # rough characters per token for the pre-call estimate
RPM_MARGIN, TPM_SHARE, RPD_SHARE = 1, 0.90, 0.95
COOLDOWN_5XX_S, COOLDOWN_TIMEOUT_S, DISABLE_404_S = 20.0, 45.0, 3600.0
REASONING_EFFORT = "low"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    rpm: int
    tpm: int
    rpd: int
    thinking: bool = False        # a reasoning model: its hidden thinking counts against max_tokens and adds latency


# Best first. Limits are the free-tier numbers on the account's rate-limit page; edit them there and here together.
# Left out on purpose (probed live 2026-10-01): Pro models (limit 0), gemini-2.5-flash and 2.5-flash-lite (404, closed to new
# users), gemma-4-26b (500) and gemma-4-31b (answers with its chain of thought in the content, which would end up in a scene).
MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("gemini-3.8-flash", 5, 250_000, 20, thinking=True),
    ModelSpec("gemini-3.7-flash", 5, 250_000, 20, thinking=True),
    ModelSpec("gemini-3.6-flash", 5, 250_000, 20, thinking=True),
    ModelSpec("gemini-3.5-flash", 5, 250_000, 20, thinking=True),
    ModelSpec("gemini-3-flash-preview", 5, 250_000, 20, thinking=True),
    ModelSpec("gemini-3.5-flash-lite", 15, 250_000, 500),
    ModelSpec("gemini-3.1-flash-lite", 15, 250_000, 500),
)
ALIASES = {"gemini-3-flash": "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview": "gemini-3.1-flash-lite"}


def pacific_day(now: float) -> str:
    """The quota day (midnight Pacific to midnight Pacific) that `now` falls in."""
    try:
        from zoneinfo import ZoneInfo
        local = datetime.fromtimestamp(now, ZoneInfo("America/Los_Angeles"))
    except Exception:                                   # no tz database (a bare Windows install): standard time
        local = datetime.fromtimestamp(now, timezone(timedelta(hours=-8)))
    return local.strftime("%Y-%m-%d")


def estimate_tokens(body: dict) -> int:
    chars = sum(len(str(m.get("content") or "")) for m in body.get("messages") or [] if isinstance(m, dict))
    return int(chars / TOKEN_CHARS) + int(body.get("max_tokens") or 512)


@dataclass
class _Budget:
    window: deque = field(default_factory=deque)        # [time, tokens] pairs of the last minute (lists: settled in place)
    day: str = ""
    used_today: int = 0
    blocked_until: float = 0.0
    day_exhausted: bool = False


@dataclass
class Ticket:
    model: str
    entry: list


class GeminiRouter:
    def __init__(self, models: tuple[ModelSpec, ...] = MODELS, clock: Callable[[], float] = time.time,
                 state_path: Optional[Path] = None) -> None:
        self.models = models
        self.clock = clock
        self.state_path = state_path
        self._budget = {m.name: _Budget() for m in models}
        self._load()

    # -- capacity ------------------------------------------------------------------------------------------------
    def _limits(self, spec: ModelSpec) -> tuple[int, int, int]:
        rpm = spec.rpm - (RPM_MARGIN if spec.rpm >= 5 else 0)
        return max(1, rpm), max(1, int(spec.tpm * TPM_SHARE)), max(1, int(spec.rpd * RPD_SHARE))

    def _roll(self, name: str, now: float) -> _Budget:
        budget = self._budget[name]
        today = pacific_day(now)
        if budget.day != today:
            budget.day, budget.used_today, budget.day_exhausted = today, 0, False
        while budget.window and now - budget.window[0][0] >= MINUTE_S:
            budget.window.popleft()
        return budget

    def start_index(self, requested: str) -> int:
        requested = ALIASES.get(requested, requested)
        return next((i for i, m in enumerate(self.models) if m.name == requested), 0)

    def _free_in(self, spec: ModelSpec, tokens: int, now: float) -> Optional[float]:
        """Seconds until `spec` can take a call of `tokens`; 0 now, None when it cannot today."""
        budget = self._roll(spec.name, now)
        rpm, tpm, rpd = self._limits(spec)
        if budget.day_exhausted or budget.used_today >= rpd or tokens > tpm:
            return None
        wait = max(0.0, budget.blocked_until - now)
        window = list(budget.window)
        if len(window) >= rpm:
            wait = max(wait, window[len(window) - rpm][0] + MINUTE_S - now)
        spent = sum(t for _, t in window)
        if spent + tokens > tpm:
            freed = 0
            for stamp, used in window:
                freed += used
                if spent - freed + tokens <= tpm:
                    wait = max(wait, stamp + MINUTE_S - now)
                    break
        return wait

    def pick(self, requested: str, tokens: int, exclude: frozenset[str] = frozenset()) -> tuple[Optional[ModelSpec], Optional[float]]:
        """(best model with room now, None) or (None, seconds until one frees up / None if none will today)."""
        now = self.clock()
        soonest: Optional[float] = None
        for spec in self.models[self.start_index(requested):]:
            if spec.name in exclude:
                continue
            wait = self._free_in(spec, tokens, now)
            if wait == 0:
                return spec, None
            if wait is not None:
                soonest = wait if soonest is None else min(soonest, wait)
        return None, soonest

    def reserve(self, spec: ModelSpec, tokens: int) -> Ticket:
        now = self.clock()
        budget = self._roll(spec.name, now)
        entry = [now, tokens]
        budget.window.append(entry)
        budget.used_today += 1
        self._save()
        return Ticket(spec.name, entry)

    def settle(self, ticket: Ticket, actual_tokens: int) -> None:
        if actual_tokens > 0:
            ticket.entry[1] = actual_tokens

    def refund(self, ticket: Ticket) -> None:
        budget = self._budget[ticket.model]
        if ticket.entry in budget.window:
            budget.window.remove(ticket.entry)
            budget.used_today = max(0, budget.used_today - 1)
            self._save()

    # -- what the provider told us -------------------------------------------------------------------------------
    def block_for_day(self, name: str) -> None:
        budget = self._budget[name]
        budget.day, budget.day_exhausted = pacific_day(self.clock()), True
        self._save()

    def block_for(self, name: str, seconds: float) -> None:
        budget = self._budget[name]
        budget.blocked_until = max(budget.blocked_until, self.clock() + seconds)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        now = self.clock()
        out = {}
        for spec in self.models:
            budget = self._roll(spec.name, now)
            out[spec.name] = {"used_today": budget.used_today, "limit_today": self._limits(spec)[2],
                              "last_minute": len(budget.window), "exhausted": budget.day_exhausted,
                              "blocked_for_s": round(max(0.0, budget.blocked_until - now), 1)}
        return out

    # -- persistence: the day counters survive a restart ----------------------------------------------------------
    def _save(self) -> None:
        if self.state_path is None:
            return
        data = {name: {"day": b.day, "used": b.used_today, "exhausted": b.day_exhausted}
                for name, b in self._budget.items() if b.day}
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(_json.dumps(data), encoding="utf-8")
        except OSError:
            logger.debug("gemini router could not save its counters", exc_info=True)

    def _load(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            data = _json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        today = pacific_day(self.clock())
        for name, row in (data or {}).items():
            if name in self._budget and isinstance(row, dict) and row.get("day") == today:
                self._budget[name].day = today
                self._budget[name].used_today = int(row.get("used") or 0)
                self._budget[name].day_exhausted = bool(row.get("exhausted"))


_router: Optional[GeminiRouter] = None


def get_router() -> GeminiRouter:
    global _router
    if _router is None:
        data = Path("/data") if Path("/data").exists() else Path("./data")
        _router = GeminiRouter(state_path=data / "gemini_router.json")
    return _router


def reset_router_for_tests() -> None:
    global _router
    _router = None


def is_gemini_url(url: str) -> bool:
    return GEMINI_HOST in str(url) and os.environ.get("GEMINI_ROUTER", "on").lower() not in ("off", "0", "false")


def _retry_delay_s(text: str) -> Optional[float]:
    import re
    match = re.search(r'retryDelay"?\s*:\s*"?([\d.]+)s', text) or re.search(r"retry in ([\d.]+)s", text, re.I)
    return float(match.group(1)) if match else None


UNSUPPORTED_FIELDS = ("seed",)       # Gemini's OpenAI-compatible endpoint answers 400 to these (probed live)


def _prepare(body: dict, spec: ModelSpec) -> dict:
    """The caller's body for `spec`. Reasoning models get low reasoning effort unless the caller chose one: probed live, the
    default effort made scenes take 25 to 45 s and often cut the JSON off mid-way (hidden thinking eats max_tokens)."""
    out = {k: v for k, v in body.items() if k not in UNSUPPORTED_FIELDS}
    out["model"] = spec.name
    if spec.thinking and "reasoning_effort" not in out:
        out["reasoning_effort"] = REASONING_EFFORT
    return out


def _truncated(request: dict, response: Any) -> bool:
    """A 200 whose reply was cut off by max_tokens when the caller needed a whole answer (structured output, or nothing at all)."""
    try:
        choice = response.json()["choices"][0]
        content = str((choice.get("message") or {}).get("content") or "")
        if choice.get("finish_reason") != "length":
            return False
        if not content.strip():
            return True
        if request.get("response_format"):
            _json.loads(content)
        return False
    except ValueError:
        return True
    except (KeyError, IndexError, TypeError, AttributeError):
        return False


def _synthetic_limit(url: str, why: str) -> httpx.Response:
    return httpx.Response(429, json={"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": why}},
                          request=httpx.Request("POST", url))


async def call_gemini(client: Any, url: str, *, headers: dict, json: dict, timeout: Optional[float] = None,
                      router: Optional[GeminiRouter] = None,
                      sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                      max_wait_s: float = MAX_WAIT_S) -> Any:
    """POST a chat/completions body to Gemini on the best model that has room; returns the provider's response.

    Falls through the quality order on 429, 5xx, a missing model or a refused request, waits briefly when every model is
    only momentarily full, and returns the last real response (or a synthetic 429) when nothing can serve the call."""
    router = router or get_router()
    requested = str(json.get("model") or "")
    tokens = estimate_tokens(json)
    excluded: set[str] = set()
    waited, refused, last = 0.0, 0, None
    kwargs = {} if timeout is None else {"timeout": timeout}
    while True:
        spec, wait = router.pick(requested, tokens, frozenset(excluded))
        if spec is None:
            if wait is None or waited + wait > max_wait_s:
                break
            await sleep(wait + 0.05)
            waited += wait + 0.05
            continue
        ticket = router.reserve(spec, tokens)
        try:
            response = await client.post(url, headers=headers, json=_prepare(json, spec), **kwargs)
        except httpx.TransportError:
            router.refund(ticket)
            router.block_for(spec.name, COOLDOWN_TIMEOUT_S)     # a model that just timed out is skipped for a while
            excluded.add(spec.name)
            if len(excluded) >= len(router.models):
                raise
            continue
        status = response.status_code
        if 200 <= status < 300:
            try:
                router.settle(ticket, int((response.json().get("usage") or {}).get("total_tokens") or 0))
            except (ValueError, AttributeError):
                pass
            if not _truncated(json, response):
                return response
            last = response                             # cut off mid-answer: another model may finish it
            excluded.add(spec.name)
            continue
        last = response
        excluded.add(spec.name)
        if status == 429:
            text = str(response.text or "")
            if "perday" in text.lower().replace(" ", "").replace("_", ""):
                router.block_for_day(spec.name)
            else:
                router.block_for(spec.name, min(120.0, max(5.0, _retry_delay_s(text) or MINUTE_S)))
        elif status >= 500:
            router.block_for(spec.name, COOLDOWN_5XX_S)
        elif status == 404:
            router.block_for(spec.name, DISABLE_404_S)
        elif status in (400, 422):
            refused += 1
            if refused >= 2:                            # two models refused the same body: it is the request, not the model
                return response
        else:                                           # 401/403 and the like: a different model will not help
            return response
    return last if last is not None else _synthetic_limit(url, "every free Gemini model is at its limit right now")


async def llm_post(client: Any, url: str, *, headers: dict, json: dict, timeout: Optional[float] = None) -> Any:
    """One POST to any chat endpoint: Gemini goes through the router, everything else is a plain post."""
    if is_gemini_url(url):
        return await call_gemini(client, url, headers=headers, json=json, timeout=timeout)
    return await client.post(url, headers=headers, json=json, **({} if timeout is None else {"timeout": timeout}))
