"""BL-49: every story declares a briefing; one resolved payload feeds the screen, the chat card and the player agent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.engine.briefing import DEFAULT_CONTROLS, brief_lines, resolved, validate
from backend.app.engine.story_loader import build_story_registry

GOOD = {"briefing": {"goal": "Find the person who did it and get them to admit it.", "controls": []}}


def test_every_active_story_declares_a_valid_briefing():
    registry = build_story_registry()
    assert {"six_strangers", "iu_murder_mystery"} <= set(registry)
    for story_id, entry in registry.items():
        assert validate(entry["raw"]) == [], story_id


@pytest.mark.parametrize("cfg, fragment", [
    ({}, "missing"),
    ({"briefing": "go win"}, "missing"),
    ({"briefing": {"goal": "short"}}, "briefing.goal"),
    ({"briefing": {"goal": "x" * 701}}, "briefing.goal"),
    ({"briefing": {"goal": GOOD["briefing"]["goal"], "controls": "nope"}}, "list"),
    ({"briefing": {"goal": GOOD["briefing"]["goal"], "controls": [{"title": "Only a title"}]}}, "controls[0]"),
    ({"briefing": {"goal": GOOD["briefing"]["goal"], "controls": [{"title": " ", "text": "x"}]}}, "controls[0]"),
])
def test_a_bad_briefing_is_reported(cfg, fragment):
    assert any(fragment in problem for problem in validate(cfg))


def test_resolved_puts_the_shared_controls_first_then_the_games_own_and_its_endings():
    cfg = {"briefing": {"goal": "  Do the thing well enough to win.  ",
                        "controls": [{"title": "Extra", "text": "Only in this game."}]},
           "endings": [{"id": "w", "kind": "win", "title": "You won it", "summary": "s"},
                       {"id": "l", "kind": "loss", "title": "Cut", "summary": "s"}]}
    out = resolved(cfg)
    assert out["goal"] == "Do the thing well enough to win."
    assert out["controls"][:len(DEFAULT_CONTROLS)] == list(DEFAULT_CONTROLS)
    assert out["controls"][-1] == {"title": "Extra", "text": "Only in this game."}
    assert out["endings"] == [{"title": "You won it", "kind": "win"}, {"title": "Cut", "kind": "loss"}]


def test_the_shared_controls_teach_parentheses_the_map_and_the_menu():
    text = " ".join(f"{c['title']} {c['text']}" for c in DEFAULT_CONTROLS)
    assert "(parentheses) or [brackets]" in text and "game master" in text
    assert "[map]" in text and "/map" in text and "menu" in text.lower()


def test_terrace_briefing_says_what_to_do_without_leaking_the_rules():
    goal = resolved(build_story_registry()["six_strangers"]["raw"])["goal"].lower()
    assert "relationship" in goal and "leave the house with you" in goal and "director" in goal
    for hidden in ("standing", "tier", "cooldown", "70", "score", "threshold"):
        assert hidden not in goal, hidden
    extras = " ".join(c["text"] for c in resolved(build_story_registry()["six_strangers"]["raw"])["controls"])
    assert "[play ending]" in extras, "how to answer the leave-together card by text is taught"


def test_the_public_story_endpoint_returns_the_briefing_for_every_story():
    from fastapi.testclient import TestClient
    from backend.app import main
    client = TestClient(main.app)
    for story_id in ("six_strangers", "iu_murder_mystery"):
        body = client.get(f"/api/story/{story_id}").json()
        assert body["briefing"]["goal"] and len(body["briefing"]["controls"]) >= len(DEFAULT_CONTROLS)
        assert body.get("world_map_image"), "the briefing's Map card uses the story's own map"


def test_brief_lines_are_plain_text_for_bots_and_the_chat_card():
    lines = brief_lines(resolved(GOOD))
    assert lines[0].startswith("GOAL: Find the person")
    assert any(line.startswith("TALK TO THE GAME MASTER:") for line in lines)


def _mock_http(data):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = data
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_the_player_agent_is_briefed_from_the_same_briefing_not_a_hardcoded_mystery_goal():
    from backend.app.api.debug_engine import _build_player_brief
    meta = {"title": "Six Strangers", "goal": {"win_text_rule": "old text"}, "rules": {},
            "briefing": resolved(build_story_registry()["six_strangers"]["raw"])}
    with patch("backend.app.api.debug_engine.httpx.AsyncClient", return_value=_mock_http(meta)):
        brief = await _build_player_brief("six_strangers", "http://x")
    assert "GOAL: Get into a romantic relationship" in brief and "(parentheses)" in brief
    assert "Discover what happened" not in brief and "who is responsible" not in brief
