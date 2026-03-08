# Auth + Per-User Persistence Design

> **What this doc is for:** Design of authentication (Google OAuth) and per-user data persistence. Edit this doc when auth flow, session storage, or user data persistence changes.

## Overview

StoriesChat uses Google OAuth 2.0 for authentication and Railway's `/data` persistent volume for
per-user game state storage. The architecture supports **browse freely, login to play**: the home
screen and game catalog are public; clicking "Play" triggers the login flow.

---

## Architecture

```
Browser
  ├── Home screen (no auth needed)        → GET /api/stories (public)
  ├── Click Play → JWT missing?
  │     └── Shows login modal
  │           → Click "Continue with Google"
  │           → GET /auth/google/login (backend)
  │           → Google OAuth consent screen
  │           → GET /auth/google/callback (backend)
  │           → Redirect to /?token=<jwt>
  │           → Frontend stores JWT in localStorage
  └── Chat (authenticated)               → POST /api/chat + Authorization: Bearer <jwt>

Backend
  ├── JWT validation (FastAPI dependency) → extracts real user_id from sub claim
  ├── SQLite (/data/storieschat.db)       → users + game_sessions tables
  ├── JSONL files (/data/users/{uid}/sessions/{sid}.jsonl) → raw conversation log
  └── In-memory SESSIONS cache           → fast per-turn access, loaded from SQLite on cache miss
```

---

## Auth Flow

### Login
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

### Per-request auth
- Every API call that needs auth includes `Authorization: Bearer <jwt>` header
- `get_current_user` dependency verifies JWT signature and returns payload
- `get_optional_user` dependency returns `None` if no JWT (used in `/api/chat`)

### Anonymous users
- No JWT → `user_id = "anon"` in `chat_handler`
- Anonymous users can play (in-memory only, no persistence, state lost on server restart)
- Same experience as before auth was added

---

## Database Schema

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

## JSONL Raw Logs

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

## State Serialization

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

**Complex objects NOT serialized** (always rebuilt from story config on resume):
- `world_runtime` — rebuilt by `WorldLoader`
- `character_graph` — rebuilt from `StoryDefinition.relationships`
- `story_cfg` — rebuilt by `_canonicalize_story_cfg()`
- `epistemic_state` entries — re-seeded by `_seed_epistemic_from_story()`
- `transient_entries` — re-seeded by `_seed_noncanonical_story_details_to_transient()`

---

## API Endpoints

### Auth
| Method | Path | Auth required | Description |
|--------|------|---------------|-------------|
| GET | `/auth/google/login` | No | Redirect to Google OAuth |
| GET | `/auth/google/callback` | No | Handle OAuth callback, issue JWT |
| GET | `/api/auth/me` | Yes | Return current user info |
| POST | `/api/auth/logout` | No | Stateless (client clears JWT) |

### User Sessions
| Method | Path | Auth required | Description |
|--------|------|---------------|-------------|
| GET | `/api/user/sessions` | Yes | List user's game sessions (newest first) |
| GET | `/api/user/sessions/{id}/history` | Yes | Paginated conversation history |
| DELETE | `/api/user/sessions/{id}` | Yes | Delete session + JSONL file |

---

## Security Guarantees

1. **No data bleed**: Every DB query uses `WHERE user_id = ?` with JWT's `sub` claim
2. **Session ownership**: `get_session()` returns `None` if `user_id` doesn't match
3. **JSONL isolation**: Path uses `user_id` from JWT, never from request body
4. **Anonymous fallback**: `user_id = "anon"` → in-memory only, no DB writes
5. **JWT signed**: HS256, `JWT_SECRET` from Railway env var, 30-day expiry

---

## Concurrency

- SQLite handles 20+ concurrent users trivially (WAL mode, connection-per-operation)
- In-memory SESSIONS cache: per-session, no shared mutable state between users
- JSONL writes: append-only, one file per session, no contention
- Uvicorn single worker is sufficient for 20-50 users; bump to 2 workers if needed

---

## Google Cloud Console Setup

1. Go to https://console.cloud.google.com/
2. Create a project (or use existing)
3. Navigate to **APIs & Services → Credentials**
4. Click **Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Authorized redirect URIs — add ALL:
   - `https://storieschat.ai/auth/google/callback`
   - `https://beta-api.storieschat.ai/auth/google/callback`
   - `http://localhost:8899/auth/google/callback`
7. Copy **Client ID** and **Client Secret**
8. In Railway dashboard for **both prod and beta** services, add env vars:
   ```
   GOOGLE_CLIENT_ID=<your client id>
   GOOGLE_CLIENT_SECRET=<your client secret>
   JWT_SECRET=<run: python -c "import secrets; print(secrets.token_hex(32))">
   ```
9. Optionally: **APIs & Services → OAuth consent screen** → set app name "StoriesChat"

---

## New Files

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
