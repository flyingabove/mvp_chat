import pytest

# This test is intentionally slow and real.
# It MUST fail if retrieval is broken.


@pytest.mark.integration
def test_iu_retrieval_returns_real_songs():
    """
    End-to-end retrieval test.

    This verifies that:
    - Knowledge indexes load successfully
    - Retrieval returns REAL IU knowledge
    - We do not silently hallucinate generic answers
    """

    from app.knowledge.runtime.load_indexes import load_character_indexes
    from app.knowledge.runtime.retrieve import retrieve_knowledge

    # Load real indexes (must exist or test fails)
    indexes = load_character_indexes("1_iu")

    assert "chunks" in indexes
    assert len(indexes["chunks"]) > 0, "No knowledge chunks loaded"

    # Query something factual and easy
    query = "what are some songs you sang"

    chunks, debug = retrieve_knowledge(query)

    # --- HARD FAIL CONDITIONS ---
    assert chunks, "Retrieval returned no chunks"
    assert isinstance(chunks, list)

    # Look for real IU song titles we KNOW exist in the KB
    joined_text = " ".join(c.get("text", "").lower() for c in chunks)

    expected_any = [
        "good day",
        "palette",
        "love poem",
        "through the night",
        "celebrity",
        "eight",
        "blueming",
    ]

    assert any(title in joined_text for title in expected_any), (
        "Retrieval did not return real IU song knowledge.\n"
        "This usually means:\n"
        "- Index not built\n"
        "- BM25/FAISS miswired\n"
        "- Retrieval silently failed\n\n"
        f"Retrieved text:\n{joined_text[:500]}"
    )
