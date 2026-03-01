"""
Local Debug UI — thin launcher
==============================
Starts the main backend on port 8899 with Ollama as the story master.

Usage:
    python scripts/scorer/story_agent_ui.py

Then open: http://localhost:8899/beta/debug

Requires:
    - Ollama running locally  (ollama serve)
    - Models pulled:          ollama pull llama3.1:8b && ollama pull gemma3:12b
"""
import os
import uvicorn

# Point story master at local Ollama (overrides OpenAI defaults)
os.environ.setdefault("STORY_MASTER_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("STORY_MASTER_MODEL", "llama3.1:8b")
os.environ.setdefault("STORY_MASTER_API_KEY", "ollama")

if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8899, reload=True)
