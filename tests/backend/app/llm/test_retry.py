"""Bounded single retry on 429/5xx (QC round 1, 2026-09-25)."""
import asyncio
from types import SimpleNamespace

import pytest

from backend.app.llm.retry import post_with_retry, retry_delay


def resp(status, text="", headers=None):
    return SimpleNamespace(status_code=status, text=text, headers=headers or {})


OPENAI_429 = ('{"error": {"message": "Rate limit reached for gpt-4o-mini ... Please try again in 322ms. '
              'Visit https://platform.openai.com/account/rate-limits"}}')


@pytest.mark.parametrize("response,expected", [
    (resp(200), None),
    (resp(400), None),
    (resp(401), None),
    (resp(429, OPENAI_429), 0.322),
    (resp(429, "try again in 1.587s"), 1.587),
    (resp(429, "", {"retry-after": "1"}), 1.0),
    (resp(429, "", {"retry-after-ms": "40"}), 0.2),      # floored
    (resp(503), 0.5),                                    # default wait
    (resp(429, "try again in 20s"), None),               # too long: fail fast
    (resp(429, "", {"retry-after": "junk"}), 0.5),
])
def test_retry_delay(response, expected):
    assert retry_delay(response) == (pytest.approx(expected) if expected is not None else None)


class FakeClient:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    async def post(self, url, headers=None, json=None):
        self.calls += 1
        return self.responses.pop(0)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_one_retry_recovers_a_rate_limited_call():
    waits = []

    async def sleep(seconds):
        waits.append(seconds)
    client = FakeClient(resp(429, OPENAI_429), resp(200))
    result = run(post_with_retry(client, "u", headers={}, json={}, sleep=sleep))
    assert result.status_code == 200 and client.calls == 2 and waits == [pytest.approx(0.322)]


def test_never_more_than_one_retry():
    async def sleep(seconds):
        pass
    client = FakeClient(resp(429), resp(429), resp(200))
    assert run(post_with_retry(client, "u", headers={}, json={}, sleep=sleep)).status_code == 429
    assert client.calls == 2


def test_non_retryable_and_long_waits_are_returned_immediately():
    async def sleep(seconds):
        raise AssertionError("must not sleep")
    for first in (resp(200), resp(400), resp(429, "try again in 30s")):
        client = FakeClient(first, resp(200))
        assert run(post_with_retry(client, "u", headers={}, json={}, sleep=sleep)) is first
        assert client.calls == 1
