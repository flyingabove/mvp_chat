

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


# --- BL-26: authored lore never reached the prompt ---------------------------
# Every turn passes namespace=<user>-<story>-<instance>. Authored bundle chunks
# carry no namespace, so the old filter dropped all of them: live retrieval for
# IU returned 0 of 57 lore chunks (8 with namespace="").

def _lore_and_tagged_bundle():
    chunks = [
        {"chunk_id": "lore_1", "text": "alpha authored lore"},                          # authored: no namespace
        {"chunk_id": "mine", "text": "alpha playthrough fact", "namespace": "user-story-1"},
        {"chunk_id": "theirs", "text": "alpha other playthrough", "namespace": "other-story-1"},
    ]

    class FakeBM25:
        def get_scores(self, _):
            return [3.0, 2.0, 1.0]

    faiss = get_faiss()
    index = faiss.IndexFlatIP(2)
    vecs = np.array([[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]], dtype="float32")
    maybe_norm = faiss.normalize_L2(vecs)
    index.add(maybe_norm if maybe_norm is not None else vecs)
    return CharacterIndexBundle(
        character_id="test_character", artifact_dir=Path("."), chunks=chunks,
        chunk_ids=[c["chunk_id"] for c in chunks], bm25=FakeBM25(), faiss_index=index,
    )


def test_authored_chunks_without_namespace_survive_a_session_namespace(monkeypatch):
    bundle = _lore_and_tagged_bundle()
    IndexService.reset_for_tests()
    monkeypatch.setattr(IndexService, "get", classmethod(lambda cls: bundle))
    monkeypatch.setattr("backend.app.knowledge.build.embedder.embed_query", lambda q: [1.0, 0.0])

    results, _ = retrieve_knowledge("alpha", k_bm25=3, k_faiss=3, k_final=3, namespace="user-story-1")
    ids = {r["chunk_id"] for r in results}
    assert "lore_1" in ids                 # authored lore is always eligible
    assert "mine" in ids                   # this playthrough's tagged chunk
    assert "theirs" not in ids             # another playthrough stays isolated


def test_fallback_keeps_authored_chunks_under_a_namespace(monkeypatch):
    chunks = [{"chunk_id": "lore", "text": "gamma lore"}, {"chunk_id": "x", "text": "gamma x", "namespace": "other"}]
    bundle = CharacterIndexBundle(character_id="fb", artifact_dir=Path("."), chunks=chunks,
                                  chunk_ids=["lore", "x"], bm25=None, faiss_index=None)
    IndexService.reset_for_tests()
    monkeypatch.setattr(IndexService, "get", classmethod(lambda cls: bundle))
    results, _ = retrieve_knowledge("gamma", k_final=2, namespace="ns")
    assert [r["chunk_id"] for r in results] == ["lore"]


def test_real_iu_lore_is_retrieved_on_the_live_namespaced_path(monkeypatch):
    from backend.app.api.prompt_engine import build_namespace_key

    IndexService.reset_for_tests()
    IndexService.set_active_character("1_iu")
    dim = getattr(IndexService.get().faiss_index, "d", 768)
    monkeypatch.setattr("backend.app.knowledge.build.embedder.embed_query",
                        lambda q: np.ones((1, dim), dtype="float32"))
    namespace = build_namespace_key(user_id="default_user", story_id="iu_murder_mystery", instance=1)
    results, _ = retrieve_knowledge("IU song album released", namespace=namespace)
    assert len(results) >= 4, "authored IU lore must survive the per-session namespace"
    lore_ids = set(IndexService.get().chunk_ids)
    assert all(r.get("chunk_id") in lore_ids for r in results)
    IndexService.reset_for_tests()


class _FakeSessionStore:
    def __init__(self, chunks):
        self._chunks = chunks

    def query(self, query, top_k=4):
        return self._chunks[:top_k]


def test_session_memory_keeps_its_share_when_lore_fills_every_slot(monkeypatch):
    """Once lore works, 8 static hits must not crowd out conversation memory."""
    chunks = [{"chunk_id": f"lore_{i}", "text": f"alpha lore {i}"} for i in range(10)]

    class FakeBM25:
        def get_scores(self, _):
            return [10.0 - i for i in range(10)]

    faiss = get_faiss()
    index = faiss.IndexFlatIP(2)
    vecs = np.array([[1.0, 0.0]] * 10, dtype="float32")
    maybe_norm = faiss.normalize_L2(vecs)
    index.add(maybe_norm if maybe_norm is not None else vecs)
    bundle = CharacterIndexBundle(character_id="t", artifact_dir=Path("."), chunks=chunks,
                                  chunk_ids=[c["chunk_id"] for c in chunks], bm25=FakeBM25(), faiss_index=index)
    IndexService.reset_for_tests()
    monkeypatch.setattr(IndexService, "get", classmethod(lambda cls: bundle))
    monkeypatch.setattr("backend.app.knowledge.build.embedder.embed_query", lambda q: [1.0, 0.0])
    session = _FakeSessionStore([{"chunk_id": f"ai-{i}", "text": f"alpha said {i}"} for i in range(6)])

    results, debug = retrieve_knowledge("alpha", namespace="user-story-1", session_store=session)
    ids = [r["chunk_id"] for r in results]
    assert len(ids) == 8
    assert sum(i.startswith("ai-") for i in ids) == 4     # half the slots for conversation memory
    assert sum(i.startswith("lore_") for i in ids) == 4
    assert debug["session_chunks_added"] == 4


def test_lore_fills_slots_session_memory_does_not_use(monkeypatch):
    bundle = _lore_and_tagged_bundle()
    IndexService.reset_for_tests()
    monkeypatch.setattr(IndexService, "get", classmethod(lambda cls: bundle))
    monkeypatch.setattr("backend.app.knowledge.build.embedder.embed_query", lambda q: [1.0, 0.0])
    session = _FakeSessionStore([{"chunk_id": "ai-1", "text": "alpha said"}])
    results, _ = retrieve_knowledge("alpha", k_bm25=3, k_faiss=3, k_final=3,
                                    namespace="user-story-1", session_store=session)
    assert [r["chunk_id"] for r in results][-1] == "ai-1"
    assert {"lore_1", "mine"} <= {r["chunk_id"] for r in results}
