# AI Coding Agent Instructions for mvp_chat

## Project Overview
**StoriesChat**: An interactive narrative game backend where players engage in real-time dialogue with AI characters. The system combines story-driven state management, hybrid knowledge retrieval, and world navigation to create immersive murder mystery experiences.

**Tech Stack**: FastAPI (Python 3.10), OpenAI GPT-4o-mini, FAISS + BM25 hybrid retrieval, Docker/Railway deployment

## Architecture Layers

### 1. API Layer (`backend/app/api/`)
**Entry point**: `chat.py` – the single chat endpoint orchestrating the entire request flow.

**Key patterns**:
- **Session management**: In-memory `SESSIONS` dict (keyed by `session_id`) stores `MurderGameState`, message log, and debug mode.
- **Command parsing**: Prefixed commands (`__cmd_reset__`, `__cmd_newgame__:`) handled before LLM call.
- **Debug toggle**: Type `[D]`, `[DEBUG]`, etc. to toggle `debug_mode` for state inspection without LLM invocation.
- **Flow**: Extract location intent → retrieve knowledge → build messages → call OpenAI → apply state tag → advance world time

### 2. Game State (`backend/app/engine/state.py`)
**Core abstraction**: `MurderGameState` dataclass replaces dict-based state from earlier versions.

**Critical attributes**:
- `player_name`, `gender`: Set at game init via `__cmd_newgame__`.
- `story_cfg`: Loaded story JSON (contains character config, opening text, manifestation rules).
- `characters`: Dict of `CharacterState` (indexed by `key`, e.g., `"MAIN"`).
- `location_id`, `location`: Current world position; synced with world graph if available.
- `minute`: World time tracker; advanced by `advance_time(state, msg)` based on message length.
- `emotion`, `relationship`: Per-character dynamics; modified via state tags in LLM response.
- `world_runtime`: Optional `WorldLoadResult` containing graph, clock, travel resolver (loaded if story has `"world"` config).

### 3. Knowledge Retrieval (`backend/app/knowledge/`)

**Entry**: `retrieve_knowledge(query)` in `runtime/retrieve.py` – called in `chat.py` before building prompt.

**Architecture**:
- **IndexService** (`runtime/index_service.py`): Thread-safe cache for character-specific index bundles (BM25 + FAISS).
  - Per-request active character set via `set_active_character(character_id)`.
  - Falls back to env var `KNOWLEDGE_CHARACTER_ID` or auto-detects single character dir.
- **Hybrid retrieval**: BM25 (lexical) + FAISS (semantic) scored separately, fused by `hybrid_retrieve()`.
- **Character knowledge**: Lives in `backend/app/knowledge/characters/<character_id>/` – built at deploy time via `build_index.py`.

**For new retrieval types**: Extend `retrieve_knowledge()` return tuple; update `api/chat.py` call site accordingly.

### 4. Prompt Builder (`backend/app/engine/prompt_builder.py`)
**Function**: `build_messages(state, log, user_msg, retrieved_chunks)` → list of OpenAI message dicts.

**Key sections**:
- **System prompt**: Instructs LLM on character role, world context, manifestation state.
- **Memory block**: Formatted retrieved chunks injected as canon facts (debug info included).
- **Conversation history**: Last `MEMORY_TURNS` exchanges from session log.

**State tags** (LLM output parsing): LLM appends JSON tag at response end, e.g., `[[STATE: {"emotion": "soft", "rel_delta": 1}]]`. Parsed by `extract_state_tag()`, applied to `MurderGameState` via `apply_state_tag()`.

### 5. World Engine (`backend/app/engine/world/`)

**Optional subsystem** – only active if story has `"world"` config.

- **WorldLoader**: Parses JSON with `locations` (id, name, description, tags) and `edges` (travel routes, minutes, blocked status).
- **WorldGraph**: Node/edge container; handles location lookups and reachability.
- **TravelResolver**: Computes travel time & validity (blocks, exposure rules).
- **WorldClock**: Tracks in-world time; used in `WorldTimeFormatter.compute(start_datetime, minute)` for display.
- **Location intent extraction** (`extractors/location_extractor.py`): Disambiguates movement commands against active graph (conservative – only triggers on explicit "go to X" commands).

## Data Flows

### New Game Initialization
1. Client sends `__cmd_newgame__:<story_id>|<gender>|<player_name>`.
2. `chat_handler()` loads story JSON via `load_story(story_id)`.
3. `init_state()` creates fresh `MurderGameState`.
4. If story has `"world"` key, `WorldLoader.load_from_file()` or `.try_load_story_world()` populates `world_runtime`.
5. Character config from story initializes `MurderGameState.characters[main_key]`.
6. Opening text from `story_cfg["opening"]["text"]` + placeholders returned to client.

### Turn Processing
1. **Time advance**: `advance_time(state, msg)` → computes `word_count(msg)` × `MINS_PER_WORD`, updates `state.minute`.
2. **Name extraction**: Regex patterns in `NAME_PATTERNS` detect "my name is X"; confirm via `CONFIRM_WORDS`.
3. **Location intent**: Optional extractor calls LLM-free heuristics; if `intent == MOVE`, canonicalize to "go to <location_id>".
4. **Knowledge retrieval**: `retrieve_knowledge(msg)` → hybrid BM25 + FAISS search from active character bundle.
5. **Prompt build**: `build_messages(state, log, msg, retrieved)` injects system context + memory + history.
6. **LLM call**: OpenAI request with `temperature=0.8`, `max_tokens=512`.
7. **State tag parsing**: Extract `[[STATE: {...}]]` from response tail; apply via `apply_state_tag()`.
8. **Win condition**: `confession_detected(reply, state)` checks for confession; if yes, `state.over = True` + end game message.

### Deployment & Caching
- **Knowledge indexes** built at Docker build time (or on-demand at first request if `FORCE_REBUILD_INDEX=1`).
- **Env vars** (Railway):
  - `OPENAI_API_KEY`: Required.
  - `KNOWLEDGE_CACHE_DIR`: Where FAISS + BM25 artifacts stored (default: `/data/knowledge_cache`).
  - `PYTHONPATH=/srv`: Points to `/srv/backend`, `/srv/tests`.

## Testing & Debugging

### Running Tests
```bash
pytest tests/backend
```
- Markers: `@pytest.mark.integration` for end-to-end tests (hybrid retrieval, 5-turn gameplay).
- State tracking: Inspect logs via `assert state.minute > 0` after `advance_time()`.

### Debug Mode
- Type `[D]` in chat to toggle debug output.
- Appends ASCII box with: current timestamp, user location, character list + individual locations.
- Never added to LLM context (client-side only).

### JSON Logging
- All key events logged as JSON lines to stdout (Railway Deploy Logs):
  - `chat_request`: Turn data, retrieval debug, chunk IDs.
  - `chat_response`: Latency, usage, preview.
  - `retrieval_error`, `chat_upstream_error`: Errors with context.

## Conventions & Patterns

### State Access
- **Always use `getattr(state, attr, default)`** – `MurderGameState` is a dataclass; safe fallback for optional fields.
- **Location syncing**: Both `state.location` (string for UI) and `state.location_id` (graph key) must stay in sync when world graph is active.

### Character Identity
- `state.main_character_id` = key of the main NPC (e.g., `"MAIN"`).
- `state.knowledge_character_id` = character dir name for retrieval (e.g., `"1_iu"`).
- Can differ: story file configures both independently.

### Story JSON Structure
```json
{
  "opening": { "text": "{{PLAYER_NAME}}, welcome..." },
  "setting": { "start_location": "Office" },
  "main_character": {
    "key": "MAIN",
    "name": "Yuna",
    "knowledge_character_id": "1_iu"
  },
  "world": {
    "file": "iu_murder_mystery_world.json",
    "seed": 42,
    "start_datetime": "2025-01-01T09:00:00"
  },
  "rules": {
    "manifestation": { "apartment_location_contains": ["unit 302", "officetel"] }
  }
}
```

### Error Handling
- **Silent fallbacks**: Retrieval errors return empty chunks; LLM still runs with base prompt.
- **Logging over exceptions**: Use `_log({"kind": "error_type", ...})` instead of crashing.
- **Location extraction**: Wrapped in try/except; only optimizes, never blocks turn flow.

### Naming Conventions
- **State tags**: `[[STATE: {...}]]` – double brackets, capital STATE, JSON dict inside.
- **Commands**: Prefixed with `__cmd_` + snake_case (e.g., `__cmd_newgame__`).
- **Debug tokens**: `[D]`, `[DEBUG]`, `(D)`, `(DEBUG)` – case-insensitive after strip + upper.

## Common Tasks

### Adding a New Story
1. Create `backend/app/stories/<story_id>.json` with structure above.
2. If world needed: create `backend/app/stories/<story_id>_world.json` with locations/edges; reference in story.
3. Link knowledge bundle: set `knowledge_character_id` to match character dir in `backend/app/knowledge/characters/`.
4. No code changes required; tested via `__cmd_newgame__:<story_id>` in session.

### Extending Knowledge Retrieval
- Modify `retrieve_knowledge()` signature/return if adding new chunk types.
- Update call site in `api/chat.py` to pass new data to `build_messages()`.
- Regenerate indexes: `python backend/app/knowledge/build/build_index.py`.

### Debugging State Issues
1. Toggle debug mode (`[D]`) to inspect location, character list, timestamp.
2. Check `_log()` output in Railway logs for retrieval, LLM, state tag parsing events.
3. Verify `state.story_cfg` loaded correctly: inspect opening text + character keys.

### Understanding Timing
- `state.minute` incremented per turn by: `word_count(msg) × MINS_PER_WORD + BASE_TURN_MINS`.
- Travel: if `location` changes, add `TRAVEL_MINS` (15 default).
- World time display: `WorldTimeFormatter.compute(state.world_start_datetime, state.minute)`.

## Critical Files by Role
| File | Purpose |
|------|---------|
| `api/chat.py` | Main endpoint + session loop |
| `engine/state.py` | State definition + init |
| `engine/prompt_builder.py` | Message construction + state tag parsing |
| `engine/world/world_loader.py` | World JSON parsing |
| `knowledge/runtime/retrieve.py` | Hybrid retrieval entry |
| `knowledge/runtime/index_service.py` | Character bundle caching |
| `config/settings.py` | Game constants (turn time, relationship bounds, etc.) |
