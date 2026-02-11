from pathlib import Path
import os
import tempfile


def default_cache_root() -> Path:
    """Compute a platform-aware default cache root for knowledge artifacts.

    Priority:
    1) KNOWLEDGE_CACHE_DIR env var
    2) KNOWLEDGE_PERSIST_ROOT env var
    3) Preferred deployment path: /data/knowledge_cache when present
    4) Fallback: system temp dir /mvp_chat/knowledge_cache
    """
    env = os.getenv("KNOWLEDGE_CACHE_DIR") or os.getenv("KNOWLEDGE_PERSIST_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    data_path = Path("/data/knowledge_cache")
    if data_path.exists():
        return data_path.resolve()

    tmp_root = Path(tempfile.gettempdir()) / "mvp_chat" / "knowledge_cache"
    return tmp_root.resolve()
