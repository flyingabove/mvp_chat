import os
import sys
from pathlib import Path

# Ensure the backend 'app' package is importable during test collection.
repo_root = Path(__file__).resolve().parents[1]
# Add 'backend' so we can `import app....`
backend_dir = repo_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Provide a deterministic default for settings.
os.environ.setdefault("OPENAI_API_KEY", "test-key")


# Some modules in the repo use the legacy import path `backend.app....`.
# In this zip, the importable package is simply `app`. Create aliases so
# tests can import without requiring code changes.
import types
import importlib

try:
    _app_pkg = importlib.import_module("app")
    _backend_mod = types.ModuleType("backend")
    _backend_mod.app = _app_pkg
    sys.modules.setdefault("backend", _backend_mod)
    sys.modules.setdefault("backend.app", _app_pkg)
except Exception:
    # If app isn't importable, individual tests will fail with clearer errors.
    pass


# Optional deps used by knowledge runtime may not be installed in CI.
# Provide a minimal stub so imports succeed; tests that require the real
# dependency use pytest.importorskip(...).
if "faiss" not in sys.modules:
    try:
        import faiss  # noqa: F401
    except Exception:
        _faiss_stub = types.ModuleType("faiss")

        def _missing(*args, **kwargs):
            raise RuntimeError("faiss is not installed in this environment")

        _faiss_stub.read_index = _missing
        _faiss_stub.write_index = _missing
        # Minimal types used in annotations
        class _Index:  # pragma: no cover
            pass

        _faiss_stub.Index = _Index
        sys.modules["faiss"] = _faiss_stub


if "rank_bm25" not in sys.modules:
    try:
        import rank_bm25  # noqa: F401
    except Exception:
        _rb_stub = types.ModuleType("rank_bm25")

        class BM25Okapi:  # pragma: no cover
            def __init__(self, corpus_tokens):
                self.corpus_tokens = corpus_tokens

            def get_scores(self, query_tokens):
                # Extremely simple scoring: count token overlaps
                scores = []
                q = set(query_tokens)
                for doc in self.corpus_tokens:
                    scores.append(float(len(q.intersection(set(doc)))))
                return scores

        _rb_stub.BM25Okapi = BM25Okapi
        sys.modules["rank_bm25"] = _rb_stub
