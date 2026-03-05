"""
Local Debug UI — thin launcher
==============================
Starts the main backend on port 8899 with Ollama as the story master.

Usage (run from any directory):
    python scripts/scorer/story_agent_ui.py

Then open: http://localhost:8899/beta/debug

Requires:
    - Ollama running locally  (ollama serve)
    - Models pulled:          ollama pull llama3.1:8b && ollama pull gemma3:12b
"""
import os
import sys
from pathlib import Path

# Project root is three levels up from this file: scripts/scorer/story_agent_ui.py
_project_root = Path(__file__).resolve().parent.parent.parent

# Change working directory so relative paths (stories/, data/, etc.) resolve correctly
os.chdir(_project_root)

# Make backend importable in both this process and the uvicorn reload subprocess
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
os.environ["PYTHONPATH"] = str(_project_root)

import uvicorn  # noqa: E402 (import after sys.path setup)

# Point story master at local Ollama (overrides OpenAI defaults)
os.environ.setdefault("STORY_MASTER_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("STORY_MASTER_MODEL", "llama3.1:8b")
os.environ.setdefault("STORY_MASTER_API_KEY", "ollama")

if __name__ == "__main__":
    print(f"[launcher] Project root: {_project_root}")
    print("[launcher] Open: http://localhost:8899/beta/debug")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8899, reload=True)
