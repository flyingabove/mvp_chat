import numpy as np

from backend.app.engine.story_loader import load_story
from backend.app.knowledge.runtime.index_service import IndexService
from backend.app.knowledge.runtime.retrieve import retrieve_knowledge


def test_jennie_story_uses_isolated_indexes(monkeypatch):
    IndexService.reset_for_tests()

    story = load_story("jennie_murder_mini")
    assert story, "Story config should load"
    assert story.get("id") == "jennie_murder_mini"
    assert story.get("main_character", {}).get("knowledge_character_id") == "2_jennie"

    # Load Jennie bundle and ensure chunks are scoped
    bundle_j = IndexService.get("2_jennie")
    assert all(c.get("character_id") == "2_jennie" for c in bundle_j.chunks)

    # Load another bundle to ensure caches stay separated
    bundle_iu = IndexService.get("1_iu")
    assert bundle_j.artifact_dir != bundle_iu.artifact_dir

    # Force active character to Jennie for retrieval
    IndexService.set_active_character("2_jennie")

    dim = getattr(bundle_j.faiss_index, "d", 768)
    monkeypatch.setattr(
        "backend.app.knowledge.build.embedder.embed_query",
        lambda q: np.ones((1, dim), dtype="float32"),
    )

    results, dbg = retrieve_knowledge("knife coverup in the kitchen", k_final=4)
    assert results, "Expected retrieval results for Jennie mini-game"
    assert all(r.get("character_id") == "2_jennie" for r in results)
    assert not any(r.get("chunk_id", "").startswith("iu_") for r in results)

    IndexService.reset_for_tests()
