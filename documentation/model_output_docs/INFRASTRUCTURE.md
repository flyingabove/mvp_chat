Infrastructure Reference
========================

> **What this doc is for:** Infrastructure reference (Railway, Docker, env vars, domains, local dev). Edit this doc when deployment, hosting, environment variables, or infrastructure changes.

## Deployment Stack

| Layer | Provider | Notes |
|-------|----------|-------|
| Backend API | Railway | Docker-based, auto-deploys from `prod` (production) and `beta` (staging) branches |
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
| `OPENAI_MODEL` | Model for extractors/translation (honored since 2026-09-24; previously hardcoded) | (unset = `gpt-4o-mini`) |
| `OPENAI_BASE_URL` | Base URL for extractor/translation calls; arena offline mode points it at Ollama | (unset = `https://api.openai.com/v1`) |
| `STORY_MASTER_BASE_URL` | Override story master API base | (unset = OpenAI) |
| `STORY_MASTER_MODEL` | Override story master model | (unset = OPENAI_MODEL) |
| `STORY_MASTER_API_KEY` | Override story master key | (unset = OPENAI_API_KEY) |
| `PLAYER_API_MODEL` | Cloud model for debug player agent | (unset = OPENAI_MODEL) |
| `GRADER_API_MODEL` | Cloud model for debug grader | (unset = OPENAI_MODEL) |
| `KNOWLEDGE_CACHE_DIR` | Where indexes are cached | `/data/knowledge_cache` |
| `MASTER_RESET` | **Nuclear option**: wipe ALL user data + indexes and start fresh | `0` (default, set `1` to wipe) |
| `FORCE_REBUILD_INDEX` | Wipe knowledge cache only (user data preserved) and rebuild indexes | `0` (default) |
| `RUN_TESTS` | Skip build-time tests | `1` (default, set `0` to skip) |
| `DEBUG_MODE` | Enable verbose build/startup logs | `FALSE` (default) |
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID | `123...apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret | `GOCSPX-...` |
| `JWT_SECRET` | HS256 signing key for JWTs (365-day expiry) | 32+ char random hex |
| `DEBUG_TOOLS_ENABLED` + `OPERATOR_TOKEN` | Unlock operator-only debug/authoring routes; fail closed when unset. Not needed for the game arena (local-only). | (unset on beta and prod) |

### Storage path detection (in code)
```python
DATA_DIR = Path("/data") if Path("/data").exists() else Path("./data")
```
Railway has `/data` volume mounted → uses `/data`.
Local dev has no `/data` → uses `./data` (created if missing).

### Data reset env vars (startup behavior)

| Flag | What it deletes | Indexes rebuilt? | User data preserved? |
|------|----------------|------------------|---------------------|
| Neither set | Nothing | Only if missing | Yes |
| `FORCE_REBUILD_INDEX=1` | `/data/knowledge_cache/` only | Yes | **Yes** |
| `MASTER_RESET=1` | **Everything** in `/data/` | Yes (forced) | **No** — SQLite DB, JSONL logs, debug runs all wiped |

`MASTER_RESET` takes precedence over `FORCE_REBUILD_INDEX`. Set `MASTER_RESET=1` to
start completely fresh (e.g., after schema changes or to clear corrupted data).
**Remember to set it back to `0` after deployment** or every redeploy will wipe data.

### What lives in /data (Railway persistent volume)

```
/data/
  storieschat.db          ← SQLite (users, game_sessions tables)
  users/
    {user_id}/
      sessions/
        {session_id}.jsonl ← Conversation logs (append-only)
  knowledge_cache/
    characters/
      {id}/               ← FAISS index, BM25 corpus, embeddings
  debug_runs/
    {run_id}.json          ← Debug player-agent run transcripts
  debug_scores.csv         ← Grader evaluation history
  test_cases.json          ← Saved test cases for debug player agent
```

### JWT token lifetime

JWTs expire after **365 days**. Users should almost never need to re-authenticate.
If `JWT_SECRET` changes between deployments, all existing tokens become invalid
and users must sign in again. Keep `JWT_SECRET` stable across deploys.

---

## URL Scheme

All routes live under a single domain (no subdomain juggling):

| URL | What | Railway service |
|-----|------|-----------------|
| `https://storieschat.ai/` | Prod game UI | Prod (prod branch) |
| `https://storieschat.ai/debug` | Prod debug UI | Prod |
| `https://storieschat.ai/beta/` | Beta game UI | Beta (beta branch) |
| `https://storieschat.ai/beta/debug` | Beta debug UI | Beta |

**How DNS must be configured** (e.g., Cloudflare Workers or similar):
- `storieschat.ai/beta/*` → Railway beta service (`beta-api.storieschat.ai`)
- `storieschat.ai/*` → Railway prod service (`api.storieschat.ai`)

### Cloudflare routing control plane (authoritative behavior)

Cloudflare is the effective traffic control plane for the public domain.
Even when Railway services are healthy, user traffic follows Cloudflare route and
origin decisions first.

Expected behavior:
- Zone: `storieschat.ai` managed in Cloudflare.
- Path-based split at the edge:
  - `/beta/*` must route to beta origin (`beta-api.storieschat.ai`).
  - all other paths must route to prod origin (`api.storieschat.ai`).
- Origin hostnames (`api.storieschat.ai`, `beta-api.storieschat.ai`) are Railway
  service domains and must continue to point at the intended Railway services.

Important operational fact:
- This repository does not contain full Cloudflare zone config as code.
- Cloudflare dashboard/API changes can alter live routing without any git diff in
  this repo.

### How Cloudflare can be abused to silently reroute the same domain

If an AI agent, operator, or compromised token gets Cloudflare write access, they
can keep `storieschat.ai` unchanged for users while sending traffic to different
origins (including a completely separate Railway project/service).

High-risk tamper paths:
- Edge route tampering:
  - Change `/beta/*` route target from `beta-api.storieschat.ai` to another
    hostname (for example, a different Railway project domain).
  - Change catch-all route so prod traffic goes to an unintended origin.
- Worker script tampering:
  - Modify Worker fetch target/origin mapping logic.
  - Add conditional routing (for specific paths, countries, user agents, or query
    params) that hides malicious routing during casual checks.
- DNS record tampering:
  - Repoint `api.storieschat.ai` or `beta-api.storieschat.ai` CNAME records to
    different infrastructure.
  - Add wildcard records that unexpectedly shadow intended hostnames.
- Rule precedence abuse:
  - Insert a more specific route/rule above the intended one so only selected
    paths are hijacked.
- Header-level deception:
  - Rewrite `Host` or upstream headers so requests land in a different backend
    while still appearing under the same public domain.

Potential impact:
- Parallel "shadow" deployment workflow under the same domain.
- Traffic split between intended and unintended Railway projects.
- Hard-to-detect environment drift (especially if only beta or a subset of paths
  are hijacked).

### Required controls to prevent Cloudflare-based hijack

Access control:
- Do not give AI agents broad Cloudflare write tokens.
- Use least-privilege API tokens scoped to specific operations and zones.
- Separate read-only tokens (inspection) from write tokens (changes).
- Require MFA + SSO for human Cloudflare admin accounts.

Change management:
- Treat Cloudflare routing changes like code deploys:
  - ticket/change request,
  - explicit approver,
  - documented rollback plan,
  - post-change validation checks.
- Record every routing/origin change in this repo under infrastructure docs.

Detection and verification:
- Maintain synthetic checks for both paths:
  - `https://storieschat.ai/`
  - `https://storieschat.ai/beta/`
- Verify origin identity, not just status code:
  - include deployment/service identity in health/debug responses,
  - alert on unexpected origin/service IDs.
- Review Cloudflare audit logs for route, Worker, DNS, and token changes.

**Build identity endpoints (2026-09-19 fix)**: `GET /api/version`, `GET /version.json`,
`GET /beta/version.json`, and `GET /api/health` all now return the same
`commit`/`environment`/`content_schema_version` fields from
`backend/app/config/build_info.get_build_info()`. `commit` reads
`RAILWAY_GIT_COMMIT_SHA` (set automatically by Railway on every deploy; falls
back to a local `git rev-parse HEAD` when unset, for local dev). `environment`
reads `RAILWAY_ENVIRONMENT_NAME` (falls back to `"local"`). Before this fix,
`/api/version` had no version field at all and `/version.json`/`/beta/version.json`
returned a hardcoded `"1.0.0"` disconnected from the actual deployed commit —
there was no way to confirm what commit a live deployment was actually serving
without trusting the Railway dashboard (see
`documentation/SIX_STRANGERS_AUDIT_PROPOSAL_2026_09_19.md`, which found this
gap while trying to verify a deployment). `Railway.toml` now also sets
`[deploy] healthcheckPath = "/api/health"` — previously unset.

Incident response (if tamper suspected):
- Rotate Cloudflare API tokens immediately.
- Revert routes/Worker/DNS to known-good config.
- Revalidate origin mapping for prod and beta paths.
- Force redeploy and verify service metadata from live endpoints.

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

Localhost policy:
- Localhost is for debug tooling only (primarily `/beta/debug`).
- The player-facing app login flow is domain-hosted and should not depend on localhost OAuth callbacks.

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
