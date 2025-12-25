# backend/app/knowledge/build/bm25_utils.py
from pathlib import Path
import json
import re
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi


# ---------- IO ----------

def load_chunks_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"chunks.jsonl not found: {path}")

    chunks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


# ---------- Tokenization ----------

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣']+")

def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# ---------- Build ----------# backend/app/knowledge/build/bm25_utils.py

import json
from pathlib import Path
from rank_bm25 import BM25Okapi


def build_bm25_index(chunks: list, out_path: Path) -> BM25Okapi:
    """
    Build and persist a BM25 index payload.

    Runtime schema invariant (STRICT):
    {
        "corpus_tokens": List[List[str]],
        "chunks": List[dict]
    }

    Returns:
        BM25Okapi instance (build-time only)
    """

    if not chunks:
        raise RuntimeError("BM25 build failed: no chunks provided")

    corpus_tokens = []
    for c in chunks:
        text = c.get("text")
        if not isinstance(text, str):
            raise RuntimeError(
                f"BM25 build failed: chunk {c.get('chunk_id')} has invalid text"
            )
        corpus_tokens.append(text.lower().split())

    payload = {
        "corpus_tokens": corpus_tokens,
        "chunks": chunks,  # ✅ REQUIRED by runtime
    }

    print(f"Writing payload: {payload}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- ATOMIC WRITE (prevents partial/corrupt files) ---
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f)

    tmp.replace(out_path)

    # Build-time BM25 object (DO NOT serialize this)
    return BM25Okapi(corpus_tokens)


# ---------- Load ----------

def load_bm25(path: Path):
    from rank_bm25 import BM25Okapi

    if not path.exists():
        raise FileNotFoundError(f"bm25.json not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if payload.get("schema") != "bm25_v1":
        raise ValueError("Unsupported BM25 schema")

    return BM25Okapi(payload["corpus_tokens"])


# ---------- Search ----------

def bm25_search(bm25, chunks, query: str, k: int):
    q_tokens = tokenize(query)
    scores = bm25.get_scores(q_tokens)

    idxs = sorted(
        range(len(scores)),
        key=lambda i: scores[i],
        reverse=True
    )[:k]

    return idxs, [float(scores[i]) for i in idxs]
