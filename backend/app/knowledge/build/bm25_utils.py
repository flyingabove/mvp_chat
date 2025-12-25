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


# ---------- Build ----------

def build_bm25_index(chunks: list, out_path: Path):
    """
    Build and persist a BM25 index payload.

    Runtime schema invariant:
    {
        "corpus_tokens": List[List[str]],
        "chunks": List[dict]
    }
    """
    corpus_tokens = [
        c["text"].lower().split()
        for c in chunks
    ]

    payload = {
        "corpus_tokens": corpus_tokens,
        "chunks": chunks,   # ✅ MUST be 'chunks', not 'docs'
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)

    # Return BM25 instance for build-time tests
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
