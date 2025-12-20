from pathlib import Path
import os
import shutil


CHARACTER_ID = "1_iu"

# Repo artifacts inside the image
REPO_DIR = Path(__file__).resolve().parents[1]  # .../knowledge
REPO_CHAR_DIR = REPO_DIR / "characters" / CHARACTER_ID

# Cache root on volume
CACHE_ROOT = Path(os.getenv("KNOWLEDGE_CACHE_DIR", str(REPO_DIR))).resolve()
CACHE_CHAR_DIR = CACHE_ROOT / "characters" / CHARACTER_ID
print("Files:", [p.name for p in CACHE_CHAR_DIR.iterdir()])

ARTIFACT_FILES = ["faiss.index", "embeddings.npy", "bm25.json", "build_info.json"]

def artifacts_present(d: Path) -> bool:
    return all((d / f).exists() for f in ARTIFACT_FILES)

def main():
    # If cache == repo, nothing to do
    if CACHE_CHAR_DIR.resolve() == REPO_CHAR_DIR.resolve():
        print("ensure_cache: cache dir == repo dir, skipping")
        return

    # If already present in cache, nothing to do
    if artifacts_present(CACHE_CHAR_DIR):
        print(f"ensure_cache: cache already populated at {CACHE_CHAR_DIR}")
        return

    # Otherwise copy from repo into cache
    if not artifacts_present(REPO_CHAR_DIR):
        raise RuntimeError(
            f"ensure_cache: repo artifacts missing at {REPO_CHAR_DIR} "
            f"(expected {ARTIFACT_FILES})"
        )

    CACHE_CHAR_DIR.mkdir(parents=True, exist_ok=True)
    for f in ARTIFACT_FILES:
        shutil.copy2(REPO_CHAR_DIR / f, CACHE_CHAR_DIR / f)

    print(f"ensure_cache: copied artifacts to {CACHE_CHAR_DIR}")

if __name__ == "__main__":
    main()
