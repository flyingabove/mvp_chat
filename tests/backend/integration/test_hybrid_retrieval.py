import pytest

from backend.app.integration_playback.loader import ensure_scenarios_loaded
from backend.app.integration_playback.runner import run_scenario

pytest.importorskip("faiss")
pytest.importorskip("rank_bm25")


@pytest.mark.integration
def test_character_hybrid_retrieval_recall_threshold():
    ensure_scenarios_loaded()
    result = run_scenario("hybrid_retrieval_thresholds")

    assert all(entry["status"] == "ok" for entry in result["log"])
