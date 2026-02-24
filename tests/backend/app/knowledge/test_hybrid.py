
def test_hybrid_retrieve_dedup_and_order():
    from backend.app.knowledge.build.hybrid import hybrid_retrieve

    bm25 = [1, 2, 3]
    faiss = [3, 4, 2, 5]
    fused = hybrid_retrieve(bm25, faiss, top_k=4)
    # Item present in both lists should win via RRF
    assert fused[0] == 3
    assert len(fused) == 4
    assert len(set(fused)) == 4

from backend.app.integration_playback.scenarios.scenario_hybrid_retrieval_thresholds import HybridRetrievalScenario


# -- Pytest entry point --
import pytest  # noqa: E402

pytest.importorskip("faiss")
pytest.importorskip("rank_bm25")

@pytest.mark.integration
def test_character_hybrid_retrieval_recall_threshold():
    HybridRetrievalScenario.run_as_test()
