from pathlib import Path
import os


def default_cache_root() -> Path:
    """Compute a platform-aware default cache root for knowledge artifacts.

    Priority:
    1) KNOWLEDGE_CACHE_DIR env var
    2) KNOWLEDGE_PERSIST_ROOT env var
    3) Platform default:
       - Windows: %LOCALAPPDATA%/mvp_chat/knowledge_cache
       - Others: /data/knowledge_cache
    """
    env = os.getenv("KNOWLEDGE_CACHE_DIR") or os.getenv("KNOWLEDGE_PERSIST_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return (base / "mvp_chat" / "knowledge_cache").resolve()

    return Path("/data/knowledge_cache").resolve()
