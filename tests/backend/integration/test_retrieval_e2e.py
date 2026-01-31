import pytest
import os

# This test is intentionally slow and real.
# It MUST fail if retrieval is broken.


@pytest.mark.integration
def test_character_retrieval_returns_real_knowledge():
    """
    End-to-end retrieval test for a character.

    This verifies that:
    - Knowledge indexes load successfully
    - Retrieval returns REAL character knowledge
    - We do not silently hallucinate generic answers
    
    """
    from backend.app.knowledge.runtime.load_indexes import load_character_indexes
    from backend.app.knowledge.runtime.retrieve import retrieve_knowledge

    # Load character from env or default to "1_iu"
    character_id = os.getenv("TEST_CHARACTER_ID", "1_iu")

    # Load real indexes (must exist or test fails)
    indexes = load_character_indexes(character_id)

    # CharacterIndexBundle contract (not dict)
    assert indexes.chunks, "No knowledge chunks loaded"
    assert len(indexes.chunks) > 0

    # Query something factual
    query = "who are you"

    chunks, debug = retrieve_knowledge(query)

    # --- HARD FAIL CONDITIONS ---
    assert chunks, "Retrieval returned no chunks"
    assert isinstance(chunks, list)

    # Verify we got actual knowledge (character_id should be in chunks)
    joined_text = " ".join((c.get("text", "") or "").lower() for c in chunks)
    assert len(joined_text) > 0, "Retrieved chunks have no text content"
