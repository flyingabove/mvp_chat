"""One bounded retry for transient provider responses (429 / 5xx).

Arena gates and busy periods saturate the shared OpenAI rate limit; OpenAI's
429 body says e.g. "Please try again in 322ms". Returning the public "story
master unavailable" error on the first 429 turned many recoverable turns into
failures. This helper waits the suggested time (capped) and retries ONCE;
anything asking for longer than the cap fails fast.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Optional

RETRYABLE = {429, 500, 502, 503, 504}
MAX_WAIT_S = 2.0
DEFAULT_WAIT_S = 0.5
MIN_WAIT_S = 0.2
HINT = re.compile(r"try again in ([\d.]+)\s*(ms|s)\b", re.I)


def retry_delay(response: Any, cap_s: float = MAX_WAIT_S) -> Optional[float]:
    """Seconds to wait before one retry, or None when the response should not be retried."""
    if getattr(response, "status_code", 200) not in RETRYABLE:
        return None
    headers = getattr(response, "headers", None) or {}
    wait: Optional[float] = None
    try:
        if headers.get("retry-after-ms"):
            wait = float(headers["retry-after-ms"]) / 1000.0
        elif headers.get("retry-after"):
            wait = float(headers["retry-after"])
    except (TypeError, ValueError):
        wait = None
    if wait is None:
        match = HINT.search(str(getattr(response, "text", "") or ""))
        if match:
            value, unit = float(match.group(1)), match.group(2).lower()
            wait = value / 1000.0 if unit == "ms" else value
    wait = DEFAULT_WAIT_S if wait is None else max(MIN_WAIT_S, wait)
    return wait if wait <= cap_s else None


async def post_with_retry(client: Any, url: str, *, headers: dict, json: dict,
                          sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                          cap_s: float = MAX_WAIT_S) -> Any:
    response = await client.post(url, headers=headers, json=json)
    delay = retry_delay(response, cap_s)
    if delay is None:
        return response
    await sleep(delay)
    return await client.post(url, headers=headers, json=json)
