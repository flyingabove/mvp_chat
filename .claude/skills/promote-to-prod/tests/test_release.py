"""Tests for the release helpers used by the promote-to-prod skill."""
import json

import httpx
import pytest

from arena.release import SMOKE_STORIES, smoke, wait_for_commit


def health_transport(commits):
    def handler(request: httpx.Request) -> httpx.Response:
        commit = commits.pop(0) if len(commits) > 1 else commits[0]
        return httpx.Response(200, json={"ok": True, "commit": commit, "deployment_id": "dep"})
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_wait_for_commit_returns_when_the_new_commit_is_live():
    async with httpx.AsyncClient(transport=health_transport(["old", "old", "abc1234def"])) as c:
        result = await wait_for_commit("https://x", "abc1234", interval_s=0, timeout_s=5, client=c)
    assert result == {"live": True, "commit": "abc1234def", "deployment_id": "dep"}


@pytest.mark.asyncio
async def test_wait_for_commit_times_out_with_the_last_answer():
    async with httpx.AsyncClient(transport=health_transport(["old"])) as c:
        result = await wait_for_commit("https://x", "abc1234", interval_s=0, timeout_s=0, client=c)
    assert result["live"] is False and result["last"]["commit"] == "old"


def game_transport(fail_story=None):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"commit": "c", "environment": "prod", "content_schema_version": 1})
        if path == "/api/eval/capabilities":
            return httpx.Response(200, json={"contract_version": "arena-capabilities-1"})
        if path == "/":
            return httpx.Response(200, text="<html>")
        body = json.loads(request.content)
        if fail_story and fail_story in body["message"]:
            return httpx.Response(200, json={"error": f"story not found: {fail_story}"})
        return httpx.Response(200, json={"reply": "A scene unfolds.", "segments": []})
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_smoke_passes_when_every_story_plays_a_turn():
    async with httpx.AsyncClient(transport=game_transport()) as c:
        result = await smoke("https://x", client=c)
    assert result["passed"]
    assert {sid for sid, _, _ in SMOKE_STORIES} <= set(result["checks"])


@pytest.mark.asyncio
async def test_smoke_fails_when_one_story_cannot_start():
    async with httpx.AsyncClient(transport=game_transport(fail_story="six_strangers")) as c:
        result = await smoke("https://x", client=c)
    assert not result["passed"]
    assert result["checks"]["six_strangers"]["error"].startswith("story not found")
    assert result["checks"]["iu_murder_mystery"]["ok"]
