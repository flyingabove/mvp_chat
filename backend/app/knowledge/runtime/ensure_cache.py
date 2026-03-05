from pathlib import Path
import os
import shutil

from backend.app.knowledge.runtime.cache_paths import default_cache_root


# Repo artifacts inside the image
REPO_DIR = Path(__file__).resolve().parents[1]  # .../knowledge
REPO_CHARS_DIR = REPO_DIR / "characters"

# Cache root on volume (platform-aware default)
CACHE_ROOT = default_cache_root()

ARTIFACT_FILES = ["faiss.index", "embeddings.npy", "bm25.json", "build_info.json"]


def _list_character_dirs() -> list[str]:
    """Auto-discover character directories (sorted by folder prefix)."""
    if not REPO_CHARS_DIR.exists():
        return []
    return sorted(p.name for p in REPO_CHARS_DIR.iterdir() if p.is_dir())


def artifacts_present(d: Path) -> bool:
    return all((d / f).exists() for f in ARTIFACT_FILES)


def ensure_character(character_id: str) -> None:
    """Ensure cache is populated for a single character."""
    repo_char_dir = REPO_CHARS_DIR / character_id
    cache_char_dir = CACHE_ROOT / "characters" / character_id

    # If cache == repo, nothing to do
    if cache_char_dir.resolve() == repo_char_dir.resolve():
        print(f"ensure_cache [{character_id}]: cache dir == repo dir, skipping")
        return

    # If already present in cache, nothing to do
    if artifacts_present(cache_char_dir):
        print(f"ensure_cache [{character_id}]: cache already populated at {cache_char_dir}")
        return

    # Otherwise copy from repo into cache
    if not artifacts_present(repo_char_dir):
        print(f"ensure_cache [{character_id}]: repo artifacts missing at {repo_char_dir}, skipping")
        return

    cache_char_dir.mkdir(parents=True, exist_ok=True)
    for f in ARTIFACT_FILES:
        shutil.copy2(repo_char_dir / f, cache_char_dir / f)

    print(f"ensure_cache [{character_id}]: copied artifacts to {cache_char_dir}")


def main():
    """Ensure cache is populated for ALL discovered characters."""
    chars = _list_character_dirs()
    if not chars:
        print("ensure_cache: no character directories found")
        return

    for cid in chars:
        ensure_character(cid)


if __name__ == "__main__":
    main()
