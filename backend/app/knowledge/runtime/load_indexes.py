from pathlib import Path
import os
import faiss
import numpy as np
from app.knowledge.common.bm25_runtime import load_bm25

CHARACTER_ID = "1_iu"

BASE_KNOWLEDGE_DIR = Path(__file__).resolve().parents[1]  # .../knowledge
CACHE_ROOT = Path(os.getenv("KNOWLEDGE_CACHE_DIR", str(BASE_KNOWLEDGE_DIR))).resolve()
CHAR_DIR = CACHE_ROOT / "characters" / CHARACTER_ID

def load_character_indexes():
    faiss_index = faiss.read_index(str(CHAR_DIR / "faiss.index"))
    embeddings = np.load(CHAR_DIR / "embeddings.npy")
    bm25 = load_bm25(CHAR_DIR / "bm25.json")
    return {"faiss": faiss_index, "embeddings": embeddings, "bm25": bm25}
