import numpy as np
from pathlib import Path

from backend.app.knowledge.contracts.index_bundle import CharacterIndexBundle
from backend.app.knowledge.runtime.index_service import IndexService
from backend.app.knowledge.runtime.faiss_shim import get_faiss
from backend.app.knowledge.runtime.retrieve import retrieve_knowledge


def _make_bundle_with_namespace():
    chunks = [
        {"chunk_id": "a", "text": "alpha detail", "namespace": "user-story-1"},
        {"chunk_id": "b", "text": "beta detail", "namespace": "other-story-1"},
    ]

    class FakeBM25:
        def get_scores(self, _):
            return [2.0, 0.5]

    faiss = get_faiss()
    index = faiss.IndexFlatIP(2)
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    maybe_norm = faiss.normalize_L2(vecs)
    index.add(maybe_norm if maybe_norm is not None else vecs)

    return CharacterIndexBundle(
        character_id="test_character",
        artifact_dir=Path("."),  # not used in retrieval
        chunks=chunks,
        chunk_ids=[c["chunk_id"] for c in chunks],
        bm25=FakeBM25(),
        faiss_index=index,
    )


def test_retrieve_knowledge_namespaced_hybrid(monkeypatch):
    bundle = _make_bundle_with_namespace()

    # Isolate IndexService for this test
    IndexService.reset_for_tests()
    monkeypatch.setattr(IndexService, "get", classmethod(lambda cls: bundle))

    # Mock embed_query to avoid LLM calls
    monkeypatch.setattr("backend.app.knowledge.build.embedder.embed_query", lambda q: [1.0, 0.0])

    results, debug = retrieve_knowledge(
        "alpha",
        k_bm25=2,
        k_faiss=2,
        k_final=2,
        namespace="user-story-1",
    )

    assert [r["chunk_id"] for r in results] == ["a"]
    assert debug["namespace"] == "user-story-1"
    assert debug["bm25_idxs"] == [0]
    assert debug["faiss_idxs"] == [0]

    # Switching namespace should exclude the first chunk
    results_other, debug_other = retrieve_knowledge(
        "alpha",
        k_bm25=2,
        k_faiss=2,
        k_final=2,
        namespace="other-story-1",
    )
    assert [r["chunk_id"] for r in results_other] == ["b"]
    assert debug_other["namespace"] == "other-story-1"


def test_retrieve_knowledge_fallback_respects_namespace(monkeypatch):
    # Build bundle without bm25/faiss to force fallback path
    chunks = [
        {"chunk_id": "c", "text": "gamma text", "namespace": "ns"},
        {"chunk_id": "d", "text": "delta text", "namespace": "other"},
    ]
    bundle = CharacterIndexBundle(
        character_id="fallback_character",
        artifact_dir=Path("."),
        chunks=chunks,
        chunk_ids=[c["chunk_id"] for c in chunks],
        bm25=None,
        faiss_index=None,
    )

    IndexService.reset_for_tests()
    monkeypatch.setattr(IndexService, "get", classmethod(lambda cls: bundle))

    results, debug = retrieve_knowledge("gamma", k_final=2, namespace="ns")
    assert [r["chunk_id"] for r in results] == ["c"]
    assert debug["namespace"] == "ns"

    results_other, _ = retrieve_knowledge("gamma", k_final=2, namespace="other")
    assert [r["chunk_id"] for r in results_other] == ["d"]