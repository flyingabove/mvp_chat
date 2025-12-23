# backend/app/knowledge/runtime/load_indexes.py
from pathlib import Path
import os
import shutil
import faiss

from app.knowledge.runtime.bm25_runtime import load_bm25, search_bm25


def _load_chunks_jsonl(path: Path):
    import json
    chunks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunks.append(json.loads(line))
    return chunks


def _copy_if_missing(src: Path, dst: Path):
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)


def load_character_indexes(character_id: str = "1_iu"):
    """
    Loads indexes from persistent volume if available, otherwise falls back to
    image-bundled artifacts. If /data exists but is empty, it will initialize
    /data cache by copying artifacts from the image.
    """

    # --- Image-bundled knowledge directory (always present inside container) ---
    image_knowledge_dir = Path(__file__).resolve().parents[1]  # .../knowledge
    image_char_dir = image_knowledge_dir / "characters" / character_id

    # --- Persistent volume cache root (Railway volume mounted at /data) ---
    # Keep it separate from repo path. This is where we *prefer* runtime reads.
    persist_root = Path(os.getenv("KNOWLEDGE_PERSIST_ROOT", "/data/knowledge_cache"))
    persist_char_dir = persist_root / "characters" / character_id

    # Artifacts we need
    filenames = ["faiss.index", "bm25.json", "embeddings.npy", "build_info.json", "chunks.jsonl"]

    # Decide which dir to read from:
    # 1) If persistent dir exists AND has the needed files -> use it
    # 2) Else if image dir has them -> use image dir
    # 3) If /data exists but missing artifacts, initialize it by copying from image
    use_dir = None

    def has_required(d: Path) -> bool:
        return all((d / name).exists() for name in ["faiss.index", "bm25.json", "chunks.jsonl"])

    if has_required(persist_char_dir):
        use_dir = persist_char_dir
    elif has_required(image_char_dir):
        use_dir = image_char_dir

        # If /data is mounted, initialize it for future fast boots
        if Path("/data").exists():
            persist_char_dir.mkdir(parents=True, exist_ok=True)
            for name in filenames:
                _copy_if_missing(image_char_dir / name, persist_char_dir / name)
    else:
        raise RuntimeError(
            f"Could not locate required knowledge artifacts.\n"
            f"Checked persistent: {persist_char_dir}\n"
            f"Checked image: {image_char_dir}\n"
            f"Missing at least: faiss.index, bm25.json, chunks.jsonl"
        )

    # Load chunks + ids so runtime can map idx -> text
    chunks_path = use_dir / "chunks.jsonl"
    chunks = _load_chunks_jsonl(chunks_path)
    chunk_ids = [c.get("chunk_id", "") for c in chunks]

    # Load BM25
    bm25 = load_bm25(str(use_dir / "bm25.json"))

    # Load FAISS
    faiss_index = faiss.read_index(str(use_dir / "faiss.index"))

    return {
        "character_id": character_id,
        "artifact_dir": str(use_dir),
        "chunks": chunks,
        "chunk_ids": chunk_ids,
        "bm25": bm25,
        "faiss": faiss_index,
        "search_bm25": search_bm25,
    }

# backend/app/knowledge/runtime/load_indexes.py

def retrieve(
    indexes,
    query: str,
    k_bm25: int = 8,
    k_faiss: int = 8,
    k_final: int = 8,
):
    bm25 = indexes["bm25"]
    faiss_index = indexes["faiss"]
    chunks = indexes["chunks"]

    from app.knowledge.build.bm25_utils import bm25_search
    from app.knowledge.build.faiss_utils import faiss_search
    from app.knowledge.build.hybrid import hybrid_retrieve
    from app.knowledge.build.embedder import embed_query

    bm25_idxs, _ = bm25_search(bm25, chunks, query, k=k_bm25)
    qv = embed_query(query)
    faiss_idxs, _ = faiss_search(faiss_index, qv, k=k_faiss)

    fused_idxs = hybrid_retrieve(bm25_idxs, faiss_idxs, top_k=k_final)

    retrieved_chunks = [chunks[i] for i in fused_idxs]

    return {
        "chunks": retrieved_chunks,
        "bm25_idxs": bm25_idxs,
        "faiss_idxs": faiss_idxs,
        "fused_idxs": fused_idxs,
    }
