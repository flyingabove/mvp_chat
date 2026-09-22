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
async def test_call_extractor_llm_raises_on_network_error():
    """Phase 1.2: _call_extractor_llm now RAISES on HTTP failure instead of
    swallowing to []. This is the deliberate contract change that lets
    extract_facts_with_status distinguish "provider failed" (must retry) from
    "genuinely nothing to extract" (safe to mark done) — the old []-for-both
    behavior meant a provider outage was silently recorded as a successful
    empty extraction. The OLD assertion (returns [] without raising) is now
    the contract of the public `extract_facts_from_message` wrapper instead —
    see test_extract_facts_from_message_returns_empty_on_llm_failure below."""
    from backend.app.knowledge.runtime.dialogue_extractor import _call_extractor_llm

    with patch("httpx.AsyncClient", side_effect=Exception("connection refused")):
        with pytest.raises(Exception, match="connection refused"):
            await _call_extractor_llm("some text")


@pytest.mark.asyncio
async def test_extract_facts_from_message_returns_empty_on_llm_failure():
    """The PUBLIC, backward-compatible contract: extract_facts_from_message
    still never raises, even though the underlying _call_extractor_llm now
    does. Many existing callers (and tests) depend on this."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message

    with patch("httpx.AsyncClient", side_effect=Exception("connection refused")):
        result = await extract_facts_from_message("some text", "user", "msg1", "char1")

    assert result == []


# ============================================================================
# Phase 1.2 — extract_facts_with_status / ExtractionResult: the richer
# contract durable callers use to distinguish a provider failure (must
# retry) from a genuinely fact-free message (safe to mark done, no retry).
# ============================================================================

@pytest.mark.asyncio
async def test_extract_facts_with_status_empty_text_is_empty_success():
    """An empty/whitespace message is EmptySuccess, not a failure — there was
    never anything to extract, so it must be marked done, not retried."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_with_status

    result = await extract_facts_with_status("", "user", "abc123", "iu")
    assert result.ok is True
    assert result.chunks == []

    result2 = await extract_facts_with_status("   \n\t  ", "user", "abc123", "iu")
    assert result2.ok is True
    assert result2.chunks == []


@pytest.mark.asyncio
async def test_extract_facts_with_status_success_with_facts():
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_with_status

    with patch("backend.app.knowledge.runtime.dialogue_extractor._call_extractor_llm",
               new=AsyncMock(return_value=["IU lived in the apartment."])):
        result = await extract_facts_with_status(
            "IU lived in this apartment.", role="user", msg_id="abc123", character_id="iu",
        )

    assert result.ok is True
    assert len(result.chunks) == 1
    assert result.chunks[0]["text"] == "IU lived in the apartment."
    assert result.error == ""


@pytest.mark.asyncio
async def test_extract_facts_with_status_genuinely_no_facts_is_empty_success():
    """The LLM ran successfully and found nothing worth extracting (e.g. "ok",
    "hi") — this must be ok=True with empty chunks, NOT a failure."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_with_status

    with patch("backend.app.knowledge.runtime.dialogue_extractor._call_extractor_llm",
               new=AsyncMock(return_value=[])):
        result = await extract_facts_with_status("ok", role="user", msg_id="abc123", character_id="iu")

    assert result.ok is True
    assert result.chunks == []


@pytest.mark.asyncio
async def test_extract_facts_with_status_provider_failure_is_not_ok():
    """THE regression test: a provider failure must be told apart from a
    fact-free message. Before Phase 1.2, both cases returned [] identically —
    a durable caller could not tell "nothing to extract" from "extraction
    never actually ran"."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_with_status

    with patch("httpx.AsyncClient", side_effect=Exception("connection refused")):
        result = await extract_facts_with_status(
            "some real dialogue with facts in it", role="user", msg_id="abc123", character_id="iu",
        )

    assert result.ok is False
    assert result.chunks == []
    assert "connection refused" in result.error


@pytest.mark.asyncio
async def test_extract_facts_with_status_chunk_ids_match_legacy_format():
    """Chunk shape/IDs must match extract_facts_from_message exactly — this
    is a parallel API, not a schema change."""
    from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_with_status

    with patch("backend.app.knowledge.runtime.dialogue_extractor._call_extractor_llm",
               new=AsyncMock(return_value=["A fact.", "Another fact."])):
        result = await extract_facts_with_status(
            "dialogue text", role="assistant", msg_id="ff1122334455", character_id="iu",
        )

    assert len(result.chunks) == 2
    assert result.chunks[0]["chunk_id"] == "ai-ff1122334455-0"
    assert result.chunks[1]["chunk_id"] == "ai-ff1122334455-1"
    assert result.chunks[0]["source_type"] == "ai"
    assert result.chunks[0]["confidence"] == "ai_stated"
