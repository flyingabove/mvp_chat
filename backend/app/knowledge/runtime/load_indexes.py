from pathlib import Path
import numpy as np
import faiss

from backend.app.knowledge.build.bm25_utils import load_bm25

BASE = Path(__file__).resolve().parents[2]
CHAR_DIR = BASE / "knowledge" / "characters" / "1_iu"

def load_character_indexes():
    faiss_index = faiss.read_index(str(CHAR_DIR / "faiss.index"))
    embeddings = np.load(CHAR_DIR / "embeddings.npy")
    bm25 = load_bm25(CHAR_DIR / "bm25.json")

    return {
        "faiss": faiss_index,
        "bm25": bm25,
        "embeddings": embeddings,
    }
