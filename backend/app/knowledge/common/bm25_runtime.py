# backend/app/knowledge/common/bm25_runtime.py
from pathlib import Path
import json
from rank_bm25 import BM25Okapi

def load_bm25(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return BM25Okapi(payload["corpus_tokens"])
