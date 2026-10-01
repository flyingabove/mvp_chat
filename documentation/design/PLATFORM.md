# Platform: infrastructure, auth, UI, playback tests, Python style

> This file merges several design documents (each keeps its own section, with its original status notes). Open work is in [../backlog/](../backlog/).

Infrastructure Reference
========================

> **What this doc is for:** Infrastructure reference (Railway, Docker, env vars, domains, local dev). Edit this doc when deployment, hosting, environment variables, or infrastructure changes.

### Deployment Stack

| Layer | Provider | Notes |
|-------|----------|-------|
| Backend API | Railway | Docker-based, auto-deploys from `prod` (production) and `beta` (staging) branches |
| Frontend (game UI) | Namecheap | Static file hosting; `frontend/index.html` |
| Domain | Namecheap | `storieschat.ai` |
| Persistent storage | Railway Volume | Mounted at `/data` at runtime |
| Container base | `python:3.10-slim` | See `Dockerfile` in project root |

---

### Railway Setup

#### Container layout at runtime
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

#### Dockerfile key facts
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

#### Build-time test gate
Tests run during `docker build` (before deploy). A failing test aborts the build
and Railway never deploys the broken image. Override with `RUN_TESTS=0` env var.
The gate is unit tests only and makes **no LLM API calls** (owner rule 2026-09-24):
```
OPENAI_API_KEY= TYPESAFE_API_KEY= LANGSMITH_API_KEY= TESTS_BLOCK_LLM_NETWORK=1 python -m pytest /srv/tests -m "not integration" --disable-warnings --tb=short -ra --continue-on-collection-errors
```
Build arg `RUN_LIVE_LLM_TESTS=1` (with `OPENAI_API_KEY`) opts into also running the
`@pytest.mark.integration` tests against real APIs. The runtime key is a Railway
service variable and is never baked into the image.

#### Environment variables (Railway dashboard)
| Variable | Purpose | Example |
|----------|---------|---------|
| `LLM_PROVIDER` | Which LLM the whole game uses: `gemini` \| `openai` \| `ollama` (`backend/app/llm/chat.py`, single `get_chat()` / `resolve_chat_config()`; default switched from GPT to Gemini free tier 2026-09-30) | (unset = `gemini`) |
| `LLM_MODEL` | Override the provider's default model | (unset = `gemini-3.8-flash` / `gpt-4o-mini` / `llama3.1:8b`) |
| `GEMINI_API_KEY` | Google AI Studio key (Gemini via its OpenAI-compatible endpoint). If missing while provider=gemini, falls back to openai with a warning | `AQ...` |
| `OLLAMA_BASE_URL` | Ollama endpoint when `LLM_PROVIDER=ollama` | (unset = `http://127.0.0.1:11434/v1`) |
| `OPENAI_API_KEY` | OpenAI key (used when provider=openai or as the Gemini fallback). Legacy: `settings.OPENAI_API_KEY/BASE_URL/MODEL` now hold the ACTIVE provider's values | `sk-...` |
| `OPENAI_MODEL` | Explicit override of the extractor/translation model (wins over the provider default) | (unset = provider default) |
| `OPENAI_BASE_URL` | Base URL for extractor/translation calls; arena offline mode points it at Ollama | (unset = `https://api.openai.com/v1`) |
| `STORY_MASTER_BASE_URL` | Override story master API base | (unset = active provider) |
| `STORY_MASTER_MODEL` | Override story master model | (unset = OPENAI_MODEL) |
| `STORY_MASTER_API_KEY` | Override story master key | (unset = active provider key) |
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
| Operator token in the debug UI | `frontend/debug.html` sends `X-Operator-Token` (REST) and `?operator_token=` (WebSocket) from `localStorage.storieschat_operator_token`; a 401/403 or malformed `/status` shows a banner with a token field and Retry instead of crashing. Helpers are unit-tested in `tests/frontend/debug_operator.test.cjs`. | (entered in the page) |

#### Storage path detection (in code)
```python
DATA_DIR = Path("/data") if Path("/data").exists() else Path("./data")
```
Railway has `/data` volume mounted → uses `/data`.
Local dev has no `/data` → uses `./data` (created if missing).

#### Data reset env vars (startup behavior)

| Flag | What it deletes | Indexes rebuilt? | User data preserved? |
|------|----------------|------------------|---------------------|
| Neither set | Nothing | Only if missing | Yes |
| `FORCE_REBUILD_INDEX=1` | `/data/knowledge_cache/` only | Yes | **Yes** |
| `MASTER_RESET=1` | **Everything** in `/data/` | Yes (forced) | **No** — SQLite DB, JSONL logs, debug runs all wiped |

`MASTER_RESET` takes precedence over `FORCE_REBUILD_INDEX`. Set `MASTER_RESET=1` to
start completely fresh (e.g., after schema changes or to clear corrupted data).
**Remember to set it back to `0` after deployment** or every redeploy will wipe data.

#### What lives in /data (Railway persistent volume)

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

#### JWT token lifetime

JWTs expire after **365 days**. Users should almost never need to re-authenticate.
If `JWT_SECRET` changes between deployments, all existing tokens become invalid
and users must sign in again. Keep `JWT_SECRET` stable across deploys.

---

### URL Scheme

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

#### Cloudflare routing control plane (authoritative behavior)

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

#### How Cloudflare can be abused to silently reroute the same domain

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

#### Required controls to prevent Cloudflare-based hijack

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
`SIX_STRANGERS_AUDIT_PROPOSAL_2026_09_19.md (removed; see git history)`, which found this
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

#### Frontend-Lean Design Principle

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

### Local Development

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

### Known Issues / Lessons

#### `frontend/` must be in the Dockerfile COPY list
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

#### `ModuleNotFoundError: No module named 'backend'` when launching locally
**Symptom**: Running `python scripts/scorer/story_agent_ui.py` from the home directory fails.

**Root cause**: uvicorn spawns a reload subprocess that doesn't inherit `sys.path`.
If the working directory isn't the project root, `backend` package isn't on `sys.path`.

**Fix**: The launcher now calls `os.chdir(project_root)` and sets `os.environ["PYTHONPATH"]`
before invoking uvicorn, so both the main process and the reload subprocess find `backend`.

---

## Auth + Per-User Persistence Design

> **What this doc is for:** Design of authentication (Google OAuth) and per-user data persistence. Edit this doc when auth flow, session storage, or user data persistence changes.

### Overview

StoriesChat uses Google OAuth 2.0 for authentication and Railway's `/data` persistent volume for
per-user game state storage. The architecture supports **browse freely, login to play**: the home
screen and game catalog are public; clicking "Play" triggers the login flow.

Localhost is **debugger-only** in this project. App login and OAuth callbacks are expected on hosted
domains (prod/beta), not localhost.

---

### Architecture

```
Browser
  ├── Home screen (no auth needed)        → GET /api/stories (public)
  ├── Click Play → JWT missing?
  │     ├── Shows login modal
  │     │     → "Continue with Google" → OAuth flow → JWT in localStorage
  │     └── "Continue as Guest" → generates guest device UUID
  │           → Stored in localStorage + cookie (1-year expiry)
  ├── Chat (authenticated)               → POST /api/chat + Authorization: Bearer <jwt>
  └── Chat (guest)                       → POST /api/chat + X-Guest-Id: <uuid>

Backend
  ├── Identity resolution: JWT sub > "guest:<X-Guest-Id>" > "anon"
  ├── SQLite (/data/storieschat.db)       → users + game_sessions tables
  ├── JSONL files (/data/users/{uid}/sessions/{sid}.jsonl) → raw conversation log
  └── In-memory SESSIONS cache           → fast per-turn access, loaded from SQLite on cache miss
```

---

### Auth Flow

#### Login
1. User clicks "Play" on a game card
2. `startGame()` checks for JWT in localStorage
3. If no JWT: shows login modal with "Continue with Google" button
4. Button redirects to `GET /auth/google/login`
5. Backend builds Google OAuth URL and redirects browser to Google
6. User consents on Google's consent screen
7. Google redirects to `GET /auth/google/callback?code=...&state=...`
8. Backend exchanges code for access token, fetches user info, upserts user in SQLite
9. Backend creates 30-day JWT and redirects to `/?token=<jwt>` (or `/beta/?token=<jwt>`)
10. Frontend extracts token from URL query param, stores in localStorage, cleans URL

#### Per-request auth
- Every API call that needs auth includes `Authorization: Bearer <jwt>` header
- `get_current_user` dependency verifies JWT signature and returns payload
- `get_optional_user` dependency returns `None` if no JWT (used in `/api/chat`)

#### Guest users (persistent anonymous)
- No JWT → frontend generates a **guest device ID** (UUID), stored in localStorage + cookie (1-year expiry)
- Sent as `X-Guest-Id` header on all API requests when no JWT is present
- Backend maps to `user_id = "guest:<uuid>"` — full DB persistence (same as authenticated users)
- Guest sessions survive server restarts and appear in "My Games"
- `get_current_user_or_guest` dependency: accepts JWT OR X-Guest-Id header (validates UUID format)
- Guest ID validated by regex: must be valid UUID hex (32-36 chars), lowercased. Invalid IDs → 401.
- Privacy: each guest device ID is unique, data isolated by `WHERE user_id = ?`

#### Guest session lifecycle

**TTL & cleanup:**
- Guest sessions expire after **24 hours** of inactivity (`GUEST_TTL_SECONDS = 86400`)
- Background async task `_guest_cleanup_loop()` runs hourly in `main.py` lifespan
- Deletes DB rows WHERE `user_id LIKE 'guest:%' AND last_played < cutoff`
- Also deletes JSONL conversation log files and evicts from in-memory SESSIONS cache
- Frontend warns at game start: *"Guest mode: your progress will be deleted after 24 hours unless you sign in with Google."*

**Guest → Google transfer:**
- On OAuth callback (`/auth/google/callback`), backend reads `storieschat_guest_id` cookie
- If valid UUID, calls `SessionRepo.transfer_sessions(from_guest, to_google_user)`
- Transfer updates `user_id` in all `game_sessions` DB rows and moves JSONL files
- In-memory SESSIONS cache updated to reflect new ownership
- Guest cookie deleted after successful transfer (`resp.delete_cookie(...)`)
- Idempotent: if guest has no sessions, transfer is a no-op (returns 0)

**Filesystem safety:**
- `_safe_dir_name(user_id)` replaces `:` with `_` for Windows compatibility
- All JSONL paths use sanitized user_id: `/data/users/guest_<uuid>/sessions/{sid}.jsonl`

#### Fully anonymous users
- No JWT AND no X-Guest-Id → `user_id = "anon"` in `chat_handler`
- In-memory only, no persistence, state lost on server restart
- This path is only hit if cookies + localStorage are both cleared

---

### Database Schema

**File:** `/data/storieschat.db`

```sql
CREATE TABLE users (
    id          TEXT PRIMARY KEY,     -- Google sub (unique, stable)
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    avatar_url  TEXT,
    created_at  INTEGER NOT NULL,
    last_login  INTEGER NOT NULL
);

CREATE TABLE game_sessions (
    id           TEXT PRIMARY KEY,    -- client-generated UUID
    user_id      TEXT NOT NULL REFERENCES users(id),
    story_id     TEXT NOT NULL,
    story_title  TEXT,
    player_name  TEXT,
    gender       TEXT,
    status       TEXT DEFAULT 'active',
    created_at   INTEGER NOT NULL,
    last_played  INTEGER NOT NULL,    -- Unix seconds
    turns        INTEGER DEFAULT 0,
    last_message TEXT,                -- ≤120 chars for My Games list
    state_json   TEXT,                -- JSON: safe primitive fields only
    flags_json   TEXT                 -- JSON: debug_mode, chinese_mode, etc.
);

CREATE INDEX idx_sessions_user ON game_sessions(user_id, last_played DESC);
```

---

### JSONL Raw Logs

**Path:** `/data/users/{user_id}/sessions/{session_id}.jsonl`

Each line is a single JSON object:
```json
{"turn": 1, "role": "user", "content": "Hello", "ts": 1700000000}
{"turn": 1, "role": "assistant", "content": "Hi there!", "ts": 1700000000}
```

- Append-only (no rewrites)
- One file per session (no cross-session reads)
- Full history stored; LLM only sees last `MEMORY_TURNS=8` entries (stored in `state_json.log`)
- Paginated loading: frontend loads 20 most recent entries; "Load earlier messages" fetches more

---

### State Serialization

`state_json` in `game_sessions` stores only safely serializable primitive fields:

```json
{
  "story": "jennie_murder_mini",
  "gender": "M",
  "player_name": "Alex",
  "minute": 45,
  "location": "Interview Room A",
  "location_id": "room_a",
  "emotion": "wary",
  "relationship": 1,
  "turns": 12,
  "over": false,
  "instance": 1,
  "user_formal_name": "Alex",
  "user_display_name": "Alex",
  "log": [...]
}
```

**Complex objects with persisted runtime snapshots:**
- `character_graph` — authored base graph is loaded from `StoryDefinition.relationships`, then runtime edge state (trust/fear/affection/suspicion/jealousy, narrative/history fields, and dynamically created edges) is restored from `state_json.character_graph`.
- `session_chunk_store` — dialogue-extracted session facts are persisted in `state_json.session_chunks` and restored into `SessionChunkStore` so BM25 session-memory retrieval survives restart/resume.
- `character_locations` — runtime character-to-location assignments are restored from `state_json.character_locations` (overrides story start defaults).
- `last_turn_*` extractor context — `last_turn_user_msg`, `last_turn_assistant_reply`, and `last_turn_retrieved_chunks` are restored for continuity of single-call extraction behavior.

**Objects still rebuilt from story config on resume:**
- `world_runtime` — rebuilt by `WorldLoader`.
- `story_cfg` — rebuilt by `_canonicalize_story_cfg()`.
- `epistemic_state` seed structures — re-seeded by `_seed_epistemic_from_story()`.
- `transient_entries` — re-seeded by `_seed_noncanonical_story_details_to_transient()`.

**Session restore** (`_try_load_session_from_db`): Uses `SessionRepo._get()` (synchronous) to load from SQLite on in-memory cache miss. Safe to call from async handlers — SQLite indexed lookups are sub-millisecond. Failures are logged via `logger.exception()`, never silently swallowed.

---

### API Endpoints

#### Auth
| Method | Path | Auth required | Description |
|--------|------|---------------|-------------|
| GET | `/auth/google/login` | No | Redirect to Google OAuth |
| GET | `/auth/google/callback` | No | Handle OAuth callback, issue JWT |
| GET | `/api/auth/me` | Yes | Return current user info |
| POST | `/api/auth/logout` | No | Stateless (client clears JWT) |

#### User Sessions
| Method | Path | Auth required | Description |
|--------|------|---------------|-------------|
| GET | `/api/user/sessions` | JWT or X-Guest-Id | List user's game sessions (newest first) |
| GET | `/api/user/sessions/{id}/history` | JWT or X-Guest-Id | Paginated conversation history |
| DELETE | `/api/user/sessions/{id}` | JWT or X-Guest-Id | Delete session + JSONL file |

#### Resume behavior across entry points
- `My Games` always reads from `GET /api/user/sessions` (JWT or guest ID).
- Home page "Continue Playing" and game-detail "Resume Game" now use a merged local+server session cache; server sessions are fetched from `/api/user/sessions`, merged into local storage, and used by both entry points.
- Result: users can resume the same in-progress game from either Home or My Games after re-login or server restart.

---

### Security Guarantees

1. **No data bleed**: Every DB query uses `WHERE user_id = ?` with JWT's `sub` claim
2. **Session ownership (DB)**: `SessionRepo._get()` returns `None` if `user_id` doesn't match
3. **Session ownership (cache)**: `get_session()` verifies `user_id` on in-memory cache hits — on mismatch, creates a fresh session (defense-in-depth, prevents cross-user data leaks even if session UUIDs collide)
4. **JSONL isolation**: Path uses `user_id` from JWT, never from request body
5. **Anonymous fallback**: `user_id = "anon"` → in-memory only, no DB writes
6. **JWT signed**: HS256, `JWT_SECRET` from Railway env var, 30-day expiry

---

### Concurrency

- SQLite handles 20+ concurrent users trivially (WAL mode, connection-per-operation)
- In-memory SESSIONS cache: per-session, no shared mutable state between users
- JSONL writes: append-only, one file per session, no contention
- Uvicorn single worker is sufficient for 20-50 users; bump to 2 workers if needed

---

### Google Cloud Console Setup

1. Go to https://console.cloud.google.com/
2. Create a project (or use existing)
3. Navigate to **APIs & Services → Credentials**
4. Click **Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Authorized redirect URIs — add ALL:
   - `https://storieschat.ai/auth/google/callback`
   - `https://beta-api.storieschat.ai/auth/google/callback`
  - Do not add localhost app callback URIs for normal operation.
7. Copy **Client ID** and **Client Secret**
8. In Railway dashboard for **both prod and beta** services, add env vars:
   ```
   GOOGLE_CLIENT_ID=<your client id>
   GOOGLE_CLIENT_SECRET=<your client secret>
   JWT_SECRET=<run: python -c "import secrets; print(secrets.token_hex(32))">
   ```
9. Optionally: **APIs & Services → OAuth consent screen** → set app name "StoriesChat"

#### Localhost policy (important)

- `localhost:8899` is for the debug/scorer developer UI (`/beta/debug`) only.
- The player-facing app and Google sign-in should run on hosted domains.
- If a localhost OAuth callback is temporarily added for isolated troubleshooting, treat it as temporary and remove it afterward.

#### Local credential loading (.env.test)

- Google + JWT secrets live in `.env.test` at project root (gitignored).
- `backend/app/config/credentials.py` exposes `get_google_client_id()`, `get_google_client_secret()`, `get_jwt_secret()` (alongside `get_openai_api_key()`).
- Each helper triggers `_load_env_test_once()` only if the live env var is missing — so Railway/CI env vars always take priority.
- `settings.py` consumes those helpers at import time; `google_oauth.py` and `jwt_utils.py` see fully resolved values.
- If `GOOGLE_CLIENT_ID` is empty on boot, the OAuth URL Google receives is missing `client_id`, and login silently fails with a 400 from Google. Always confirm via `GET /api/auth/debug-config`.

#### Guest bypass UI ("Play as Guest" pill)

- Frontend exposes `✦ Play as Guest` on the home top-bar (`#home-guest-pill`).
- Storage flag: `localStorage.storieschat_skip_login = "1"` (set by the pill or the modal's "Continue as Guest").
- When set, `startGame()` skips the login modal entirely, mints a guest UUID, and runs the chat call with `X-Guest-Id`.
- Cleared on explicit sign-in (profile button or `?token=` callback) so JWT takes over.

---

### New Files

| File | Purpose |
|------|---------|
| `backend/app/auth/__init__.py` | Package init |
| `backend/app/auth/jwt_utils.py` | JWT sign (30-day expiry) + verify |
| `backend/app/auth/google_oauth.py` | Google OAuth URL builder + token/userinfo exchange |
| `backend/app/auth/dependencies.py` | FastAPI `Depends(get_current_user)` + `Depends(get_optional_user)` |
| `backend/app/db/__init__.py` | Package init |
| `backend/app/db/database.py` | SQLite init, schema migration, DATA_DIR detection |
| `backend/app/db/repos.py` | `UserRepo`, `SessionRepo`, `ConversationRepo` |
| `backend/app/api/auth.py` | `/auth/google/login`, `/auth/google/callback`, `/api/auth/me`, `/api/auth/logout` |
| `backend/app/api/user_sessions.py` | `GET/DELETE /api/user/sessions`, `GET /api/user/sessions/{id}/history` |

---

## StoriesChat UI Redesign — Design Spec (2026)

> **What this doc is for:** Full design spec for the 2026 Netflix+Character.AI UI redesign. Edit this doc when UI screens, components, CSS system, or navigation changes.

### Context

The original terminal-style `frontend/index.html` was replaced with a modern
dark SPA that blends Netflix-style game discovery with Character.AI-style chat.
This document is the canonical design spec.

The user-provided screenshots that drove this design:
1. **Character.AI profile page** — dark bg, rounded avatar, follower/interaction counts, icon tab row, empty state
2. **Character.AI Chats list (compact)** — dark bg, square-rounded thumbnails, game title, bottom Create sheet
3. **Character.AI Chats list (expanded)** — full list: Zeno Re9, Sukuna, Fushiguro, Gojo, Bruce Wayne, Percy Jackson RP, Elon Musk, Yor Forger
4. **Character.AI chat screen** — character name + "c.ai" badge, chat bubbles, right panel: Voice/History/Customize/Pinned/Persona/Style
5. **Character.AI search** — character cards, trending panel
6. **Netflix desktop** — hero banner, "Today's Top Picks", horizontal card rows with TOP 10 and Recently Added badges
7. **Netflix mobile home** — "For [User]" header, horizontal rows, "Gems for You", "Mobile Games"
8. **Netflix mobile rows** — genre rows: "Japanese Movies & TV", "Boredom Busters", "We Think You'll Love These"

**Design synthesis:**
- Home page = Netflix dark rows, but card styling is Character.AI (square, rounded, with emoji/image)
- Chat = Character.AI exact clone (bubbles, avatar, name badge, 3-dot menu)
- My Games = Character.AI Chats list (session thumbnail + title + last time)
- Create = Character.AI Create flow, simplified for games
- Profile = Character.AI profile adapted for game stats
- Color palette = Netflix dark (#141414) — NOT the white Character.AI palette

---

### Screen Inventory

#### 1. Home Screen (`#screen-home`)
**Purpose:** Game discovery — feels like Netflix

**Layout:**
- Top bar: "StoriesChat" logo (red) + search icon + profile icon
- Hero banner: Featured game with gradient overlay, genre badge, title, description, "Play" + "More Info" buttons
- Game rows (horizontal scroll):
  - "Featured Games" (wide 16:9 cards)
  - Per-genre rows (e.g., "Murder Mystery", "Romance")
  - "All Games"
- Each card: 130px wide, 2:3 aspect image, genre badge overlay, title below

**API calls:**
- `GET /api/stories` → renders all rows
- Card click → Game Detail Modal

---

#### 2. My Games Screen (`#screen-games`)
**Purpose:** Currently active/recent sessions — feels like Character.AI Chats

**Layout:**
- Top bar: "My Games" + "+" button (→ Home)
- List of sessions from localStorage (`storieschat_sessions`)
- Each row: 56px square-rounded thumbnail (emoji), game title, last message snippet, time ago
- Empty state: "No games yet" with "Explore Games" button

**Data source:** localStorage only — no backend call needed for the list

---

#### 3. Chat Screen (`#screen-chat`)
**Purpose:** In-game conversation — Character.AI exact clone (no tab bar)

**Layout:**
- Top bar: back arrow, centered character name + genre sub-label, 3-dot menu
- Character header (shown at session start): 80px avatar, game title, genre badge
- Messages area (scrollable):
  - NPC: left-aligned bubble (dark #1e1e1e), small emoji avatar left
  - Player: right-aligned bubble (red #e50914)
  - System: centered muted text
- Typing indicator: animated 3 dots (visible while awaiting response)
- Input area: rounded textarea + red send button (fixed bottom)

**3-dot menu items:**
- 🗺 World Map → shows `#map-modal`
- 🔬 Debug Info → toggles debug mode, sends `[DEBUG]` to backend
- 💡 Truth Mode → toggles, sends `[TRUTH]` to backend
- 🀄 Chinese Mode → toggles, sends `[CHINESE]` to backend
- 🧠 Epistemic State → toggles, sends `[EPISTEMICSTATE]` to backend
- 🚪 Exit Game → confirm → returns to Home

---

#### 4. Create Screen (`#screen-create`)
**Purpose:** Create a new game draft — simplified Character.AI Create flow

**Fields:**
- Game Title (text input, max 100)
- Genre (select: Murder Mystery / Romance / Horror / Fantasy / Comedy / Sci-Fi / Thriller)
- Short Description (textarea, max 500)

**API call:** `POST /api/stories/draft` → `{ title, genre, description }`

**On success:** Shows green success banner. Game appears in `/api/stories` list.

---

#### 5. Profile Screen (`#screen-profile`)
**Purpose:** Player identity + stats + settings — Character.AI profile adapted

**Sections:**
- Avatar (emoji), username, handle
- Stats: Games played / Wins / Turns (from localStorage `storieschat_stats`)
- Settings: Dark Mode (always on, decorative toggle), Notifications (coming soon)
- About: App version (from `/version.json`), link to Debug Console

---

### CSS Design System

#### Color Variables
```css
--bg:           #141414;   /* Netflix background */
--surface:      #1c1c1c;   /* Cards, modals */
--card:         #222222;   /* Input backgrounds */
--card-hover:   #2a2a2a;
--border:       #2e2e2e;
--red:          #e50914;   /* Netflix red — primary accent */
--red-dark:     #b2070f;   /* Hover/pressed state */
--text:         #ffffff;
--text-sub:     #aaaaaa;
--text-muted:   #666666;
--bubble-user:  #e50914;   /* Player chat bubble */
--bubble-npc:   #1e1e1e;   /* NPC chat bubble */
```

#### Typography
- Font: System UI sans-serif (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`)
- NO monospace — this is the key break from the old terminal UI
- Base: 15px / 1.5 line-height

#### Layout Constants
```css
--tab-h:        60px;    /* Bottom tab bar height */
--top-h:        56px;    /* Top bar height */
--radius:       12px;    /* Standard card radius */
--radius-sm:    8px;     /* Small card radius */
--radius-bubble:18px;    /* Chat bubble radius */
```

---

### Component Library

#### GameCard
```
.game-card (130px wide, 2:3 image, .wide variant for 16:9)
  .game-card-img (image or emoji fallback, .card-genre-badge overlay)
  .game-card-body (.game-card-title)
```

#### ChatBubble
```
.msg-row.npc → .msg-avatar + .msg-bubble.npc
.msg-row.user → .msg-bubble.user
.msg-row.system → .msg-bubble.system-msg
```

#### TabBar
```
#tab-bar
  .tab-item (data-screen="home|games|create|profile")
    .tab-icon
    span (label)
```
Tab bar is hidden when `#screen-chat` is active.

#### TopBar
```
.top-bar
  .back-btn (← back)
  .logo (StoriesChat wordmark)
  .page-title (centered)
  .top-actions (.icon-btn)
```

---

### localStorage Schema

#### Sessions (`storieschat_sessions`) — Array
```json
[
  {
    "story_id": "jennie_murder_mini",
    "story_title": "The Quiet Agreement",
    "session_id": "uuid-v4",
    "player_name": "Alex",
    "gender": "M",
    "started_at": 1700000000000,
    "last_played": 1700003600000,
    "last_message": "I know you were there that night.",
    "turns": 12
  }
]
```
Max 50 sessions stored. Newest first.

#### Profile (`storieschat_profile`)
```json
{ "name": "Player", "handle": "@player" }
```

#### Stats (`storieschat_stats`)
```json
{ "games": 3, "wins": 1, "turns": 47 }
```

---

### PWA Setup

#### Files
- `frontend/manifest.json` — App name, theme, icons (inline SVG), standalone display
- `frontend/sw.js` — Cache-first for shell, network-first for `/api/*`

#### Backend routes (main.py)
```python
GET /manifest.json        → FileResponse(frontend/manifest.json)
GET /beta/manifest.json   → same
GET /sw.js                → FileResponse(frontend/sw.js)
GET /beta/sw.js           → same
```

#### Install trigger
- HTML `<link rel="manifest" href="manifest.json" />`
- `<meta name="theme-color" content="#141414" />`
- Apple PWA meta tags
- `navigator.serviceWorker.register("sw.js")` in JS boot

---

### Story JSON New Fields

Fields added to each story JSON to support the new UI:

```json
{
  "description": "Short 1-3 sentence teaser for the game card and modal.",
  "genre": "Murder Mystery",
  "thumbnail_url": null,
  "featured": true
}
```

- `description`: Shown on game cards and detail modal. Max ~200 chars displayed.
- `genre`: Used for row grouping on home screen and badge overlays.
- `thumbnail_url`: Optional path to a card image. If null, falls back to emoji icon.
- `featured`: If true, appears in the "Featured Games" row and can be the hero.

The `/api/stories` endpoint returns all four fields.

---

### Backend Changes

#### `backend/app/api/stories.py`
- `list_stories()` now returns `genre`, `description`, `thumbnail_url`, `featured` per story
- New `POST /api/stories/draft` endpoint:
  - Accepts `{ title, genre, description }`
  - Generates slug-based ID: `draft_{slug}_{6-char-hex}`
  - Saves stub JSON to `backend/app/stories/`
  - Returns `{ id, title }`

#### `backend/app/main.py`
- Imports `FileResponse`
- Adds `_MANIFEST_PATH` and `_SW_PATH` path constants
- Adds 4 new routes for PWA assets (`/manifest.json`, `/beta/manifest.json`, `/sw.js`, `/beta/sw.js`)

---

### Scalability Notes

The UI is fully stateless on the server side:
- All session/profile/stats data lives in localStorage
- The backend only stores active LLM state (in-memory, keyed by session UUID)
- 100+ concurrent users = 100+ in-memory sessions, no coordination needed
- Story drafts are written to disk — at scale these should move to a database, but for MVP the file-based approach is fine
- The PWA service worker caches the shell — reduces Railway egress at scale

---

### Preserved Legacy Functionality

All original bracket commands still work, now via the 3-dot menu or by typing them directly in the chat input:

| Command | Trigger in new UI |
|---------|-------------------|
| `[DEBUG]` | 🔬 Debug Info menu item |
| `[TRUTH]` | 💡 Truth Mode menu item |
| `[CHINESE]` | 🀄 Chinese Mode menu item |
| `[EPISTEMICSTATE]` | 🧠 Epistemic State menu item |
| `[MAP]` | 🗺 World Map menu item |
| `[EXIT]` | 🚪 Exit Game menu item |

The integration playback feature is now accessible only via the `/debug` console URL (debug.html).

### PWA delivery and mobile presentation (2026-09-24)

The FastAPI-served shell now references SHA-256 content-addressed JS/CSS URLs.
HTML, fixed-name legacy assets, worker scripts, manifests and version responses
use `Cache-Control: no-store`. The service worker only caches hashed JS/CSS;
activation removes old StoriesChat caches before claiming clients. Its served
bytes include a fingerprint of the HTML, styles, scripts and manifest, so every
shell deployment changes the worker. Registration bypasses HTTP caches, and the
app checks the shell revision on foreground return and every minute. Automatic
revision checks defer during an active chat request, then reload even if a draft
is present; they preserve login and saved games. First installation does not
cause a competing reload. The user-triggered Refresh Cache action clears worker
registrations, Cache Storage, local/session storage, accessible cookies and
enumerable IndexedDB databases, then reloads a cache-busted document. It signs
the player out and removes locally saved state by request.

Beta manifests use `/beta/` for start URL, scope and identity; installing from
beta must not send the player to production `/`. Existing production installs
still require an explicitly authorized production deployment to receive these
changes. Physical iOS Home Screen installation remains distinct from WebKit
emulation and should not be claimed as tested from desktop tooling.

The scene uses a stable game-cover avatar and smaller named character portrait
bubbles within each reply; narration stays in reading order. The header and
resumed games retain the cover too. Slow/Normal/Fast use 10/4/(10÷3.5) milliseconds
per character, with Normal as default; this controls text reveal, not model
inference latency. The unused upload-photo control is removed. My Games rows
fill the available width, distinguish taps from horizontal drags, and reveal an
accessible X delete button. The bottom Refresh Cache button shares tab styling.
Standalone viewport sizing uses the full inner height except when the keyboard
is open.

The opening beneath the Six Strangers map is now a short arrival scene. Each
AI speaker has a named portrait bubble that opens a full-size portrait; narrator
passages carry a separate label, and human messages are right-aligned with a
"You" label. The structured dialogue schema excludes the player as an AI
speaker and drops any invalid player dialogue segment returned by a provider.
An unknown speaker who explicitly introduces themselves with the full name of
one active housemate receives that housemate's portrait; concealed voices stay
unknown.

Validation scripts: `scripts/verify_mobile_pwa_browser.py` drives real desktop
Chromium, iPhone WebKit and a simulated standalone flag; `scripts/verify_pwa_upgrade.py`
installs the actual legacy worker from commit 37cdcfe, seeds stale script data,
then verifies replacement and old-cache deletion in Chromium and WebKit.

---

## Integration Test Playback Design (UI + Harness)

> **What this doc is for:** Design of the integration test playback harness (UI + automated runner). Edit this doc when the playback system architecture or UI changes.

### Purpose
Define a reusable structure for integration scenarios that can run in pytest and playback UI flows.

### Load When
- You add a new integration scenario.
- You convert an integration path into deterministic playback.
- You need scenario metadata/tag standards.

### Canonical Code
- `backend/app/integration_playback/**`
- `tests/backend/app/api/test_prompt_engine.py`
- `tests/backend/app/config/test_epistemic_flags.py`

Goal: All integration tests (chat, extractor-only, cached LLM, live LLM) can be played back in a UI submenu as auto-running dialogues with consistent structure. Tests remain executable via pytest but also expose a uniform, serializable script the UI can consume.

### Core Concepts
- **Scenario registry**: Each integration test registers a `Scenario` object describing metadata, required fixtures (cache vs live API), and a sequence of `Step` objects.
- **Step types (uniform)**:
  - `UserMessage(content)` – what the human sends
  - `SystemAction(name, payload)` – internal actions (state init, travel, time advance)
  - `LLMCall(kind, mode, prompt, cached_response=None)` – renderer/extractor calls; `mode` in {`live`, `cached`}; `cached_response` holds deterministic text when available
  - `Assertion(description, fn_ref)` – validates state after the step
  - `Delay(ms)` – optional pacing for playback
- **Execution engines**:
  - **Pytest runner**: Executes steps with real code paths, running assertions; respects `mode` to decide live vs cached calls.
  - **UI playback**: Reads the scenario, replays messages and responses (uses cached text or stubbed calls), surfaces assertion results and state snapshots in a side panel.

### Data Model (plain Python classes)
```python
class Scenario:
    id: str
    title: str
    description: str
    tags: list[str]  # e.g., ["integration", "live-llm", "extractor-only"]
    requires_api_key: bool
    requires_cache: bool  # needs /data or local cache
    steps: list[Step]

class Step:
    kind: Literal["user", "system", "llm", "assert", "delay"]
    payload: dict  # shape depends on kind

# Helpers for authoring
UserMessage = lambda text: Step(kind="user", payload={"text": text})
SystemAction = lambda name, payload=None: Step(kind="system", payload={"name": name, "payload": payload or {}})
LLMCall = lambda kind, mode, prompt, cached_response=None: Step(kind="llm", payload={"kind": kind, "mode": mode, "prompt": prompt, "cached_response": cached_response})
AssertionStep = lambda description, fn_ref: Step(kind="assert", payload={"description": description, "fn": fn_ref})
Delay = lambda ms=400: Step(kind="delay", payload={"ms": ms})
```

### Registry & Discovery
- A central `integration_scenarios.py` exports `SCENARIOS: dict[str, Scenario]`.
- Each test module registers its scenario in `SCENARIOS` and uses it in pytest via a small adapter fixture `run_scenario(scenario_id)`.
- UI reads the same registry (import or JSON export) to list scenarios.

### How existing tests map to scenarios
- **test_prompt_engine** (canonical path): includes multi-turn API flow checks (time/location movement and scene context) with deterministic mocks.
- **test_location_extractor** (canonical path): movement extraction assertions with live/cached behavior options.
- **test_hybrid** (canonical path): hybrid retrieval assertions and score behavior checks.
- **test_epistemic_flags** (canonical path): layer toggle behavior and gating assertions.
- **knowledge-resolution flow (single-call extractor)**: UserMessage + renderer LLMCall with turn extractor output carrying knowledge updates + Assertions on:
  - belief graph claim upsert (`kr::<speaker>::<chunk_id>`),
  - transient knowledge object existence,
  - 8-turn TTL expiration behavior.

### Playback Engine (UI)
- Menu entry: "Integration Playback" → list scenarios (id, title, tags, live/cached badges, needs API key). Filter by tag.
- On select: show sidebar with description, prereqs, and controls: Play, Pause, Step, Speed (delay ms).
- Renderer:
  - Renders chat transcript; for `llm` steps, uses `cached_response` when present; if `mode=live` and API keys are missing, UI disables play or prompts for key.
  - Shows assertions as checkmarks; if an assertion fails in playback mode, render red badge with message.
  - Shows state diff snapshot if provided by assertion function (optional return value from fn_ref).
- Deterministic mode: default to cached paths if available; allow toggle to "live" when supported.

### Test Runner Adapter (pytest)
- Fixture `scenario_runner` that takes a Scenario and executes steps:
  - `user`: call chat endpoint or extractor input depending on scenario config
  - `system`: perform setup (init state, set env, set character id)
  - `llm`: if `mode="cached"` use provided text; else call real LLM (guarded by api key fixtures)
  - `assert`: call fn_ref(state) and raise on failure
- Each integration test becomes a thin wrapper: `def test_xxx(scenario_runner): scenario_runner("api_play_5_turns")`

### Caching Strategy
- For LLM-dependent scenarios, store `cached_response` text in the scenario definition to ensure offline determinism.
- For extractor-only steps, store parsed JSON output as `cached_response`.
- Provide a script to refresh caches (opt-in) with live calls; not used in CI.

### Storage/Paths
- Registry should live under canonical playback modules (for example `backend/app/integration_playback/**`).
- Cached payloads can be embedded inline in scenario objects or stored under a canonical playback cache path (for example `backend/app/integration_playback/cached/{scenario_id}/step_{n}.json`).

### Implementation Plan (incremental)
1) Add Scenario/Step classes + registry file; add authoring helpers.
2) Refactor one test (api_play_5_turns) to use `scenario_runner`; include cached replies.
3) Add UI stub (menu + list + playback panel) consuming registry; CLI/JSON export if needed for frontend.
4) Migrate remaining integration tests into scenarios; add cached outputs where feasible to avoid live calls.
5) Add cache refresh script and docs on providing API keys when running live.

### CI / Docker Environment Notes

#### OPENAI_API_KEY in CI
The `OPENAI_API_KEY` environment variable **is set** as a Railway build-time secret.
However, Docker `RUN` commands only see build args declared with `ARG`, not runtime
env vars. The Dockerfile must include:

```dockerfile
ARG OPENAI_API_KEY=""
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
```

Without this, build-time `pytest` runs will skip any test guarded by
`require_openai_api_key` even though the key is available in Railway's
environment. Railway passes build args automatically when they match
configured env var names.

#### scripts/ directory in Docker
The Dockerfile must `COPY scripts/ /srv/scripts/` alongside `backend/` and
`tests/`. Tests under `tests/scripts/` import from `scripts.scorer.story_agent_ui`
and will fail with `ModuleNotFoundError` if the `scripts/` tree is not present
in the Docker image.

### Acceptance
- All integration tests run via scenario runner with existing assertions unchanged in spirit.
- UI can list scenarios and auto-play transcripts using cached data.
- Live runs remain possible for scenarios tagged `live-llm` when API key is present.
- Playback model includes extractor-after-render phases (location extraction pre-render and knowledge-resolution extraction post-render).

---

## Python Coding Style Guide

> **What this doc is for:** Python coding standards for this project. Edit this doc when coding conventions or style rules change.

### Purpose
This document defines coding style rules for Python changes in this repository so AI agents and humans produce consistent code.

### Scope
- Backend Python modules under `backend/app/**`
- Python test modules under `tests/**`
- Utility scripts under `scripts/**`

### Naming conventions

#### Functions and methods
- Use snake_case names.
- **RULE: No leading underscore for helper functions or methods.**
- Leading underscores (`_name`) are reserved only for name-mangling or truly private class internals where Python convention demands it.
- Preferred: `apply_knowledge_resolution_updates`
- Avoid: `_apply_knowledge_resolution_updates`
- If a helper is intentionally private to class internals, make it a class method and leave a comment explaining why.

#### Classes
- Use PascalCase.
- **RULE: Scenario and fixture classes must NOT be defined inside test files.** Define them in `backend/app/integration_playback/scenarios/` or equivalent backend modules. Test files are wrappers only.

#### Constants
- Use UPPER_SNAKE_CASE.

### Documentation file naming rule

**RULE: All documentation files under `documentation/` (excluding `human_north_star_docs/` and `auto_update_docs/`) must be named `UPPER_SNAKE_CASE.md`.**

- No `.txt` files. Convert to `.md`.
- No `lowercase_with_underscores.md` prefixed names. Use `UPPER_SNAKE_CASE.md`.
- Archive files prefix with `ARCHIVE_`: e.g., `ARCHIVE_EPISTEMIC_ENGINE_TODO.md`
- The only index file is `documentation/AI_DOC_INDEX_CATALOGUE.md`.

Correct examples:
- `AI_FATAL_MISTAKES.md`
- `AI_LEARNINGS_RUNNING_TESTS.md`
- `ERRORS.md (removed; see git history)`

Wrong examples (do not use):
- `ai_fatal_mistakes.txt`
- `errors.txt`
- `1_example_plan.txt`

### Testing file naming rule
Every test file must map to the source file stem it validates.

Pattern:
- Source: `backend/app/api/prompt_engine.py`
- Test: `tests/backend/app/api/test_prompt_engine.py`

No naked test filenames are allowed. Test filenames must directly reveal the target module.

### Documentation consistency rule
If docs describe runtime behavior that differs from code, update docs immediately and record the correction in `ERRORS.md (removed; see git history)`.
