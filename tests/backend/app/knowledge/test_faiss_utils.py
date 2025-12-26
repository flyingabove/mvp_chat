import numpy as np


def test_build_faiss_index_and_search(tmp_path):
    import pytest
    import faiss
    if not hasattr(faiss, "IndexFlatIP"):
        pytest.skip("faiss not available")
    from backend.app.knowledge.build.faiss_utils import build_faiss_index, faiss_search

    embs = np.array([
        [1.0, 0.0],
        [0.0, 1.0],
        [0.7, 0.7],
    ], dtype="float32")
    out = tmp_path / "faiss.index"
    idx = build_faiss_index(embs, out)
    assert out.exists()

    q = np.array([[1.0, 0.0]], dtype="float32")
    top_idxs, scores = faiss_search(idx, q, k=2)
    assert top_idxs[0] == 0
    assert len(scores) == 2