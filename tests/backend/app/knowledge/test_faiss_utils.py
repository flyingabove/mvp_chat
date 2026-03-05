from pathlib import Path
import numpy as np

from backend.app.knowledge.build.faiss_utils import build_faiss_index, faiss_search


def test_build_faiss_index_and_search(tmp_path: Path):
    out = tmp_path / "faiss.index"

    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    index = build_faiss_index(vecs, out)
    assert out.exists()

    idxs, scores = faiss_search(index, [1.0, 0.0], k=1)
    assert idxs[0] == 0
    assert isinstance(scores[0], float)
