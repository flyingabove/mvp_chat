Infrastructure Reference
========================

## Deployment Stack

| Layer | Provider | Notes |
|-------|----------|-------|
| Backend API | Railway | Docker-based, auto-deploys on push to `main` branch |
| Frontend (game UI) | Namecheap | Static file hosting; `frontend/index.html` |
| Domain | Namecheap | `storieschat.ai` |
| Persistent storage | Railway Volume | Mounted at `/data` at runtime |
| Container base | `python:3.10-slim` | See `Dockerfile` in project root |

---

## Railway Setup

### Container layout at runtime
```
/srv/
  backend/          ← Python app code
  frontend/         ← Static HTML files (debug UI, etc.)
  tests/            ← Test suite (available to build-time test gate)
  scripts/          ← Utility scripts

/data/              ← Railway persistent volume (mounted at runtime)
  debug_runs/       ← Saved debug run JSON files
  debug_scores.csv  ← Grader evaluation history
  test_cases.json   ← Saved test cases for the debug player agent
  knowledge_cache/  ← FAISS/BM25 index files (rebuilt if missing)
    characters/
      <id>/         ← Per-character bundle (bm25.json, faiss.index, etc.)
```

### Dockerfile key facts
- Working directory: `/srv`
- `PYTHONPATH=/srv` (set in Dockerfile ENV) — makes `import backend.*` work from any script
- Port: `8000` (exposed and used by uvicorn)
- Startup: builds knowledge indexes first, then starts uvicorn
- **All four source directories are copied** — Dockerfile must include:
  ```
  COPY backend/   /srv/backend/
  COPY frontend/  /srv/frontend/    ← REQUIRED for /beta/debug to serve debug.html
  COPY tests/     /srv/tests/
  COPY scripts/   /srv/scripts/
  ```
  If `frontend/` is missing from the COPY list, `GET /beta/debug` will 500 with
  `FileNotFoundError: /srv/frontend/debug.html`.

### Build-time test gate
Tests run during `docker build` (before deploy). A failing test aborts the build
and Railway never deploys the broken image. Override with `RUN_TESTS=0` env var.
```
python -m pytest /srv/tests --disable-warnings --tb=short -ra --continue-on-collection-errors
```

### Environment variables (Railway dashboard)
| Variable | Purpose | Example |
|----------|---------|---------|
| `OPENAI_API_KEY` | Cloud LLM API key | `sk-...` |
| `OPENAI_MODEL` | Default cloud model | `gpt-4o` |
| `STORY_MASTER_BASE_URL` | Override story master API base | (unset = OpenAI) |
| `STORY_MASTER_MODEL` | Override story master model | (unset = OPENAI_MODEL) |
| `STORY_MASTER_API_KEY` | Override story master key | (unset = OPENAI_API_KEY) |
| `PLAYER_API_MODEL` | Cloud model for debug player agent | (unset = OPENAI_MODEL) |
| `GRADER_API_MODEL` | Cloud model for debug grader | (unset = OPENAI_MODEL) |
| `KNOWLEDGE_CACHE_DIR` | Where indexes are cached | `/data/knowledge_cache` |
| `FORCE_REBUILD_INDEX` | Wipe /data and rebuild indexes | `0` (default) |
| `RUN_TESTS` | Skip build-time tests | `1` (default, set `0` to skip) |
| `DEBUG_MODE` | Enable verbose build/startup logs | `FALSE` (default) |
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID | `123...apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret | `GOCSPX-...` |
| `JWT_SECRET` | HS256 signing key for JWTs | 32+ char random hex |

### Storage path detection (in code)
```python
DATA_DIR = Path("/data") if Path("/data").exists() else Path("./data")
```
Railway has `/data` volume mounted → uses `/data`.
Local dev has no `/data` → uses `./data` (created if missing).

---

## URL Scheme

All routes live under a single domain (no subdomain juggling):

| URL | What | Railway service |
|-----|------|-----------------|
| `https://storieschat.ai/` | Prod game UI | Prod (main branch) |
| `https://storieschat.ai/debug` | Prod debug UI | Prod |
| `https://storieschat.ai/beta/` | Beta game UI | Beta (beta branch) |
| `https://storieschat.ai/beta/debug` | Beta debug UI | Beta |

**How DNS must be configured** (e.g., Cloudflare Workers or similar):
- `storieschat.ai/beta/*` → Railway beta service (`beta-api.storieschat.ai`)
- `storieschat.ai/*` → Railway prod service (`api.storieschat.ai`)

**Beta/prod auto-detection (no config needed):**
- `index.html` — if `location.pathname.startsWith('/beta/')` → uses beta API
- `debug.html` — if `location.pathname.startsWith('/beta/')` → WebSocket/API point to beta Railway

**FastAPI routes (present on both prod and beta Railway deployments):**
- `GET /` → `frontend/index.html`
- `GET /beta` or `GET /beta/` → `frontend/index.html`
- `GET /debug` → `frontend/debug.html`
- `GET /beta/debug` → `frontend/debug.html`
- `WS /beta/debug/ws` → debug WebSocket
- `POST /api/chat` etc. → game API

### Frontend-Lean Design Principle

Keep `frontend/index.html` as thin as possible. Heavy lifting, business logic, and
even UI components should live in the backend when feasible.

**Rationale:**
- Every push to Railway deploys new UI instantly — no manual file uploads
- Keeping frontend minimal reduces the blast radius of frontend bugs
- `debug.html` is served by Railway, so it updates on every push with zero extra steps

**Rules:**
- Game logic, data processing, prompt assembly → always backend
- `index.html` handles: story selection, sending messages, displaying responses only
- New UI features (debug panels, admin tools) → `frontend/debug.html` served by Railway

---

## Local Development

The thin launcher (`scripts/scorer/story_agent_ui.py`) starts the full backend on port
8899 with Ollama as the story master:
```
python scripts/scorer/story_agent_ui.py
# → http://localhost:8899/beta/debug
```

The launcher self-relocates to the project root, sets `PYTHONPATH`, and sets Ollama
env vars so it works from any working directory (including home directory).

Local mode vs online mode is detected automatically from the WebSocket host header:
- `localhost` / `127.0.0.1` → local mode → Ollama for player + grader
- any other hostname → online mode → cloud API for player + grader

---

## Known Issues / Lessons

### `frontend/` must be in the Dockerfile COPY list
**Symptom**: `GET /beta/debug` returns 500 with
`FileNotFoundError: /srv/frontend/debug.html` in Railway CI/runtime.

**Root cause**: The Dockerfile `COPY` commands did not include `COPY frontend/ /srv/frontend/`.
The route `debug_ui_page()` in `main.py` reads from `_DEBUG_HTML_PATH` which resolves to
`/srv/frontend/debug.html` — but the file was never deployed.

**Fix**: Added `COPY frontend/ /srv/frontend/` to the Dockerfile after `COPY backend/ /srv/backend/`.

**Lesson for test authors**: Tests that call `/beta/debug` via `TestClient` without mocking
`_DEBUG_HTML_PATH` will fail in any environment where `frontend/debug.html` doesn't exist
at the expected path. Always mock the path in tests:
```python
import backend.app.main as main_module
original = main_module._DEBUG_HTML_PATH
main_module._DEBUG_HTML_PATH = fake_path   # tmp_path / "debug.html"
try:
    client = TestClient(main_module.app)
    resp = client.get("/beta/debug")
finally:
    main_module._DEBUG_HTML_PATH = original
```

### `ModuleNotFoundError: No module named 'backend'` when launching locally
**Symptom**: Running `python scripts/scorer/story_agent_ui.py` from the home directory fails.

**Root cause**: uvicorn spawns a reload subprocess that doesn't inherit `sys.path`.
If the working directory isn't the project root, `backend` package isn't on `sys.path`.

**Fix**: The launcher now calls `os.chdir(project_root)` and sets `os.environ["PYTHONPATH"]`
before invoking uvicorn, so both the main process and the reload subprocess find `backend`.
