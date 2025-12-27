from pathlib import Path
import numpy as np
import pytest


def test_build_faiss_index_and_search(tmp_path: Path):
    faiss = pytest.importorskip("faiss")
    if not hasattr(faiss, "IndexFlatIP"):
        pytest.skip("faiss not available")

    from backend.app.knowledge.build.faiss_utils import build_faiss_index, faiss_search

    out = tmp_path / "faiss.index"

    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    index = build_faiss_index(vecs, out)
    assert out.exists()

    idxs, scores = faiss_search(index, [1.0, 0.0], k=1)
    assert idxs[0] == 0
    assert isinstance(scores[0], float)
