from pathlib import Path
import faiss
import numpy as np
from backend.app.knowledge.common.bm25_runtime import load_bm25

# --------------------
# Persistent paths
# --------------------

CHARACTER_ID = "1_iu"

PERSIST_ROOT = Path("/data/knowledge_cache")
CHAR_DIR = PERSIST_ROOT / "characters" / "1_iu"

def load_character_indexes():
    if not CHAR_DIR.exists():
        raise RuntimeError(f"Persistent character dir missing: {CHAR_DIR}")

    faiss_path = CHAR_DIR / "faiss.index"
    emb_path = CHAR_DIR / "embeddings.npy"
    bm25_path = CHAR_DIR / "bm25.json"

    for p in [faiss_path, emb_path, bm25_path]:
        if not p.exists():
            raise RuntimeError(f"Missing index artifact: {p}")

    faiss_index = faiss.read_index(str(faiss_path))
    embeddings = np.load(emb_path)
    bm25 = load_bm25(bm25_path)

    return {
        "faiss": faiss_index,
        "embeddings": embeddings,
        "bm25": bm25,
    }
