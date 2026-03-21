"""Unit tests for SessionChunkStore.

Tests use no external dependencies — pure in-memory BM25 scoring.
"""
from backend.app.knowledge.runtime.session_chunk_store import SessionChunkStore


def _make_chunk(chunk_id: str, text: str, role: str = "usr") -> dict:
    return {
        "chunk_id": chunk_id,
        "character_id": "iu",
        "type": "dialogue_fact",
        "text": text,
        "confidence": "player_stated",
        "source_type": role,
        "source_msg_id": chunk_id.split("-")[1] if "-" in chunk_id else chunk_id,
    }


def test_empty_store_returns_empty_query():
    store = SessionChunkStore()
    assert store.query("any question") == []
    assert len(store) == 0


def test_add_chunks_increases_length():
    store = SessionChunkStore()
    store.add_chunks([_make_chunk("usr-abc123-0", "IU is a famous singer from Korea.")])
    assert len(store) == 1


def test_add_chunks_skips_chunks_with_missing_fields():
    store = SessionChunkStore()
    store.add_chunks([
        {"chunk_id": "x", "text": "valid"},
        {"text": "no id"},       # missing chunk_id
        {"chunk_id": "y"},       # missing text
        {},                      # missing both
    ])
    # Only the first has both chunk_id and text
    assert len(store) == 1


def test_query_returns_relevant_chunks():
    store = SessionChunkStore()
    store.add_chunks([
        _make_chunk("usr-abc-0", "IU lived in Gangnam-gu apartment before she died."),
        _make_chunk("usr-abc-1", "The detective suspects the butler committed the crime."),
        _make_chunk("ai-def-0", "IU's ghost haunts the sixth floor of the building."),
    ])
    results = store.query("IU apartment Gangnam", top_k=2)
    assert len(results) >= 1
    chunk_texts = [r["text"] for r in results]
    # The Gangnam chunk should be in top results
    assert any("Gangnam" in t for t in chunk_texts)


def test_query_respects_top_k():
    store = SessionChunkStore()
    for i in range(10):
        store.add_chunks([_make_chunk(f"usr-x-{i}", f"Fact number {i} about IU detective case.")])
    results = store.query("IU detective fact", top_k=3)
    assert len(results) <= 3


def test_query_only_returns_chunks_with_positive_score():
    store = SessionChunkStore()
    store.add_chunks([
        _make_chunk("usr-a-0", "The sky is blue and the grass is green."),
    ])
    # Query with no overlap — should return nothing (score 0)
    results = store.query("quantum physics nuclear reactor", top_k=4)
    # With BM25, zero-score chunks are excluded
    assert len(results) == 0


def test_all_chunks_returns_copy():
    store = SessionChunkStore()
    chunk = _make_chunk("usr-z-0", "Some fact.")
    store.add_chunks([chunk])
    all_c = store.all_chunks()
    assert len(all_c) == 1
    # Modifying the returned list doesn't affect internal store
    all_c.clear()
    assert len(store) == 1


def test_chunk_id_prefix_convention():
    """Chunk IDs must follow the usr-/ai- prefix convention."""
    store = SessionChunkStore()
    store.add_chunks([
        _make_chunk("usr-aabbcc112233-0", "User said something."),
        _make_chunk("ai-ddeeff445566-0", "AI said something."),
    ])
    ids = {c["chunk_id"] for c in store.all_chunks()}
    assert any(cid.startswith("usr-") for cid in ids)
    assert any(cid.startswith("ai-") for cid in ids)


def test_source_type_field_preserved():
    store = SessionChunkStore()
    store.add_chunks([
        _make_chunk("usr-111-0", "User fact."),
    ])
    chunk = store.all_chunks()[0]
    assert chunk["source_type"] == "usr"
    assert chunk["source_msg_id"] == "111"
