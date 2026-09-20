"""Unit tests for dialogue_extractor.

LLM calls are mocked — no network required.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_extract_facts_returns_empty_for_empty_text():
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message
    result = await extract_facts_from_message("", "user", "abc123", "iu")
    assert result == []


@pytest.mark.asyncio
async def test_extract_facts_returns_empty_for_whitespace_only():
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message
    result = await extract_facts_from_message("   \n\t  ", "user", "abc123", "iu")
    assert result == []


@pytest.mark.asyncio
async def test_extract_facts_usr_prefix_for_user_role():
    """Chunks from user messages must have chunk_ids starting with 'usr-'."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message

    with patch("backend.app.knowledge.runtime.dialogue_extractor._call_extractor_llm",
               new=AsyncMock(return_value=["IU lived in the apartment.", "She is a ghost."])):
        chunks = await extract_facts_from_message(
            "IU lived in this apartment and she is a ghost.",
            role="user",
            msg_id="abc123def456",
            character_id="iu",
        )

    assert len(chunks) == 2
    assert all(c["chunk_id"].startswith("usr-abc123def456-") for c in chunks)
    assert chunks[0]["source_type"] == "usr"
    assert chunks[0]["source_msg_id"] == "abc123def456"


@pytest.mark.asyncio
async def test_extract_facts_ai_prefix_for_assistant_role():
    """Chunks from AI messages must have chunk_ids starting with 'ai-'."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message

    with patch("backend.app.knowledge.runtime.dialogue_extractor._call_extractor_llm",
               new=AsyncMock(return_value=["The NPC revealed a secret."])):
        chunks = await extract_facts_from_message(
            "I... I did live here once.",
            role="assistant",
            msg_id="ff1122334455",
            character_id="iu",
        )

    assert len(chunks) == 1
    assert chunks[0]["chunk_id"].startswith("ai-ff1122334455-")
    assert chunks[0]["source_type"] == "ai"
    assert chunks[0]["confidence"] == "ai_stated"


@pytest.mark.asyncio
async def test_extract_facts_limits_to_5_chunks():
    """At most 5 chunks returned even if LLM gives more."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message

    many_facts = [f"Fact number {i}." for i in range(10)]
    with patch("backend.app.knowledge.runtime.dialogue_extractor._call_extractor_llm",
               new=AsyncMock(return_value=many_facts)):
        chunks = await extract_facts_from_message(
            "Some long message with many facts.",
            role="user",
            msg_id="aaabbb",
            character_id="iu",
        )

    assert len(chunks) <= 5


@pytest.mark.asyncio
async def test_extract_facts_chunk_ids_are_sequential():
    """Chunk IDs should be {prefix}-{msg_id}-0, -1, -2, ..."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message

    with patch("backend.app.knowledge.runtime.dialogue_extractor._call_extractor_llm",
               new=AsyncMock(return_value=["Fact A.", "Fact B.", "Fact C."])):
        chunks = await extract_facts_from_message(
            "Some text.", role="user", msg_id="xyz999", character_id="iu",
        )

    ids = [c["chunk_id"] for c in chunks]
    assert ids == ["usr-xyz999-0", "usr-xyz999-1", "usr-xyz999-2"]


@pytest.mark.asyncio
async def test_extract_facts_returns_empty_on_llm_failure():
    """If LLM call fails, extract_facts_from_message returns [] without raising."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message

    with patch("backend.app.knowledge.runtime.dialogue_extractor._call_extractor_llm",
               new=AsyncMock(side_effect=Exception("network error"))):
        # Should not raise
        result = await extract_facts_from_message(
            "Some message.", role="user", msg_id="fail123", character_id="iu",
        )
    assert result == []


@pytest.mark.asyncio
async def test_call_extractor_llm_parses_json_array():
    """_call_extractor_llm should parse a clean JSON array from LLM output."""
    from backend.app.knowledge.runtime.dialogue_extractor import _call_extractor_llm

    mock_content = '["IU is the previous tenant.", "She died in the apartment."]'
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": mock_content}}]
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _call_extractor_llm("IU is the previous tenant who died here.")

    assert "IU is the previous tenant." in result
    assert len(result) == 2


@pytest.mark.asyncio
async def test_call_extractor_llm_strips_markdown_fences():
    """_call_extractor_llm should handle ```json ... ``` wrapping."""
    from backend.app.knowledge.runtime.dialogue_extractor import _call_extractor_llm

    mock_content = '```json\n["Fact one.", "Fact two."]\n```'
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": mock_content}}]
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _call_extractor_llm("Some text.")

    assert "Fact one." in result
    assert "Fact two." in result


@pytest.mark.asyncio
async def test_call_extractor_llm_returns_empty_on_network_error():
    """_call_extractor_llm returns [] without raising on HTTP failure."""
    from backend.app.knowledge.runtime.dialogue_extractor import _call_extractor_llm

    with patch("httpx.AsyncClient", side_effect=Exception("connection refused")):
        result = await _call_extractor_llm("some text")

    assert result == []
