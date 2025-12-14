# backend/app/knowledge/build/bm25_utils.py
from pathlib import Path
import json
import re
from typing import List, Dict, Any

def load_chunks_jsonl(path: Path) -> List[Dict[str, Any]]:
    chunks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))
    return chunks

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣']+")

def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]

def build_bm25_index(chunks: List[Dict[str, Any]], out_path: Path):
    # Lightweight BM25 using rank_bm25
    from rank_bm25 import BM25Okapi

    corpus_tokens = [tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(corpus_tokens)

    # Persist tokens so runtime can reconstruct identical bm25 scores (deterministic)
    payload = {
        "schema": "bm25_v1",
        "corpus_tokens": corpus_tokens,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    return bm25

def load_bm25(path: Path):
    from rank_bm25 import BM25Okapi
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return BM25Okapi(payload["corpus_tokens"])

def bm25_search(bm25, chunks, query: str, k: int):
    q_tokens = tokenize(query)
    scores = bm25.get_scores(q_tokens)
    # top-k indices
    idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return idxs, [float(scores[i]) for i in idxs]
