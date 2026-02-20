# MVP Chat - Quick Reference Guide

## File Index

### Backend Core Files

| File | Lines | Purpose | Key Functions |
|------|-------|---------|---------------|
| `main.py` | 113 | FastAPI app entry point | `warm_indexes()`, `_startup_event()`, `version()` |
| `config/settings.py` | 26 | Global configuration | Constants only |
| `api/chat.py` | 728 | Main gameplay API | `chat_handler()`, `get_session()`, `_translate_to_chinese()` |
| `api/health.py` | 28 | Health check | `health()` |
| `api/echo.py` | 28 | Debug echo | `echo()` |
| `api/stories.py` | 53 | List stories | `list_stories()` |
| `api/story.py` | 59 | Story metadata | `get_story_meta()` |

### Game Engine Files

| File | Lines | Purpose | Key Functions |
|------|-------|---------|---------------|
| `engine/state.py` | 239 | State dataclasses | `init_state()`, `apply_state_tag()`, `extract_state_tag()` |
| `engine/gameplay.py` | 160 | Game mechanics | `advance_time()`, `manifest_mode()`, `win_condition_detected()` |
| `engine/prompt_builder.py` | 318 | AI prompt construction | `system_prompt()`, `build_messages()` |
| `engine/story_loader.py` | 63 | Story JSON loading | `load_story()` |
| `engine/time_utils.py` | 50 | Time formatting | `WorldTimeFormatter.compute()` |

### Extractors

| File | Lines | Purpose | Key Functions |
|------|-------|---------|---------------|
| `extractors/location_extractor.py` | 277 | NLP location intent | `extract()`, `_should_attempt()`, `_parse_json()` |

### World System Files

| File | Lines | Purpose | Key Functions |
|------|-------|---------|---------------|
| `world/world_loader.py` | 101 | Load world JSON | `load_from_file()`, `try_load_story_world()` |
| `world/graph.py` | 71 | World graph structure | `add_location()`, `add_edge()`, `get_outgoing()` |
| `world/location.py` | 37 | Location dataclass (includes `uuid`) | `__post_init__()` |
| `world/edge.py` | 34 | Edge dataclass | `__post_init__()` |
| `world/clock.py` | 41 | Time management | `advance_minutes()` |
| `world/travel_resolver.py` | 115 | Travel execution | `execute()`, `resolve()` |
| `world/travel_rules.py` | 214 | Pathfinding & routing | `resolve_route()`, `_find_path_bfs()` |
| `world/exposure.py` | 150 | Travel event system | `roll()` |
| `world/ids.py` | 24 | LocationId type | - |

### Knowledge System Files

| File | Lines | Purpose | Key Functions |
|------|-------|---------|---------------|
| `knowledge/runtime/index_service.py` | 79 | Index cache manager | `get()`, `set_active_character()` |
| `knowledge/runtime/load_indexes.py` | 214 | Artifact loading | `load_character_indexes()` |
| `knowledge/runtime/retrieve.py` | 86 | Hybrid retrieval | `retrieve_knowledge()` |
| `knowledge/build/build_index.py` | 281 | Index builder | `main()` |
| `knowledge/contracts/index_bundle.py` | 18 | Bundle dataclass | - |

### Frontend File

| File | Lines | Purpose | Key Functions |
|------|-------|---------|---------------|
| `frontend/index.html` | 568 | Terminal web UI | `send()`, `commitLine()`, `typewrite()`, `handleMenu()`, `handleName()`, `handleGender()` |

---

## North Star (Plain English)
- One ground truth: world state lives in code, not inside the LLM.
- Time is the driver: every message spends minutes; travel advances the world clock.
- No plotted branches: NPC behavior should flow from incentives and constraints, not scripts.
- Two-call target: first a structured extractor mutates state, then a renderer speaks. (Currently only the location extractor exists.)
- Difficulty changes forgiveness, not facts.

## Class Cheat Sheet
- `GameState` — the session ledger: time, location, player identity, world runtime, NPC roster, mood/relationship.
- `UserState` — what NPCs think your name/gender are (display vs formal).
- `CharacterState` — per-NPC card with role, emotion, relationship.
- `PromptBuilder` — shapes the system prompt + header and injects retrieved memory.
- `LocationExtractor` — LLM classifier that only triggers on explicit “go/move to …” commands.
- World graph set (`WorldGraph`, `Location`, `PathEdge`, `WorldClock`, `TravelRules`, `TravelResolver`, `ExposureResolver`) — map + clock that decide routes, minutes spent, and what travel details are exposed.
- Knowledge layer (`IndexService`, `CharacterIndexBundle`, `retrieve_knowledge`) — loads/caches BM25+FAISS bundles per character.

## Prompt Source Contract
- Prompt context is limited to: BM25/FAISS retrieval chunks, character basics, canonical truths (`epistemic_seed.canonical_facts`), character graph, belief graph, places graph, and transient buffer.
- Free-form story JSON fields are not injected directly into prompt; non-canonical story/character extras are serialized into transient context.
- Canonical story projection at new-game time keeps only generic runtime keys (`id,title,theme,instance,opening,world,time,emotion,goal,win_detection,epistemic_seed,canonical_truth,characters,relationships`).
- Each prompt knowledge item is labeled with certainty + epistemic visibility (`known_by`, `not_known_by`, `maybe_known_by`).
- Common knowledge must be represented as `known_by: ["all_characters"]`.
- Runtime stack order is: `CANONICAL_CORE` → `CANONICAL_GRAPH` → `SUBJECTIVE_BELIEF` → `RETRIEVED_MEMORY` → `TRANSIENT_CONTEXT`.
- Unknown visibility handling: if a chunk has no explicit known/not-known marker for the active speaker, model makes a best reasonable determination from dialogue context.
- Post-reply extractor pass (`KnowledgeResolutionExtractor`) converts those determinations into explicit belief updates and stores transient knowledge objects for 8 turns.

## API Endpoints

| Method | Endpoint | Purpose | Request | Response |
|--------|----------|---------|---------|----------|
| POST | `/api/chat` | Main gameplay | `{message, session_id}` | `{reply, usage, character}` |
| GET | `/api/stories` | List stories | - | `{stories: [{id, title, theme}]}` |
| GET | `/api/story/{id}` | Story metadata | - | `{id, title, goal, rules, known_locations}` |
| GET | `/api/health` | Health check | - | `{ok, php, time, cwd}` |
| POST | `/api/echo` | Debug echo | any | `{method, raw, json}` |
| GET | `/api/version` | Backend version | - | `{status, backend, message}` |

---

## Special Commands (In-Game)

| Command | Effect |
|---------|--------|
| `[D]`, `(D)`, `[DEBUG]`, `(DEBUG)` | Toggle debug mode (shows game state) |
| `[C]`, `(C)`, `[CHINESE]`, `(CHINESE)` | Toggle Chinese translation mode |
| `[M]`, `(M)`, `[MAP]`, `(MAP)` | Show world map (locations list) |
| `[ES]`, `(ES)`, `[EPISTEMICSTATE]`, `(EPISTEMICSTATE)` | Toggle epistemic layers on/off |
| `__cmd_reset__` | Reset session (clear memory) |
| `__cmd_newgame__:<story_id>|<gender>|<name>` | Start new game |
| `go to <location>` | Move to location (world graph) |
| `move to <location>` | Move to location (world graph) |

---

## Data Structures

### GameState (Main Game State)

```python
@dataclass
class GameState:
    # Session
    story: Optional[str]
   user_id: str
   instance: int  # deterministic-id instance (default 1)
    gender: Optional[str]  # 'M' or 'F'
    turns: int
    over: bool

    # Time & Location
    minute: int
    location: str
    location_id: str  # World graph ID
   location_uuid: str  # deterministic UUID for current location

    # Emotion & Relationship
    emotion: str  # e.g., "wary, exhausted"
    relationship: int  # -5 to +5

    # Story metadata
    story_cfg: Optional[dict]
    player_name: Optional[str]
    knowledge_character_id: str

    # Objects
    user: UserState
    characters: Dict[str, CharacterState]
    main_character_id: Optional[str]

    # World runtime
    world_runtime: Optional[WorldLoadResult]
    world_start_datetime: str
    last_travel_from_id: str
    last_travel_to_id: str
   last_travel_from_uuid: str
   last_travel_to_uuid: str
    last_travel_exposure: Optional[ExposurePacket]
```

### CharacterState

```python
@dataclass
class CharacterState:
    key: str  # "main", "suspect1", etc.
    name: str  # "IU", "Manager", etc.
    role: str  # "ghost", "victim", "suspect"
    emotion: str
    relationship: int
   uuid: str
```

### UserState

```python
@dataclass
class UserState:
    formal_name: str  # Full name learned by character
    display_name: str  # What character calls user
    gender: Optional[str]  # 'M' or 'F'
```

---

## Configuration Constants

### Game Settings (`config/settings.py`)

```python
OPENAI_MODEL = "gpt-4o-mini"
MAX_TOKENS = 512
TEMPERATURE = 0.8
MEMORY_TURNS = 8   # Conversation history length
EXTRACTOR_TURNS = 8  # History window for movement intent classifier

START_LOCATION = "Nonhyeon-dong officetel"
START_MINUTE = 0
MINS_PER_WORD = 0.25  # Time advancement rate
BASE_TURN_MINS = 1
TRAVEL_MINS = 15

REL_MIN = -5
REL_MAX = 5
REL_START = 0
EMOTION_START = "wary, exhausted"
DEFAULT_USER_ID = "default_user"
DEFAULT_INSTANCE = 1

# Deterministic UUID format
# <user_id>-<story_id>-<instance>-<entity_id>
```

### Knowledge System Paths

```python
# Image-bundled artifacts
backend/app/knowledge/characters/<character_id>/
  ├── chunks.jsonl
  ├── bm25.json
  ├── faiss.index
  ├── embeddings.npy
  └── build_info.json

# Persistent cache (deployment)
/data/knowledge_cache/characters/<character_id>/
  └── (same files)
```

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication | (required) |
| `KNOWLEDGE_CHARACTER_ID` | Default character for retrieval | Auto-detect |
| `KNOWLEDGE_CACHE_DIR` | Index cache directory | `backend/app/knowledge` |
| `KNOWLEDGE_PERSIST_ROOT` | Alternative cache directory | `/data/knowledge_cache` |
| `FORCE_REBUILD_INDEX` | Force index rebuild (1=yes) | `0` |
| `DISABLE_INDEX_WARMUP` | Disable startup warmup (1=yes) | `0` |
| `REQUIRE_INDEXES` | Hard fail if indexes missing (1=yes) | `0` |
| `CHARACTER_DIRNAME` | Character dir for build_index | *(auto-discovered)* |

---

## Workflow Examples

### User Turn Processing Flow

```
1. User sends message → POST /api/chat
2. Retrieve/create session from SESSIONS dict
3. Check for special commands (debug, Chinese, map toggles)
4. advance_time(state, message) - update game clock
5. retrieve_knowledge(message) - BM25 + FAISS hybrid search
6. LocationExtractor.extract() - NLP intent classification
7. If MOVE intent: TravelResolver.resolve() - execute movement
8. build_messages() - construct AI prompt with context
9. Call OpenAI API - get response
10. extract_state_tag() - parse [[STATE]] metadata
11. sanitize_korean_terms() - enforce relationship rules
12. apply_state_tag() - update emotion/relationship
13. win_condition_detected() - check win condition
14. _translate_to_chinese() - optional translation
15. Update session log, return response
```

### World Graph Travel Flow

```
1. User: "go to Gangnam Station"
2. gameplay.advance_time() detects movement regex
3. _resolve_destination_id() normalizes "Gangnam Station" → "gangnam_station"
4. travel_resolver.resolve(from_id, to_id)
   a. TravelRules.resolve_route():
      - Try direct edge A→B
      - Try 1-intermediate A→C→B
      - Try BFS pathfinding (up to 10 hops)
      - Fallback: create dynamic edge (island warning)
   b. WorldClock.advance(exit_minutes) - exit origin
   c. For each edge: WorldClock.advance(edge.minutes)
   d. ExposureResolver.roll() - determine visible events
5. Update state.location_id, state.location, state.minute
6. Store travel history (last_travel_from_id, last_travel_to_id, last_travel_exposure)
```

### Knowledge Retrieval Flow

```
1. retrieve_knowledge("tell me about the character")
2. IndexService.get(active_character_id)
   - Check cache → return if exists
   - Else: load_character_indexes(active_character_id)
     * Load chunks.jsonl
     * Load bm25.json → BM25Okapi instance
     * Load faiss.index → FAISS index
3. Hybrid retrieval:
   a. BM25 search:
      - Tokenize query → ["tell", "me", "about", "iu", "songs"]
      - Score all chunks → top 8
   b. FAISS search:
      - Embed query → 384-dim vector
      - Search index → top 8
   c. Reciprocal rank fusion:
      - Combine rankings
      - Sort by fused score → top 8 final
4. Format chunks into memory block
5. Inject into system prompt as canonical memory
```

---

## Testing Commands

### Run Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/backend/app/api/test_chat.py

# Integration tests only
pytest -m integration

# With verbose output
pytest -v tests/
```

### Build Indexes

```bash
# Build for first auto-discovered character
cd backend
python -m backend.app.knowledge.build.build_index

# Force rebuild
FORCE_REBUILD_INDEX=1 python -m backend.app.knowledge.build.build_index

# Build for different character
CHARACTER_DIRNAME=2_alice python -m backend.app.knowledge.build.build_index
```

### Run Server Locally

```bash
# Development server
cd backend
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# Production server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Common Issues & Solutions

### 1. "Could not locate required knowledge artifacts"

**Problem:** Index files missing

**Solution:**
```bash
# Build indexes
cd backend
FORCE_REBUILD_INDEX=1 python -m backend.app.knowledge.build.build_index
```

### 2. "World Graph Island Detected"

**Problem:** Disconnected locations in world graph

**Solution:**
- Check `iu_murder_mystery_world.json`
- Add missing edges between location groups
- Verify all locations are reachable from start_location

### 3. "No knowledge character id configured"

**Problem:** Character ID not set for retrieval

**Solution:**
```python
# In story JSON:
"main_character": {
  "knowledge_character_id": "<character_dir_name>"
}

# Or set environment variable:
KNOWLEDGE_CHARACTER_ID=<character_dir_name>
```

### 4. Chinese translation returns English

**Problem:** OpenAI API error or rate limit

**Solution:**
- Check `OPENAI_API_KEY` is set
- Verify API quota/rate limits
- Review logs for `chinese_translation_error`

### 5. Location extraction not working

**Problem:** LLM classification failing

**Solution:**
- Check OpenAI API connectivity
- Review logs for `location_extraction_error`
- Verify location IDs in world graph match expected format

---

## Performance Notes

### Memory Usage

- Session storage: ~1-5 MB per active session (in-memory)
- FAISS index: ~50-200 MB (loaded once, shared)
- BM25 index: ~5-20 MB (loaded once, shared)
- Total baseline: ~300-500 MB

### API Latency

- Health check: <10ms
- Story list: ~50-100ms
- Chat turn (no movement): ~1-2 seconds
- Chat turn (with movement): ~1.5-3 seconds
- Chinese translation: +500ms-1s

### Optimization Tips

1. **Enable index warmup** - `DISABLE_INDEX_WARMUP=0` (default)
2. **Use persistent cache** - Set `KNOWLEDGE_CACHE_DIR=/data/knowledge_cache`
3. **Reduce MEMORY_TURNS** - Lower if memory constrained (default: 8)
4. **Adjust MAX_TOKENS** - Lower for faster responses (default: 512)

---

## Architecture Patterns

### 1. Dependency Injection

- `TravelResolver` receives all dependencies in `__init__`
- Enables testing with mocks/stubs

### 2. Frozen Dataclasses

- Immutable data structures (Location, PathEdge, ExposurePacket)
- Thread-safe, hashable, predictable

### 3. Thread-Safe Caching

- `IndexService` uses `Lock` + double-checked locking
- Prevents race conditions on first load

### 4. Seeded Randomness

- `TravelRules`, `ExposureResolver` use seeded RNG
- Deterministic behavior for testing

### 5. Hybrid Retrieval

- BM25 (lexical) + FAISS (semantic)
- Reciprocal rank fusion for best results

### 6. Atomic File Writes

- Use temp file + `replace()` for safe writes
- Prevents corruption on crash

---

**End of Quick Reference**
