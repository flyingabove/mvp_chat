"""Tests for backend/app/api/debug_engine.py"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api.debug_engine import (
    _is_local,
    _build_scorer_context,
    _build_player_brief,
    _verify_game_ended,
    generate,
    ollama_generate,
    cloud_generate,
)


# ---------------------------------------------------------------------------
# _is_local
# ---------------------------------------------------------------------------

def test_is_local_localhost():
    assert _is_local("localhost:8899") is True


def test_is_local_127():
    assert _is_local("127.0.0.1:8000") is True


def test_is_local_hosted():
    assert _is_local("storieschat.ai") is False


def test_is_local_beta_api():
    assert _is_local("beta-api.storieschat.ai") is False


# ---------------------------------------------------------------------------
# _build_scorer_context
# ---------------------------------------------------------------------------

def test_build_scorer_context_empty():
    assert _build_scorer_context({}) == ""


def test_build_scorer_context_includes_canonical_facts():
    ctx = {
        "title": "The Ghost",
        "canonical_facts": [{"text": "IU died in 2020", "known_by": ["iu"]}],
        "characters": [],
        "protagonist": {},
        "character_self_knowledge": [],
    }
    result = _build_scorer_context(ctx)
    assert "IU died in 2020" in result
    assert "CANONICAL FACTS" in result


def test_build_scorer_context_title():
    ctx = {"title": "Murder Mystery"}
    result = _build_scorer_context(ctx)
    assert "Murder Mystery" in result


def test_build_scorer_context_character_flags():
    ctx = {
        "characters": [{"name": "Alice", "role": "suspect", "is_main": True, "is_suspect": True, "tags": []}],
    }
    result = _build_scorer_context(ctx)
    assert "[MAIN NPC]" in result
    assert "[SUSPECT]" in result


# ---------------------------------------------------------------------------
# _build_player_brief (async, mocked HTTP)
# ---------------------------------------------------------------------------

def _make_mock_http_client(status: int, data: dict):
    """Helper: create a mock AsyncClient whose .get() returns a sync-json response."""
    mock_response = MagicMock()
    mock_response.status_code = status
    mock_response.json.return_value = data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


@pytest.mark.asyncio
async def test_build_player_brief_returns_empty_on_error():
    """Returns empty string if context API call fails."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("connection refused")

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.app.api.debug_engine.httpx.AsyncClient", return_value=mock_ctx):
        result = await _build_player_brief("story_1", "http://localhost:8000")
    assert result == ""


@pytest.mark.asyncio
async def test_build_player_brief_includes_public_meta():
    """Player brief includes title, player role, and win condition — same as real user sees."""
    # Mirrors the /api/story/{story_id} response shape (public endpoint)
    meta_data = {
        "title": "The Manor Mystery",
        "goal": {"win_text_rule": "Get a full confession from the killer."},
        "rules": {"player_role": "You are a detective investigating a suspicious death."},
        "known_locations": [],
    }

    with patch("backend.app.api.debug_engine.httpx.AsyncClient",
               return_value=_make_mock_http_client(200, meta_data)):
        brief = await _build_player_brief("story_1", "http://localhost:8000")

    assert "The Manor Mystery" in brief
    assert "detective" in brief
    assert "confession" in brief


@pytest.mark.asyncio
async def test_build_player_brief_excludes_character_list():
    """Player brief must NOT contain character names — real users discover them through gameplay."""
    meta_data = {
        "title": "Test Story",
        "goal": {"win_text_rule": "Solve the case."},
        "rules": {"player_role": "investigator"},
        "known_locations": [],
    }

    with patch("backend.app.api.debug_engine.httpx.AsyncClient",
               return_value=_make_mock_http_client(200, meta_data)):
        brief = await _build_player_brief("story_1", "http://localhost:8000")

    # No character names or roles should leak through
    assert "Ghost IU" not in brief
    assert "Manager Kim" not in brief
    assert "butler" not in brief
    assert "suspect" not in brief


# ---------------------------------------------------------------------------
# generate dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_dispatches_local():
    """generate() with local=True calls ollama_generate."""
    with patch("backend.app.api.debug_engine.ollama_generate", new_callable=AsyncMock) as mock_ollama:
        mock_ollama.return_value = "hello"
        result = await generate("llama3.1:8b", "sys", "user", local=True)
        assert result == "hello"
        mock_ollama.assert_called_once_with("llama3.1:8b", "sys", "user")


@pytest.mark.asyncio
async def test_generate_dispatches_online():
    """generate() with local=False calls cloud_generate."""
    with patch("backend.app.api.debug_engine.cloud_generate", new_callable=AsyncMock) as mock_cloud:
        mock_cloud.return_value = "cloud response"
        result = await generate("gpt-4o", "sys", "user", local=False)
        assert result == "cloud response"
        mock_cloud.assert_called_once_with("gpt-4o", "sys", "user")


# ---------------------------------------------------------------------------
# _verify_game_ended
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_game_ended_false_for_normal_reply():
    """Normal NPC reply should not trigger game-end detection."""
    result = await _verify_game_ended("Hello there, how can I help?", "model", local=True)
    assert result is False


@pytest.mark.asyncio
async def test_verify_game_ended_calls_llm_when_marker_present():
    """When 'END GAME' is in reply, the LLM verifier is called."""
    sentinel = "[@@GAME ENDED CONGRATS@@]"
    with patch("backend.app.api.debug_engine.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = sentinel
        result = await _verify_game_ended("END GAME YOU WIN — congratulations!", "model", local=True)
    assert result is True


@pytest.mark.asyncio
async def test_verify_game_ended_returns_false_when_llm_says_no():
    """LLM saying NO means game has not ended."""
    with patch("backend.app.api.debug_engine.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "NO"
        result = await _verify_game_ended("END GAME — dramatic scene here", "model", local=False)
    assert result is False


@pytest.mark.asyncio
async def test_verify_game_ended_trusts_literal_on_llm_error():
    """If LLM call fails, falls back to True (literal check already passed)."""
    with patch("backend.app.api.debug_engine.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.side_effect = Exception("Ollama unavailable")
        result = await _verify_game_ended("Game already finished", "model", local=True)
    assert result is True


# ---------------------------------------------------------------------------
# GET /beta/debug route (integration via TestClient)
# ---------------------------------------------------------------------------

def test_debug_ui_route_200(tmp_path):
    """GET /beta/debug should return 200 with the debug.html content."""
    from pathlib import Path
    import backend.app.main as main_module

    # Point _DEBUG_HTML_PATH at a temp file so the test doesn't depend on file system
    fake_html = "<html><body>Debug</body></html>"
    fake_path = tmp_path / "debug.html"
    fake_path.write_text(fake_html, encoding="utf-8")

    original = main_module._DEBUG_HTML_PATH
    main_module._DEBUG_HTML_PATH = fake_path
    try:
        client = TestClient(main_module.app)
        resp = client.get("/beta/debug")
        assert resp.status_code == 200
        assert "Debug" in resp.text
    finally:
        main_module._DEBUG_HTML_PATH = original
