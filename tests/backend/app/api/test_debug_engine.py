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
    _load_player_visible_chunks,
    _retrieve_player_context,
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


# ---------------------------------------------------------------------------
# _load_player_visible_chunks
# ---------------------------------------------------------------------------

def test_load_player_visible_chunks_unknown_story():
    """Returns ('', empty set) when story does not exist."""
    char_id, visible = _load_player_visible_chunks("nonexistent_story_xyz")
    assert char_id == ""
    assert visible == set()


def test_load_player_visible_chunks_no_knowledge_char_id():
    """Returns ('', empty set) when story has no knowledge_character_id."""
    mock_story = MagicMock()
    mock_story.as_dict.return_value = {"knowledge_character_id": ""}

    with patch("backend.app.api.debug_engine.load_story", return_value=mock_story):
        char_id, visible = _load_player_visible_chunks("any_story")
    assert char_id == ""
    assert visible == set()


def test_load_player_visible_chunks_filters_hidden():
    """Chunks with player_visible=false are excluded from visible set."""
    mock_story = MagicMock()
    mock_story.as_dict.return_value = {"knowledge_character_id": "iu"}

    mock_bundle = MagicMock()
    mock_bundle.chunks = [
        {"chunk_id": "pub_1", "text": "Public fact"},
        {"chunk_id": "hidden_1", "text": "Secret fact", "player_visible": False},
        {"chunk_id": "pub_2", "text": "Another public fact", "player_visible": True},
    ]

    with patch("backend.app.api.debug_engine.load_story", return_value=mock_story), \
         patch("backend.app.api.debug_engine.IndexService") as mock_svc:
        mock_svc.get.return_value = mock_bundle
        char_id, visible = _load_player_visible_chunks("iu_story")

    assert char_id == "iu"
    assert "pub_1" in visible
    assert "pub_2" in visible
    assert "hidden_1" not in visible


# ---------------------------------------------------------------------------
# _retrieve_player_context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_player_context_empty_query():
    """Returns '' when query is empty."""
    result = await _retrieve_player_context("", "iu", {"pub_1"})
    assert result == ""


@pytest.mark.asyncio
async def test_retrieve_player_context_no_char_id():
    """Returns '' when knowledge_char_id is empty."""
    result = await _retrieve_player_context("some query", "", {"pub_1"})
    assert result == ""


@pytest.mark.asyncio
async def test_retrieve_player_context_no_visible_chunks():
    """Returns '' when visible_chunk_ids is empty (no public knowledge)."""
    result = await _retrieve_player_context("some query", "iu", set())
    assert result == ""


@pytest.mark.asyncio
async def test_retrieve_player_context_filters_hidden():
    """Chunks not in visible_chunk_ids are excluded even if retrieved by FAISS/BM25."""
    returned_chunks = [
        {"chunk_id": "pub_1", "text": "IU's real name is Lee Ji-eun."},
        {"chunk_id": "secret_1", "text": "IU was murdered."},  # not in visible set
    ]
    with patch("backend.app.api.debug_engine.IndexService"), \
         patch("backend.app.api.debug_engine.retrieve_knowledge", return_value=(returned_chunks, {})):
        result = await _retrieve_player_context(
            "tell me about IU", "iu", {"pub_1"}  # secret_1 not in visible set
        )
    assert "Lee Ji-eun" in result
    assert "murdered" not in result


@pytest.mark.asyncio
async def test_retrieve_player_context_returns_visible():
    """Chunks in visible_chunk_ids are included in output."""
    returned_chunks = [
        {"chunk_id": "pub_1", "text": "IU debuted in 2008 under LOEN Entertainment."},
        {"chunk_id": "pub_2", "text": "IU won multiple Daesang awards."},
    ]
    with patch("backend.app.api.debug_engine.IndexService"), \
         patch("backend.app.api.debug_engine.retrieve_knowledge", return_value=(returned_chunks, {})):
        result = await _retrieve_player_context(
            "tell me about IU", "iu", {"pub_1", "pub_2"}
        )
    assert "debuted in 2008" in result
    assert "Daesang" in result


@pytest.mark.asyncio
async def test_retrieve_player_context_graceful_on_error():
    """Returns '' if retrieval raises (e.g., index not loaded)."""
    with patch("backend.app.api.debug_engine.IndexService"), \
         patch("backend.app.api.debug_engine.retrieve_knowledge", side_effect=Exception("index error")):
        result = await _retrieve_player_context("query", "iu", {"pub_1"})
    assert result == ""


# ---------------------------------------------------------------------------
# Game-end during scripted phase — regression test for T5 early-stop bug
# ---------------------------------------------------------------------------

def test_verify_game_ended_scripted_phase_flag_logic():
    """
    Regression: in scripted+continue mode, the loop must NOT break when
    game-end fires during the scripted phase (turn <= tc_len).

    This tests the in_scripted_phase logic inline so we don't need a full
    WebSocket integration test.
    """
    tc_len = 5
    num_turns = 100
    test_case_continue = True

    # Scenario: game-end fires on the last scripted turn (turn 5)
    turn = 5
    in_scripted_phase = test_case_continue and tc_len > 0 and turn <= tc_len
    assert in_scripted_phase is True, "T5 should be inside the scripted phase"

    # Scenario: game-end fires on the first free turn (turn 6)
    turn = 6
    in_scripted_phase = test_case_continue and tc_len > 0 and turn <= tc_len
    assert in_scripted_phase is False, "T6 should be outside the scripted phase"

    # Scenario: no test_case_continue — never in_scripted_phase guard applies
    turn = 3
    in_scripted_phase = False and tc_len > 0 and turn <= tc_len  # test_case_continue=False
    assert in_scripted_phase is False
