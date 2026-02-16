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
