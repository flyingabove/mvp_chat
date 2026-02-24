

import numpy as np

from backend.app.engine.story_loader import load_story
from backend.app.knowledge.runtime.index_service import IndexService
from backend.app.knowledge.runtime.retrieve import retrieve_knowledge
from tests.conftest import all_stories, all_character_ids


def test_jennie_story_uses_isolated_indexes(monkeypatch):
    """Test that each story uses isolated knowledge indexes (no cross-contamination)."""
    IndexService.reset_for_tests()

    # Auto-discover stories — need at least 2 for isolation testing
    stories = all_stories()
    assert len(stories) >= 2, "Need at least 2 stories to test isolation"
    char_ids = all_character_ids()
    assert len(char_ids) >= 2, "Need at least 2 character dirs to test isolation"

    # Pick the second story (index 1) as the "target" for this test
    target = stories[1]
    target_story_id = target["id"]
    target_char_id = target["config"].get("main_character", {}).get("knowledge_character_id", "")
    assert target_char_id, f"Story {target_story_id} missing knowledge_character_id"

    # Pick the first story as the "other" for comparison
    other = stories[0]
    other_char_id = other["config"].get("main_character", {}).get("knowledge_character_id", "")
    assert other_char_id, f"Story {other['id']} missing knowledge_character_id"
    assert target_char_id != other_char_id, "Stories must have different character IDs"

    # Load target story config
    story = load_story(target_story_id)
    assert story, "Story config should load"
    story_cfg = story.as_dict() if hasattr(story, "as_dict") else story
    assert story_cfg.get("id") == target_story_id
    assert story_cfg.get("main_character", {}).get("knowledge_character_id") == target_char_id

    # Load target bundle and ensure chunks are scoped
    bundle_target = IndexService.get(target_char_id)
    assert all(c.get("character_id") == target_char_id for c in bundle_target.chunks)

    # Load other bundle to ensure caches stay separated
    bundle_other = IndexService.get(other_char_id)
    assert bundle_target.artifact_dir != bundle_other.artifact_dir

    # Force active character to target for retrieval
    IndexService.set_active_character(target_char_id)

    dim = getattr(bundle_target.faiss_index, "d", 768)
    monkeypatch.setattr(
        "backend.app.knowledge.build.embedder.embed_query",
        lambda q: np.ones((1, dim), dtype="float32"),
    )

    results, dbg = retrieve_knowledge("knife coverup in the kitchen", k_final=4)
    assert results, f"Expected retrieval results for {target_story_id}"
    assert all(r.get("character_id") == target_char_id for r in results)

    # Ensure no chunks from the other character leaked in
    other_prefix = other_char_id.split("_", 1)[-1] + "_" if "_" in other_char_id else other_char_id + "_"
    assert not any(r.get("chunk_id", "").startswith(other_prefix) for r in results)

    IndexService.reset_for_tests()


from backend.app.integration_playback.scenarios.scenario_character_retrieval_e2e import RetrievalE2EScenario


# -- Pytest entry point --
import pytest  # noqa: E402

@pytest.mark.integration
def test_character_retrieval_returns_real_knowledge():
    RetrievalE2EScenario.run_as_test()


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
