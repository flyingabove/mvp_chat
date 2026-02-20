# MVP Chat - Comprehensive Code Documentation

**Generated:** 2026-01-26
**Project:** StoriesChat Backend (Python FastAPI) + Terminal Frontend

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Backend Architecture](#backend-architecture)
3. [Frontend Architecture](#frontend-architecture)
4. [File-by-File Documentation](#file-by-file-documentation)
5. [Redundant & Unused Code Analysis](#redundant--unused-code-analysis)
6. [Architecture Diagrams](#architecture-diagrams)

---

## Project Overview

**MVP Chat** is an interactive narrative game platform featuring:
- **Backend**: Python FastAPI application with AI-powered storytelling (OpenAI GPT-4o-mini)
- **Frontend**: Single-page terminal-style web application (Vanilla JS)
- **Knowledge System**: Hybrid BM25 + FAISS vector retrieval for character knowledge
- **World System**: Graph-based location/travel mechanics with time progression
- **Story Format**: JSON-based story configuration with character states

**Tech Stack:**
- FastAPI 0.110.0, Uvicorn 0.29.0
- PyTorch 2.1.2, sentence-transformers 2.6.1, FAISS 1.7.4, Rank-BM25 0.2.2
- OpenAI API (gpt-4o-mini)
- Docker + Railway deployment

---

## Backend Architecture

### Core Components

```
backend/app/
├── main.py                    # FastAPI app entry point
├── config/                    # Configuration
├── api/                       # REST API endpoints
├── engine/                    # Game logic & mechanics
│   ├── state.py              # Game state management
│   ├── gameplay.py           # Gameplay mechanics
│   ├── prompt_builder.py     # AI prompt construction
│   ├── story_loader.py       # Story JSON loading
│   ├── time_utils.py         # Time formatting
│   ├── extractors/           # NLP extractors (location)
│   └── world/                # World graph system
├── knowledge/                 # Hybrid retrieval system
│   ├── build/                # Index building (offline)
│   ├── runtime/              # Index loading & retrieval
│   ├── contracts/            # Data structures
│   └── characters/           # Pre-built knowledge bases
├── middleware/                # HTTP middleware
└── stories/                   # Story content (JSON)
```

---

## Frontend Architecture

**File:** `frontend/index.html` (568 lines, single-page app)

### Components:
- Terminal UI rendering (monospace, dark theme)
- Input handling (IME support for mobile)
- Typewriter effect for bot responses
- Story selection menu
- Gender/name input flow
- API communication via XMLHttpRequest

### Key Features:
- Mobile-optimized with fixed toolbar
- iOS web app support
- Version tracking (`version.json`)
- Debug/Chinese/Map toggle commands
- Rich text formatting (bold, italic, quotes)

---

## North Star Snapshot (Plain English)

- One shared ground truth: locations, characters, time, and game state live in a single state container, not in the model's head.
- Time is the engine: every message costs minutes; travel advances the world clock; NPC actions should be driven by elapsed time and incentives.
- No plotted branches: instead of hand-scripted scenes, the system should react to incentives, constraints, and player choices.
- Two-call ambition: first a structured extractor updates state, then the main LLM renders dialogue without inventing new facts. (Currently, only a location extractor exists; quest/extractor split is still to build.)
- Difficulty = narrative resistance: easier modes forgive timing/decay; harder modes keep consequences sharp while preserving canon.

## Class Quick Guide (Plain English)

- `GameState`: the entire game ledger—tracks player identity, time, location, relationship/emotion, story config, and optional world runtime.
- `UserState`: what the NPC thinks your name and gender are; separates “display name” (what they call you) from “formal name”.
- `CharacterState`: a lightweight card for each NPC (id, name, role, current emotion, relationship score).
- `PromptBuilder`: assembles the system prompt and user message header, injects retrieved memory, enforces style/[[STATE]] tag rules.
- `LocationExtractor`: LLM-powered classifier that only detects explicit move commands and maps them to a known location id using world graph + knowledge hints.
- World graph set (`WorldGraph`, `Location`, `PathEdge`, `WorldClock`, `TravelRules`, `TravelResolver`, `ExposureResolver`): authoritative map + clock; chooses routes, advances minutes, and decides what parts of travel are exposed to the story.
- `WorldLoader` / `WorldLoadResult`: load world JSON into the runtime objects above.
- Knowledge layer (`IndexService`, `CharacterIndexBundle`, `retrieve_knowledge`): loads/caches BM25+FAISS artifacts per character and returns fused chunks + debug info.
- Utilities (`WorldTimeFormatter`, `logging_utils`): human-readable timestamps and JSON logging for deploy visibility.

---

## File-by-File Documentation

---

### BACKEND FILES

---

#### `backend/app/main.py` (113 lines)

**Purpose:** FastAPI application entry point and configuration

**Functions:**

- **`warm_indexes()`** (lines 53-74)
  - Warm retrieval indexes in background thread
  - Non-blocking, safe to disable in tests
  - Prevents first-request load cost

- **`_startup_event()`** (lines 80-91)
  - FastAPI startup event handler
  - Conditionally requires indexes if `REQUIRE_INDEXES=1`
  - Otherwise triggers background warmup

- **`version()`** (lines 107-113)
  - GET `/api/version` endpoint
  - Returns backend status and version info

**Configuration:**
- CORS middleware (allows storieschat.ai domains)
- Request ID middleware (for logging/tracing)
- 5 API routers registered (chat, echo, health, story, stories)

---

#### `backend/app/config/settings.py` (26 lines)

**Purpose:** Global configuration constants

**Constants:**
- **`OPENAI_API_KEY`**: OpenAI API key from environment
- **`OPENAI_MODEL`**: "gpt-4o-mini" (hardcoded)
- **`MAX_TOKENS`**: 512
- **`TEMPERATURE`**: 0.8
- **`MEMORY_TURNS`**: 8 (conversation history window for the main model)
- **`EXTRACTOR_TURNS`**: 8 (history window for the location/movement extractor)
- **`GAME_TITLE`**: "storieschat.ai (beta)"
- **`START_LOCATION`**: "Nonhyeon-dong officetel"
- **`START_MINUTE`**: 0
- **`MINS_PER_WORD`**: 0.25 (time progression rate)
- **`BASE_TURN_MINS`**: 1
- **`TRAVEL_MINS`**: 15
- **`REL_MIN`**: -5 (relationship bounds)
- **`REL_MAX`**: 5
- **`REL_START`**: 0
- **`EMOTION_START`**: "wary, exhausted"

---

#### `backend/app/api/chat.py` (1477 lines)

**Purpose:** Main gameplay loop and chat API endpoint

**Global Variables:**
- **`SESSIONS`** (line 67): In-memory session store `{session_id -> {state, log, debug_mode, chinese_mode}}`
- **`_LOCATION_EXTRACTOR`** (line 71): Shared stateless LocationExtractor instance
- **`DEBUG_TOGGLE_TOKENS`**, **`CHINESE_TOGGLE_TOKENS`**, **`MAP_TOGGLE_TOKENS`**: Command tokens

**Functions:**

- **`_is_debug_toggle(msg: str) -> bool`** (lines 85-86)
  - Check if message is debug toggle command

- **`_is_chinese_toggle(msg: str) -> bool`** (lines 100-101)
  - Check if message is Chinese mode toggle

- **`_is_map_toggle(msg: str) -> bool`** (lines 115-116)
  - Check if message is map toggle command

- **`_box(title: str, lines: list[str]) -> str`** (lines 119-139)
  - Render ASCII box for UI display
  - Uses Unicode box-drawing characters

- **`_log(event: dict)`** (lines 145-149)
  - JSON logging to stdout (Railway logs)
  - Safe logging with exception handling

- **`_truncate(s: str, n: int = 6000) -> str`** (lines 152-154)
  - Truncate long strings for logging

- **`_translate_to_chinese(text: str) -> str`** (lines 160-219) **[ASYNC]**
  - Translate English to Chinese using OpenAI API
  - Preserves formatting (bold, italics, quotes)
  - Fallback to English on error

- **`get_session(session_id: str)`** (lines 225-233)
  - Retrieve or create session from in-memory store
  - Initializes with default state/log/modes

- **`apply_placeholders(text: str, state: GameState) -> str`** (lines 239-245)
  - Replace `{{PLAYER_NAME}}` and `{{HONORIFIC}}` in opening text

- **`sanitize_korean_terms(text: str, state: GameState) -> str`** (lines 251-263)
  - Remove Korean honorifics ("oppa", "unnie") if relationship < 2
  - Uses regex with word boundaries

- **`clean_name(raw: str) -> str`** (lines 280-283)
  - Clean and titlecase user name
  - Remove non-alphanumeric except spaces, hyphens, apostrophes

- **`extract_user_name_from_text(user_msg: str) -> str`** (lines 286-298)
  - Extract user name from natural language using regex patterns
  - Patterns: "my name is X", "call me X", "it's X", "I am X", "I'm X"

- **`handle_name_confirmation(user_msg: str, state: GameState)`** (lines 310-320)
  - Confirm guessed name if user says "yes", "yeah", "correct", etc.

- **`chat_handler(data: dict)`** (lines 326-728) **[ASYNC]**
  - **POST `/chat`** - Main gameplay endpoint
  - Handles session management, debug/Chinese/map toggles
  - **Reset command:** `__cmd_reset__` - clears session
  - **New game command:** `__cmd_newgame__:<story_id>|<gender>|<player_name>`
  - **Regular turn flow:**
    1. Advance time based on message length
    2. Handle name extraction/confirmation
    3. Retrieve knowledge (hybrid BM25+FAISS)
    4. Extract location intent (NLP)
    5. Build AI prompt with context
    6. Call OpenAI API
    7. Extract state tags, sanitize Korean terms
    8. Update conversation log
    9. Check win condition (confession detection)
    10. Return reply (with optional Chinese translation)

**Special Commands:**
- `[D]`, `(D)`, `[DEBUG]`, `(DEBUG)` → Toggle debug mode
- `[C]`, `(C)`, `[CHINESE]`, `(CHINESE)` → Toggle Chinese translation
- `[M]`, `(M)`, `[MAP]`, `(MAP)` → Show world map

---

#### `backend/app/api/health.py` (28 lines)

**Purpose:** Health check endpoint

**Functions:**

- **`health()`** (lines 8-27) **[ASYNC]**
  - GET `/health`
  - Returns: `{ok: true, php: <Python version>, time: <unix timestamp>, cwd: <working directory>}`

---

#### `backend/app/api/echo.py` (28 lines)

**Purpose:** Debug echo endpoint

**Functions:**

- **`echo(request: Request)`** (lines 5-27) **[ASYNC]**
  - POST `/echo`
  - Echoes back request method, raw body, and parsed JSON
  - Used for debugging API calls

---

#### `backend/app/api/game_logic.py` (12 lines)

**Purpose:** Placeholder/stub endpoint

**Functions:**

- **`game_logic()`** (lines 5-11) **[ASYNC]**
  - GET `/game-logic`
  - Returns placeholder message
  - **POTENTIALLY UNUSED** - no references found in codebase

---

#### `backend/app/api/stories.py` (53 lines)

**Purpose:** List available story configurations

**Functions:**

- **`_stories_dir() -> Path`** (lines 10-12)
  - Returns path to `backend/app/stories/` directory

- **`list_stories()`** (lines 15-52) **[ASYNC]**
  - GET `/stories`
  - Scans `backend/app/stories/` for JSON files (root + subdirectories)
  - Skips `*_world.json` files
  - Returns: `{stories: [{id, title, theme}, ...]}`

---

#### `backend/app/api/story.py` (59 lines)

**Purpose:** Retrieve single story metadata

**Functions:**

- **`get_story_meta(story_id: str)`** (lines 7-58)
  - GET `/story/{story_id}`
  - Loads story JSON using `load_story()`
  - Loads world graph if available
  - Returns story metadata: `{id, title, goal, rules, known_locations}`

---

#### `backend/app/middleware/request_id.py` (14 lines)

**Purpose:** Request ID middleware for tracing

**Functions:**

- **`request_id_middleware(request: Request, call_next)`** (lines 5-13) **[ASYNC]**
  - Extracts or generates request ID (`X-Request-ID` header)
  - Stores in `request.state.request_id`
  - Adds `X-Request-ID` to response headers

---

#### `backend/app/engine/state.py` (360 lines)

**Purpose:** Game state management dataclasses

**Classes:**

- **`UserState`** **[DATACLASS]**
  - Stores player information perceived in-story
  - **Fields:**
    - `formal_name: str` - Full name learned by character
    - `display_name: str` - What character calls the user
    - `gender: Optional[str]` - 'M' or 'F'

- **`CharacterState`** **[DATACLASS]**
  - Represents any NPC in the story
  - **Fields:**
    - `key: str` - Internal ID (e.g., "main")
    - `name: str` - Display name (e.g., "IU")
    - `role: str` - Character archetype/role
    - `emotion: str` - Emotional descriptor
    - `relationship: int` - Relationship score with player
    - `uuid: str` - Deterministic UUID

- **`GameState`** **[DATACLASS]**
  - Main game state container (generic, story-type agnostic)
  - **Session fields:** `story`, `user_id`, `instance`, `gender`, `turns`, `over`
  - **Time & location:** `minute`, `location`
  - **Emotion & relationship:** `emotion`, `relationship`
  - **Knowledge:** `knowledge_character_id`
  - **Story metadata:** `story_cfg`, `player_name`
  - **Structured objects:** `user` (UserState), `characters` (Dict), `main_character_id`
  - **Epistemic structures:** `canonical_facts`, `canonical_truth`, `epistemic_log`, `observation_log`, `beliefs`
  - **Character graph:** `character_graph` (Optional[CharacterGraph])
  - **Transient buffer:** `transient_entries` (List[TransientEntry])
  - **World runtime:** `world_runtime`, `location_id`, `location_uuid`, `world_start_datetime`, `last_travel_from_id`, `last_travel_to_id`, `last_travel_from_uuid`, `last_travel_to_uuid`, `last_travel_exposure`
  - **Korean controls:** `casual_korean_used`
  - **Name helpers:** `last_assistant_guess_name`
  - **Methods:**
    - `__getitem__(key)` / `__setitem__` - Dict-like access for backward compat
    - `main_character` property - Returns primary NPC
    - `get_belief_state(character_id)` - Get or create belief state for character
    - `add_transient_entry(...)` / `expire_transient_entries(turn)` / `clear_all_transient_entries()`

**Functions:**

- **`init_state() -> GameState`**
  - Factory function to create new game state with defaults

- **`apply_state_tag(state: GameState, tag: dict)`**
  - Apply `[[STATE]]` tags from AI responses
  - Updates emotion and relationship (+/-1 delta)
  - Syncs with main character state

- **`extract_state_tag(reply: str)`**
  - Extract and remove `[[STATE]]{...}[[/STATE]]` from AI reply
  - Returns: `(clean_text, dict or None)`
  - Uses regex + JSON parsing

---

#### `backend/app/engine/gameplay.py` (172 lines)

**Purpose:** Gameplay mechanics (time, movement, win detection)

**Functions:**

- **`word_count(s: str) -> int`** (lines 12-14)
  - Count words in text for time calculation

- **`sanitize_location(loc: str) -> str`** (lines 17-20)
  - Remove HTML tags and newlines from location string

- **`manifest_mode(state) -> str`** (lines 23-47)
  - Determine ghost manifestation state
  - Returns "materialize" (inside apartment) or "whisper" (outside)
  - Based on location string matching keywords from story config

- **`advance_time(state, player_text: str)`** (lines 50-117)
  - **CRITICAL FUNCTION** - Updates game time
  - Time delta = `base_turn_mins + ceil(word_count * mins_per_word)`
  - Detects movement commands: `go to <place>` or `move to <place>`
  - **World graph integration:**
    - If world runtime exists, uses authoritative graph-based travel
    - Resolves destination ID, calls `travel_resolver.resolve()`
    - Updates location_id, syncs world clock
  - **Legacy fallback:** Free-text location updates if no world graph

- **`_normalize_token(s: str) -> str`** (lines 120-121)
  - Normalize string for location matching (lowercase, alphanumeric only)

- **`_resolve_destination_id(world_graph, place: str) -> Optional[str]`** (lines 124-140)
  - Resolve user-provided place string to location ID
  - Tries exact ID match, then name match (normalized)

- **`win_condition_detected(text: str, state) -> bool`** (lines 143-159)
  - Win condition detection using regex patterns from story config
  - Default patterns: "i am the mastermind", "i ordered/arranged/hired", etc.

---

#### `backend/app/engine/story_loader.py` (280 lines)

**Purpose:** Load story JSON files from disk

**Functions:**

- **`load_story(story_id: str) -> dict`** (lines 6-62)
  - Load story JSON by ID
  - **Search paths:**
    1. `backend/app/stories/<story_id>.json`
    2. `backend/app/stories/<subdir>/<story_id>.json`
  - **BOM handling:** Strips UTF-8 BOM (`\ufeff`) from file content
  - **Debug logging:** Prints path info, directory listings
  - Returns empty dict on error

---

#### `backend/app/engine/prompt_builder.py` (628 lines)

**Purpose:** Construct AI prompts with game context

**Functions:**

- **`_jlog(obj: dict)`** (lines 17-28)
  - JSON logging to stdout (Railway logs)
  - Adds timestamp, catches exceptions

- **`_truncate(s: str, n: int = 500) -> str`** (lines 31-35)
  - Truncate string for logging

- **`_format_memory_block(retrieved_chunks: list, character_name: str = "") -> str`** (lines 38-68)
  - Format knowledge retrieval results into canonical memory block
  - Injects at top of system prompt with authority markers
  - Format: `- (type) [chunk_id] text`

- **`system_prompt(state: GameState, is_first_turn: bool = False, memory_block: str = "") -> str`** (lines 71-244)
  - **CRITICAL FUNCTION** - Build system prompt for AI
  - **Sections:**
    1. Output style rules (italics, bold, quotes)
    2. Character behavior rules (no forced missions, conversational)
    3. Language & honorific rules (Korean terms, relationship thresholds)
    4. Passive world context (ghost backstory, suspects)
    5. Player-related details (names, gender, location)
    6. Internal game state (emotion, relationship)
    7. Canonical memory block (knowledge retrieval)
    8. First-turn guidance (optional, soft hints)
    9. Required final line (`[[STATE]]` tag)
  - **Name handling:** Never speaks player name unless `Character_has_learned_name: True`
  - **Honorifics:** Only allowed if relationship ≥ 2

- **`build_messages(state: GameState, log: list, user_msg: str, knowledge_chunks: list)`** (lines 247-317)
  - **CRITICAL FUNCTION** - Build full chat completion message array
  - **Steps:**
    1. Detect casual Korean usage in user message
    2. Format knowledge chunks into memory block
    3. Generate system prompt with memory
    4. Trim conversation log to last `MEMORY_TURNS - 2` turns
    5. Add header with game state (time, location, manifestation, emotion, relationship)
    6. Append current user message
  - **Returns:** `[{role: "system", content: ...}, ...conversation..., {role: "user", content: ...}]`

---

#### `backend/app/engine/time_utils.py` (50 lines)

**Purpose:** World time formatting

**Classes:**

- **`WorldTimestamp`** (lines 8-15) **[DATACLASS, FROZEN]**
  - **Fields:**
    - `iso: str` - ISO-like timestamp for logging
    - `display: str` - Human-friendly timestamp for UI

**Classes:**

- **`WorldTimeFormatter`** (lines 18-49)
  - Static class for time computation
  - **Constants:**
    - `DEFAULT_START = "2025-01-01 08:00 PM"`
  - **Methods:**
    - `compute(cls, start_dt_str: str, minute: int) -> WorldTimestamp` (lines 29-49)
      - Convert game minutes to real timestamp
      - Parses start datetime (supports 12-hour and 24-hour formats)
      - Adds `minute` offset
      - Returns formatted timestamp (both ISO and display)

---

#### `backend/app/engine/extractors/location_extractor.py` (277 lines)

**Purpose:** NLP-based location intent extraction using OpenAI

**Enums:**

- **`LocationIntent`** (lines 14-16)
  - `NONE` - No movement intent
  - `MOVE` - Explicit movement command

**Classes:**

- **`LocationExtraction`** (lines 19-24) **[DATACLASS, FROZEN]**
  - **Fields:**
    - `intent: LocationIntent`
    - `destination_id: Optional[str]`
    - `confidence: float`
    - `destination_text: str` (raw user text)

- **`LocationExtractor`** (lines 27-276)
  - Lightweight LLM-based location intent classifier
  - **Constructor:** `__init__(self, model: str | None = None)` (lines 34-35)

  **Methods:**

  - **`_should_attempt(self, user_msg: str) -> bool`** (lines 37-87) **[ASYNC]**
    - Use LLM to classify if message has movement intent
    - Returns `true` for explicit commands ("go to X", "move to X")
    - Returns `false` for questions/hypotheticals ("can we go to X?")

  - **`_build_locations_block(world_graph) -> str`** (lines 89-107) **[STATIC]**
    - Build prompt text listing all known locations
    - Format: `- location_id: location_name`
    - Limited to 80 locations

  - **`_parse_json(content: str) -> LocationExtraction`** (lines 109-138) **[STATIC]**
    - Parse LLM JSON response into LocationExtraction
    - Handles: `{intent: "MOVE"|"NONE", destination_id: "...", confidence: 0.0-1.0}`

  - **`extract(self, user_msg: str, *, world_graph, knowledge_chunks: list = None) -> LocationExtraction`** (lines 140-276) **[ASYNC]**
    - **MAIN METHOD** - Extract location intent and destination ID
    - **Steps:**
      1. Call `_should_attempt()` to classify intent
      2. If no intent, return `NONE` immediately
      3. Build locations block from world graph
      4. Add knowledge context (top 5 chunks) for disambiguation
      5. Call OpenAI API with JSON schema
      6. Parse response into LocationExtraction
    - **Knowledge integration:** Uses retrieved chunks to disambiguate ("old workplace" → "EDAM entertainment")

---

#### `backend/app/engine/world/world_loader.py` (101 lines)

**Purpose:** Load world JSON into runtime objects

**Classes:**

- **`WorldLoadResult`** (lines 18-24) **[DATACLASS, FROZEN]**
  - **Fields:**
    - `world_graph: WorldGraph`
    - `world_clock: WorldClock`
    - `travel_resolver: TravelResolver`
    - `seed: int`
    - `probabilities: dict`

- **`WorldLoader`** (lines 27-100)
  - Static class for loading world JSON

  **Methods:**

  - **`load_from_file(cls, filepath: str, seed: int = 0) -> WorldLoadResult`** (lines 30-84) **[CLASSMETHOD]**
    - Load world JSON from file path
    - **Parsing:**
      - Locations: `{id, name, description, tags, allows_phone, is_transit}`
      - Edges: `{from, to, minutes, is_transit, blocked}`
      - Time config: `{start_minute}`
      - Probabilities: exposure probabilities for travel
    - **Creates:**
      - `WorldGraph` with locations/edges
      - `WorldClock` with start time
      - `TravelRules` with seeded RNG
      - `ExposureResolver` with probabilities
      - `TravelResolver` combining all components

  - **`try_load_story_world(cls, story_id: str, stories_dir: str, seed: int = 0) -> Optional[WorldLoadResult]`** (lines 86-100) **[CLASSMETHOD]**
    - Convenience method to auto-load world file
    - Tries: `stories/<story_id>_world.json` or `stories/<subdir>/<story_id>_world.json`
    - Returns `None` if no world file exists

---

#### `backend/app/engine/world/graph.py` (71 lines)

**Purpose:** Authoritative world graph data structure

**Classes:**

- **`EdgeList`** (lines 12-18) **[DATACLASS, FROZEN]**
  - Immutable container for edges
  - **Fields:** `edges: Tuple[PathEdge, ...]`
  - **Methods:** `to_tuple() -> Tuple[PathEdge, ...]`

- **`WorldGraph`** (lines 21-71)
  - Topological world graph
  - **Private fields:**
    - `_locations: Dict[str, Location]`
    - `_outgoing: Dict[str, Tuple[PathEdge, ...]]`

  **Methods:**

  - **`locations`** property (lines 28-31)
    - Returns mapping of location_id → Location

  - **`add_location(self, location: Location)`** (lines 34-39)
    - Add location node to graph
    - Raises `ValueError` if duplicate ID

  - **`add_edge(self, edge: PathEdge)`** (lines 41-48)
    - Add directed edge to graph
    - Validates from/to IDs exist
    - Raises `KeyError` if unknown location

  - **`get_location(self, location_id: str | LocationId) -> Location`** (lines 50-52)
    - Retrieve location by ID

  - **`get_neighbors(self, from_id: str | LocationId)`** (lines 55-61)
    - Compatibility helper for unit tests
    - Returns list of outgoing edges

  - **`get_outgoing(self, from_id: str | LocationId) -> EdgeList`** (lines 62-64)
    - Get all outgoing edges from location

  - **`get_direct_edges(self, from_id: str | LocationId, to_id: str | LocationId) -> EdgeList`** (lines 66-70)
    - Get all direct edges between two locations

---

#### `backend/app/engine/world/location.py` (37 lines)

**Purpose:** Location data structure

**Classes:**

- **`Location`** (lines 10-36) **[DATACLASS, FROZEN]**
  - Atomic place in the world (no nesting)
  - **Fields:**
    - `id: Union[LocationId, str]`
    - `name: str` (required, non-empty)
    - `description: str`
    - `tags: Union[Tuple[str, ...], Iterable[str]]`
    - `allows_phone: bool = True`
    - `is_transit: bool = False` (subway, bus, etc.)

  **Methods:**

  - **`__post_init__(self)`** (lines 27-36)
    - Coerce `id` from str to LocationId
    - Coerce `tags` to immutable tuple
    - Validate name is non-empty

---

#### `backend/app/engine/world/edge.py` (34 lines)

**Purpose:** Edge data structure

**Classes:**

- **`PathEdge`** (lines 10-33) **[DATACLASS, FROZEN]**
  - Directed edge between two locations
  - **Fields:**
    - `from_id: Union[LocationId, str]`
    - `to_id: Union[LocationId, str]`
    - `minutes: int` (travel duration, must be positive)
    - `is_transit: bool = False`
    - `blocked: bool = False` (impassable)

  **Methods:**

  - **`__post_init__(self)`** (lines 24-33)
    - Coerce from_id/to_id to LocationId
    - Validate minutes is int and positive

---

#### `backend/app/engine/world/clock.py` (41 lines)

**Purpose:** World time management

**Classes:**

- **`WorldClock`** (lines 7-40) **[DATACLASS]**
  - Single source of truth for world time
  - **Private fields:** `_minute: int = 0`

  **Methods:**

  - **`__init__(self, start_minute: int = 0)`** (lines 18-23)
    - Initialize clock with start time
    - Validates start_minute ≥ 0

  - **`minute`** property (lines 25-27)
    - Get current minute

  - **`now_minute(self) -> int`** (lines 29-30)
    - Get current minute (alias)

  - **`advance(self, minutes: int)`** (lines 32-33)
    - Advance clock by minutes (alias for advance_minutes)

  - **`advance_minutes(self, minutes: int)`** (lines 35-40)
    - Advance clock by minutes
    - Validates minutes is int and positive

---

#### `backend/app/engine/world/travel_resolver.py` (115 lines)

**Purpose:** Execute travel according to rules

**Classes:**

- **`TravelRequest`** (lines 13-17) **[DATACLASS, FROZEN]**
  - **Fields:** `from_id: LocationId`, `to_id: LocationId`

- **`TravelTiming`** (lines 20-28) **[DATACLASS, FROZEN]**
  - **Fields:** `exit_minutes: int = 1`
  - **Methods:** `validate()` - Validates exit_minutes > 0

- **`TravelResult`** (lines 31-42) **[DATACLASS, FROZEN]**
  - Result of travel execution
  - **Fields:** `request`, `route`, `exposure`, `start_minute`, `end_minute`
  - **Methods:** `minutes_spent() -> int`

- **`TravelResolver`** (lines 45-115)
  - Executes travel with invariants: time always advances, route is seeded

  **Methods:**

  - **`__init__(self, graph, clock, rules, exposure_resolver, timing)`** (lines 54-69)
    - Initialize resolver with all components

  - **`execute(self, request: TravelRequest) -> TravelResult`** (lines 71-95)
    - **MAIN METHOD** - Execute travel
    - **Steps:**
      1. Record start time
      2. Resolve route (direct or one-intermediate)
      3. Advance clock for EXIT (1 minute)
      4. Advance clock for TRANSIT (sum of edge minutes)
      5. Roll exposure packet
      6. Return TravelResult

  - **`resolve(self, from_id: str, to_id: str)`** (lines 97-112)
    - Compatibility API for unit tests
    - Converts str IDs to LocationId
    - Returns TravelExposure (legacy format)

  - **`current_minute(self) -> int`** (lines 114-115)
    - Get current world time

---

#### `backend/app/engine/world/travel_rules.py` (214 lines)

**Purpose:** Seeded route selection and pathfinding

**Classes:**

- **`TravelSegment`** (lines 16-19) **[DATACLASS, FROZEN]**
  - One hop in a route
  - **Fields:** `edge: PathEdge`

- **`TravelRoute`** (lines 22-37) **[DATACLASS, FROZEN]**
  - Resolved route from A to B
  - **Fields:** `from_id`, `to_id`, `segments: Tuple[TravelSegment, ...]`

  **Methods:**

  - **`intermediate_id(self)`** (lines 30-34)
    - Returns LocationId of intermediate node (if 2-hop route), else None

  - **`total_transit_minutes(self) -> int`** (lines 36-37)
    - Sum of all edge minutes

- **`TravelRules`** (lines 40-213)
  - Rule-driven, seeded route selection
  - **Uses seeded RNG** for deterministic forks

  **Methods:**

  - **`__init__(self, seed: int)`** (lines 51-54)
    - Initialize with seeded random.Random instance

  - **`choose_edge(self, edges)`** (lines 57-67)
    - Choose unblocked edge using seeded RNG
    - Raises RuntimeError if no edges available

  - **`resolve_route(self, graph, from_id, to_id) -> TravelRoute`** (lines 70-110)
    - **MAIN METHOD** - Resolve route
    - **Priority:**
      1. **Direct route** (A→B)
      2. **One-intermediate route** (A→C→B)
      3. **Multi-hop BFS** (A→C→D→...→B, up to 10 hops)
      4. **Dynamic edge fallback** (creates temporary edge if islands detected)

  - **`_find_path_bfs(self, graph, from_id, to_id) -> Tuple[PathEdge, ...] | None`** (lines 112-145)
    - BFS pathfinding for multi-hop routes
    - Max 10 hops to prevent infinite loops
    - Returns tuple of edges or None

  - **`_log_island_error(self, from_id, to_id, graph)`** (lines 147-186)
    - Log giant error message when disconnected islands detected
    - Lists all locations, suggests fixes

  - **`_create_dynamic_edge(self, from_id, to_id) -> PathEdge`** (lines 188-203)
    - Create temporary in-memory edge with random travel time (8-25 min)
    - Marked as transit route
    - **WARNING:** This is a fallback for broken world graphs

  - **`_inject_dynamic_edge(self, graph, edge)`** (lines 205-212)
    - Inject edge directly into graph's internal structure
    - In-memory only, doesn't persist

---

#### `backend/app/engine/world/exposure.py` (150 lines)

**Purpose:** Travel exposure system (what AI can see during travel)

**Classes:**

- **`ExposureConfig`** (lines 10-34) **[DATACLASS, FROZEN]**
  - Probability slots for travel exposure
  - **Fields:**
    - `p_exit_A: float` - Probability of exit event at origin
    - `p_pass_C: float` - Probability of passing intermediate
    - `p_event_at_C: float` - Probability of event at intermediate
    - `p_enter_B: float` - Probability of enter event at destination
    - `p_describe_B: float` - Probability of describing destination

  **Methods:**

  - **`validate(self)`** (lines 25-34)
    - Validates all probabilities are in [0,1]

- **`ExposurePacket`** (lines 37-46) **[DATACLASS, FROZEN]**
  - Canonical v2 exposure packet
  - **Fields:** `exit_event_at_A`, `pass_intermediate_C`, `event_at_C`, `enter_event_at_B`, `describe_B`, `intermediate_id`

- **`TravelExposure`** (lines 49-73) **[DATACLASS, FROZEN]**
  - Backwards-compatible exposure shape
  - **Fields:** `exit_event`, `pass_intermediate`, `event_at_intermediate`, `enter_event`, `describe_destination`, `intermediate_id`

  **Methods:**

  - **`from_packet(cls, packet: ExposurePacket) -> TravelExposure`** (lines 64-73) **[CLASSMETHOD]**
    - Convert ExposurePacket to TravelExposure

- **`ExposureResolver`** (lines 76-149)
  - Produces exposure packets using seeded RNG

  **Methods:**

  - **`__init__(self, config, seed, *, probs)`** (lines 79-108)
    - Initialize with config or probs dict
    - Back-compat: accepts `probs={...}` instead of config

  - **`_rng(self)`** (lines 110-113)
    - Returns seeded random.Random instance

  - **`roll(self, intermediate_id: Optional[LocationId])`** (lines 115-149)
    - **MAIN METHOD** - Generate exposure packet
    - **Logic:**
      - If no intermediate: `pass_C=False`, `event_C=False`
      - If intermediate: roll `p_pass_C`, then conditionally `p_event_at_C`
      - Always roll: `p_exit_A`, `p_enter_B`, `p_describe_B`
    - Returns TravelExposure (legacy format)

---

#### `backend/app/engine/world/ids.py` (24 lines)

**Purpose:** Strong typing for location IDs

**Classes:**

- **`LocationId`** (lines 8-23) **[DATACLASS, FROZEN]**
  - Newtype wrapper for location ID strings
  - **Fields:** `value: str`

  **Methods:**

  - **`__post_init__(self)`** (lines 13-18)
    - Validates value is non-empty string

  - **`__str__(self) -> str`** (lines 20-21)
    - Returns string representation

  - **`__eq__(self, other) -> bool`** (lines 23-23)
    - Equality comparison (also compares with raw strings)

---

#### `backend/app/engine/world/world_json.py` (87 lines)

**Purpose:** World JSON schema validation

(File not read in detail, but likely contains JSON schema definitions and validators)

---

#### `backend/app/knowledge/runtime/index_service.py` (79 lines)

**Purpose:** Thread-safe cache for retrieval index bundles

**Classes:**

- **`IndexService`** (lines 12-78)
  - Static class managing index bundle cache
  - **Class variables:**
    - `_lock: Lock` - Thread safety lock
    - `_bundles: Dict[str, CharacterIndexBundle]` - Loaded bundles cache
    - `_active_character_id: ContextVar[str]` - Per-request character ID

  **Methods:**

  - **`set_active_character(cls, character_id: str)`** (lines 27-29) **[CLASSMETHOD]**
    - Set active character ID for current context

  - **`get_active_character(cls) -> str`** (lines 30-52) **[CLASSMETHOD]**
    - Get active character ID
    - **Priority:**
      1. Per-request context variable
      2. `KNOWLEDGE_CHARACTER_ID` environment variable
      3. Auto-detection: if exactly one character dir exists, use it

  - **`get(cls, character_id: Optional[str] = None) -> CharacterIndexBundle`** (lines 55-72) **[CLASSMETHOD]**
    - **MAIN METHOD** - Get or load character index bundle
    - Thread-safe with double-checked locking
    - Raises RuntimeError if no character ID configured

  - **`reset_for_tests(cls)`** (lines 74-78) **[CLASSMETHOD]**
    - Clear cache for testing

---

#### `backend/app/knowledge/runtime/load_indexes.py` (214 lines)

**Purpose:** Load pre-built knowledge artifacts

**Constants:**

- **`REQUIRED_FILES`** (lines 14-20): `("chunks.jsonl", "bm25.json", "faiss.index", "embeddings.npy", "build_info.json")`

**Functions:**

- **`_load_chunks_jsonl(path: Path) -> List[dict]`** (lines 23-30)
  - Load chunks from JSONL file
  - One JSON object per line

- **`_has_required(d: Path) -> bool`** (lines 33-34)
  - Check if directory has all required files

- **`_missing_required(d: Path) -> List[str]`** (lines 37-38)
  - List missing required files

- **`_copy_tree(src: Path, dst: Path, filenames: Tuple[str, ...])`** (lines 41-47)
  - Copy specific files from src to dst
  - Creates dst if needed

- **`_dir_listing(d: Path, max_items: int = 80) -> str`** (lines 50-68)
  - Generate directory listing for debugging
  - Shows file names and sizes

- **`_find_tmp_cache_dir(character_id: str) -> Path | None`** (lines 71-86)
  - Find pytest-created cache directory in /tmp
  - Returns most recently modified matching directory

- **`_try_autobuild_into(persist_root: Path) -> str`** (lines 89-113)
  - Attempt to build indexes into persist_root
  - Skipped if `KNOWLEDGE_PERSIST_ROOT` is set
  - Temporarily sets env vars, calls `build_index.main()`

- **`load_character_indexes(character_id: str) -> CharacterIndexBundle`** (lines 116-213)
  - **MAIN FUNCTION** - Load retrieval artifacts
  - **Search priority:**
    1. Persistent cache (`/data/knowledge_cache` or `KNOWLEDGE_CACHE_DIR`)
    2. Image-bundled artifacts (`backend/app/knowledge/characters/`)
    3. Autobuild attempt (if `/data` deployment)
    4. Pytest tmp artifacts
  - **Loading:**
    - Chunks from JSONL
    - BM25 index from JSON
    - FAISS index from binary
  - **Raises RuntimeError** with detailed diagnostics if artifacts missing

---

#### `backend/app/knowledge/runtime/retrieve.py` (86 lines)

**Purpose:** Hybrid BM25 + FAISS retrieval

**Functions:**

- **`retrieve_knowledge(query: str, k_bm25: int = 8, k_faiss: int = 8, k_final: int = 8) -> Tuple[List[Dict], Dict]`** (lines 8-85)
  - **MAIN FUNCTION** - Hybrid knowledge retrieval
  - **Returns:** `(retrieved_chunks, debug_info)`

  **Hybrid mode** (if BM25 and FAISS available):
  1. Tokenize query, compute BM25 scores
  2. Get top-k BM25 results
  3. Embed query, search FAISS index
  4. Get top-k FAISS results
  5. Fuse results using reciprocal rank fusion
  6. Return top-k final chunks

  **Fallback mode** (if no indexes):
  1. Simple keyword scoring over chunk text
  2. Boost for song-related queries
  3. Return top-k scored chunks

---

#### `backend/app/knowledge/build/build_index.py` (281 lines)

**Purpose:** Build knowledge indexes (offline process)

**Constants:**

- **`REQUIRED_FIELDS`** (line 24): `{"chunk_id", "character_id", "type", "text", "confidence"}`
- **`FORCE_REBUILD`** (line 26): From env `FORCE_REBUILD_INDEX=1`
- **`CACHE_ROOT`** (line 32): From env `KNOWLEDGE_CACHE_DIR` or default `backend/app/knowledge`

**Functions:**

- **`_get_paths(character_dirname: str)`** (lines 39-61)
  - Return dict of all artifact paths for a character

- **`_purge_existing_cache(char_dir: Path)`** (lines 68-76)
  - Remove existing cache (FORCE_REBUILD mode only)

- **`validate_chunks(chunks: list[dict])`** (lines 79-85)
  - Validate chunks have required fields

- **`load_previous_build(build_info_path: Path) -> Optional[Dict]`** (lines 88-92)
  - Load previous build_info.json if exists

- **`artifacts_exist(paths: dict) -> bool`** (lines 95-101)
  - Check if all artifacts exist

- **`should_skip(prev, new_fingerprint: str) -> bool`** (lines 104-122)
  - Determine if rebuild can be skipped
  - Checks: FORCE_REBUILD, fingerprint match, artifacts exist

- **`_ensure_cached_chunks(paths: dict)`** (lines 125-131)
  - Copy chunks.jsonl to cache if needed

- **`_atomic_write_json(path: Path, obj: dict)`** (lines 133-137)
  - Atomic file write using temp file + replace

- **`_atomic_save_npy(path: Path, arr: np.ndarray)`** (lines 140-144)
  - Atomic numpy array save

- **`main(character_dirname: str | None = None)`** (lines 151-277)
  - **MAIN FUNCTION** - Build indexes for character
  - **Steps:**
    1. Get paths for character
    2. Purge cache if FORCE_REBUILD
    3. Load + validate chunks
    4. Get embedder info
    5. Compute fingerprint
    6. Check if can skip rebuild
    7. Generate embeddings
    8. Build FAISS index
    9. Build BM25 index
    10. Verify BM25 schema
    11. Write build_info.json
    12. Verify artifacts exist

---

#### `backend/app/knowledge/contracts/index_bundle.py` (18 lines)

**Purpose:** Data structure for loaded indexes

**Classes:**

- **`CharacterIndexBundle`** (lines 9-17) **[DATACLASS, FROZEN]**
  - Container for all loaded retrieval artifacts
  - **Fields:**
    - `character_id: str`
    - `artifact_dir: Path`
    - `chunks: List[dict]`
    - `chunk_ids: List[str]`
    - `bm25: Any` (rank_bm25.BM25Okapi instance)
    - `faiss_index: Any` (faiss.Index instance)

---

### FRONTEND FILE

---

#### `frontend/index.html` (568 lines)

**Purpose:** Single-page terminal-style web application

**Structure:**

1. **HTML Head** (lines 1-131)
   - iOS safety stubs for Firefox globals
   - Dynamic base href detection (beta vs production)
   - Apple mobile web app meta tags
   - Inline CSS styling (terminal dark theme, box components, toolbar)

2. **HTML Body** (lines 133-144)
   - `#term` - Terminal output display
   - `#ime` - Hidden input field (for mobile IME)
   - `#toolbar` - Fixed bottom toolbar (input display + buttons)
   - `#errbox` - Error message display

3. **JavaScript** (lines 146-567)

**JavaScript Functions:**

- **Environment Detection** (lines 148-161)
  - Detects beta vs production based on hostname/path
  - Sets `API_BASE` URL accordingly

- **Error Handling** (lines 163-170)
  - `showErr(msg)` - Display error in UI
  - Global error handlers for JS errors and promise rejections

- **State Management** (lines 178-186)
  - `state` object: `{mode, sid, turns, story, gender, playerName, storyMeta}`

- **UI Utilities:**

  - **`scrollToBottom(force)`** (lines 192-195)
    - Auto-scroll terminal to bottom

  - **`newPrompt()`** (lines 197-210)
    - Create input prompt line with cursor

  - **`removeInputLine()`** (lines 212-216)
    - Remove input line from display

  - **`unlockInput()`** (lines 218-222)
    - Unlock input after bot response

  - **`escapeHTML(s)`** (lines 224-231)
    - Escape HTML entities

  - **`formatInline(md)`** (lines 233-239)
    - Format markdown: `**bold**`, `*italic*`, `"quotes"`

  - **`normalizeNewlines(text)`** (lines 242-246)
    - Convert literal `\n` strings to real newlines

  - **`toRichHTML(text)`** (lines 248-256)
    - Convert text to rich HTML with paragraph breaks

  - **`writeLine(text, cls)`** (lines 258-265)
    - Write line to terminal with CSS class

  - **`writeBox(title, body)`** (lines 267-283)
    - Write styled box (for instructions)

  - **`renderBuffer()`** (lines 285-289)
    - Update input buffer and ghost input display

- **Typewriter Effect:**

  - **`TYPE_DEFAULT`**, **`TYPE_OPENER`** (lines 292-293)
    - Typing speed configs

  - **`typewrite(text, cls, opt)`** (lines 295-319)
    - **Returns Promise** - Animated typewriter effect
    - Displays text gradually with configurable speed

- **Version Management:**

  - **`setHeader()`** (lines 325-332)
    - Update terminal header with version

  - **`loadVersion()`** (lines 334-348)
    - Fetch `version.json` and display version

- **Backend Communication:**

  - **`fetchStoryMeta(storyId)`** (lines 350-357)
    - Fetch story metadata from `/api/story/{id}`

  - **`renderInstructions(meta)`** (lines 359-377)
    - Render game rules/instructions box

  - **`send(msg, done, typeOpt)`** (lines 379-418)
    - **MAIN API CALL** - Send message to `/api/chat`
    - Uses XMLHttpRequest
    - Handles response with typewriter effect
    - Calls `done` callback when complete

- **Game Flow:**

  - **`commitLine()`** (lines 420-444)
    - Handle Enter key / send button
    - Routes to appropriate handler based on state.mode

  - **`showMenu()`** (lines 446-472)
    - Display story selection menu
    - Fetches `/api/stories` dynamically

  - **`handleMenu(line)`** (lines 474-502)
    - Handle story selection
    - Fetches story meta
    - Transitions to name input

  - **`handleName(line)`** (lines 504-516)
    - Handle name input
    - Validates and sanitizes name
    - Transitions to gender input

  - **`handleGender(line)`** (lines 518-538)
    - Handle gender input (F/M)
    - Sends `__cmd_newgame__` command
    - Transitions to chat mode

- **Event Handlers** (lines 540-558)
  - `ime.input` → renderBuffer
  - `term.click/touchstart` → focus input
  - `document.keydown` (Enter) → commitLine
  - `enterBtn.click` → commitLine
  - `bkspBtn.click` → backspace

- **Initialization** (lines 560-563)
  - Load version
  - Show menu
  - Focus input

---

## Redundant & Unused Code Analysis

### UNUSED/REDUNDANT CODE FINDINGS:

#### 1. **`backend/app/api/game_logic.py`** - ENTIRELY UNUSED
   - **Lines:** 1-12
   - **Issue:** Placeholder endpoint that returns only a message
   - **Evidence:** No references found in frontend or other backend files
   - **Recommendation:** **DELETE THIS FILE** or implement actual game logic

#### 2. **Duplicate `_log()` functions**
   - **Location 1:** `backend/app/api/chat.py` (lines 145-149)
   - **Location 2:** `backend/app/engine/prompt_builder.py` as `_jlog()` (lines 17-28)
   - **Issue:** Two nearly identical JSON logging functions
   - **Recommendation:** **Consolidate** into a shared logging utility module

#### 3. **Duplicate `_truncate()` functions**
   - **Location 1:** `backend/app/api/chat.py` (lines 152-154) - 6000 char default
   - **Location 2:** `backend/app/engine/prompt_builder.py` (lines 31-35) - 500 char default
   - **Issue:** Nearly identical truncation functions
   - **Recommendation:** **Consolidate** into shared utility

#### 4. **Redundant Turkish i handling in `frontend/index.html`**
   - **Location:** Lines 8-13 (Firefox-only global stub)
   - **Issue:** `window.__firefox__.playlistLongPress` stub has no actual usage
   - **Status:** Removed in generic cleanup refactor.

#### 5. **`state.evidence` field — REMOVED**
   - **Status:** Removed. Was murder-mystery-specific dead code, never populated or accessed.

#### 6. **Potentially redundant `normalizeNewlines()` in frontend**
   - **Location:** `frontend/index.html` lines 242-246
   - **Issue:** Handles literal `\n` strings, but these should already be real newlines from JSON
   - **Recommendation:** **Verify** if story JSONs actually contain literal `\\n` strings; if not, simplify

#### 7. **`state.allow_casual_korean` field**
   - **Location:** `backend/app/engine/state.py` line 135
   - **Issue:** Set in `prompt_builder.py` but never actually read/used anywhere
   - **Recommendation:** **Remove** or implement the feature

#### 8. **Backward compatibility dict methods in GameState**
   - **Location:** `backend/app/engine/state.py` lines 146-150
   - **Methods:** `__getitem__`, `__setitem__`
   - **Issue:** Maintained for "backward compatibility" but no legacy code actually uses dict access
   - **Evidence:** All code uses direct attribute access (`.location`, `.emotion`)
   - **Recommendation:** Keep for safety, but mark as **deprecated** in docstring

#### 9. **`IndexService.reset_for_tests()`**
   - **Location:** `backend/app/knowledge/runtime/index_service.py` lines 75-78
   - **Issue:** Test-only method included in production code
   - **Recommendation:** Keep (harmless), but add docstring marking as test utility

#### 10. **Debug print statements**
   - **Location:** `backend/app/engine/story_loader.py` lines 17-18, 29, 35, 50
   - **Issue:** Multiple DEBUG print statements for path debugging
   - **Recommendation:** **Replace** with proper logging (use `_log()` or Python logging module)

#### 11. **Duplicate name patterns**
   - **Location:** `backend/app/api/chat.py` lines 269-277
   - **Issue:** 7 regex patterns for name extraction, many overlapping
   - **Recommendation:** **Consolidate** to 4-5 patterns; remove redundant ones

#### 12. **`router.php` in backend root**
   - **Location:** `backend/router.php`
   - **Issue:** PHP deployment router (legacy) - codebase is now Python
   - **Recommendation:** **DELETE** if no longer using PHP deployment

#### 13. **Unused `world_json.py`**
   - **Location:** `backend/app/engine/world/world_json.py`
   - **Issue:** File imported in world_loader but content not examined; may contain unused schema validators
   - **Recommendation:** **Review** and remove unused schema definitions

#### 14. **Unused Chinese mode flag persistence**
   - **Location:** `backend/app/api/chat.py` session store
   - **Issue:** `chinese_mode` flag persists across resets but is lost on server restart (in-memory)
   - **Recommendation:** **Document** as session-scoped only, or persist to DB

#### 15. **Redundant `state.turns` tracking**
   - **Location:** Multiple places increment turns counter
   - **Issue:** Used for "first turn" detection but not actually needed (can use `len(log)`)
   - **Recommendation:** Keep for explicitness, but **document** alternative

---

### FALSE POSITIVES (Code that LOOKS unused but IS used):

- **`state.last_travel_from_id`, `state.last_travel_to_id`, `state.last_travel_exposure`** - Used for travel history/debugging
- **`state.knowledge_character_id`** - Used by IndexService for routing retrieval
- **`state.world_runtime`** - Used conditionally when world graph is loaded
- **`state.location_id`** - Used for graph-based movement (distinct from `state.location` string)

---

## Architecture Diagrams

### System Architecture (High-Level)

```
┌────────────────────────────────────────────────────────────────┐
│                        USER (Browser)                          │
└────────────────────────────────────────────────────────────────┘
                               │
                               │ HTTPS
                               ▼
┌────────────────────────────────────────────────────────────────┐
│                     FRONTEND (index.html)                      │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │  Terminal UI │  │ Input Handler│  │  Typewriter  │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Story Menu   │  │ Game State   │  │ API Client   │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
└────────────────────────────────────────────────────────────────┘
                               │
                               │ POST /api/chat
                               │ GET /api/stories
                               │ GET /api/story/{id}
                               ▼
┌────────────────────────────────────────────────────────────────┐
│              BACKEND (FastAPI + Uvicorn)                       │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    API LAYER                             │ │
│  │  /chat  /stories  /story/{id}  /health  /echo           │ │
│  └──────────────────────────────────────────────────────────┘ │
│                          │                                     │
│                          ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                 GAME ENGINE                              │ │
│  │                                                          │ │
│  │  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │ │
│  │  │   State    │  │   Gameplay   │  │ Prompt Builder │  │ │
│  │  │ Management │  │  (Time/Move) │  │  (AI Context)  │  │ │
│  │  └────────────┘  └──────────────┘  └────────────────┘  │ │
│  │                                                          │ │
│  │  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │ │
│  │  │   World    │  │   Location   │  │ Story Loader   │  │ │
│  │  │   Graph    │  │  Extractor   │  │     (JSON)     │  │ │
│  │  └────────────┘  └──────────────┘  └────────────────┘  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                          │                                     │
│                          ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              KNOWLEDGE SYSTEM                            │ │
│  │                                                          │ │
│  │  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │ │
│  │  │   Index    │  │  Hybrid      │  │    BM25 +      │  │ │
│  │  │  Service   │  │  Retrieval   │  │    FAISS       │  │ │
│  │  └────────────┘  └──────────────┘  └────────────────┘  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                          │                                     │
│                          ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                 EXTERNAL APIS                            │ │
│  │           OpenAI API (GPT-4o-mini)                       │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
                               │
                               │ File System
                               ▼
┌────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                             │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Story JSONs  │  │ World Graphs │  │   Knowledge  │        │
│  │  (stories/)  │  │ (*_world.json)│  │  (chunks.jsonl│       │
│  └──────────────┘  └──────────────┘  │  bm25.json    │        │
│                                       │  faiss.index) │        │
│                                       └──────────────┘        │
└────────────────────────────────────────────────────────────────┘
```

---

### Data Flow (Single User Turn)

```
┌─────────────┐
│    USER     │
│ Types "go   │
│ to office"  │
└──────┬──────┘
       │
       │ 1. POST /api/chat
       ▼
┌──────────────────────────────────────────────────────────────┐
│  chat_handler() in api/chat.py                               │
│                                                              │
│  2. Retrieve Session                                         │
│     ┌─────────────────────────────────┐                     │
│     │ SESSIONS[session_id]            │                     │
│     │ → {state, log, debug_mode}      │                     │
│     └─────────────────────────────────┘                     │
│                                                              │
│  3. advance_time(state, "go to office")                     │
│     ┌──────────────────────────────────────────────────┐   │
│     │ gameplay.py                                       │   │
│     │ • word_count() → delta = base + words * rate     │   │
│     │ • detect movement: regex match "go to <place>"   │   │
│     │ • call travel_resolver.resolve(from, to)         │   │
│     │   ┌──────────────────────────────────────────┐   │   │
│     │   │ TravelResolver (world/)                  │   │   │
│     │   │ • TravelRules.resolve_route()            │   │   │
│     │   │   → Direct or 1-intermediate or BFS      │   │   │
│     │   │ • WorldClock.advance(exit + transit)     │   │   │
│     │   │ • ExposureResolver.roll()                │   │   │
│     │   │   → {exit_event, pass_C, event_C, ...}   │   │   │
│     │   └──────────────────────────────────────────┘   │   │
│     │ • Update state.location_id, state.location       │   │
│     └──────────────────────────────────────────────────┘   │
│                                                              │
│  4. retrieve_knowledge("go to office")                      │
│     ┌──────────────────────────────────────────────────┐   │
│     │ knowledge/runtime/retrieve.py                     │   │
│     │ • IndexService.get(character_id)                  │   │
│     │   → Load BM25 + FAISS indexes                     │   │
│     │ • BM25 search → top 8 results                     │   │
│     │ • FAISS search → top 8 results                    │   │
│     │ • Hybrid fusion (reciprocal rank)                 │   │
│     │ • Return top 8 fused chunks                       │   │
│     └──────────────────────────────────────────────────┘   │
│                                                              │
│  5. _LOCATION_EXTRACTOR.extract(msg, world_graph, chunks)   │
│     ┌──────────────────────────────────────────────────┐   │
│     │ extractors/location_extractor.py                  │   │
│     │ • _should_attempt() → LLM classify intent         │   │
│     │ • Build locations block from world graph          │   │
│     │ • Add knowledge chunks for disambiguation         │   │
│     │ • Call OpenAI API with JSON schema                │   │
│     │ • Parse: {intent: MOVE, destination_id: "office"} │   │
│     └──────────────────────────────────────────────────┘   │
│                                                              │
│  6. build_messages(state, log, "go to office", chunks)      │
│     ┌──────────────────────────────────────────────────┐   │
│     │ prompt_builder.py                                 │   │
│     │ • system_prompt(state, memory_block)              │   │
│     │   ┌───────────────────────────────────────────┐   │   │
│     │   │ System Prompt Sections:                   │   │   │
│     │   │ • Output style rules (bold/italic)        │   │   │
│     │   │ • Character behavior (no forced mission)  │   │   │
│     │   │ • Language rules (Korean honorifics)      │   │   │
│     │   │ • Canonical memory block (retrieved)      │   │   │
│     │   │ • Game state (emotion, relationship)      │   │   │
│     │   │ • Required [[STATE]] tag format           │   │   │
│     │   └───────────────────────────────────────────┘   │   │
│     │ • Add conversation history (last 16 turns)        │   │
│     │ • Add user message with game state header         │   │
│     └──────────────────────────────────────────────────┘   │
│                                                              │
│  7. Call OpenAI API                                          │
│     ┌──────────────────────────────────────────────────┐   │
│     │ POST https://api.openai.com/v1/chat/completions  │   │
│     │ Model: gpt-4o-mini                                │   │
│     │ Temperature: 0.8                                  │   │
│     │ Max Tokens: 512                                   │   │
│     └──────────────────────────────────────────────────┘   │
│                                                              │
│  8. Process Response                                         │
│     ┌──────────────────────────────────────────────────┐   │
│     │ • extract_state_tag(reply)                        │   │
│     │   → Remove [[STATE]]{emotion, rel_delta}          │   │
│     │ • sanitize_korean_terms()                         │   │
│     │   → Remove "oppa"/"unnie" if rel < 2              │   │
│     │ • apply_state_tag(state, tag)                     │   │
│     │   → Update state.emotion, state.relationship      │   │
│     │ • win_condition_detected()                           │   │
│     │   → Check win condition regex patterns            │   │
│     │ • _translate_to_chinese() (if mode enabled)       │   │
│     └──────────────────────────────────────────────────┘   │
│                                                              │
│  9. Update Session & Return                                  │
│     ┌──────────────────────────────────────────────────┐   │
│     │ • log.append(user_msg, assistant_reply)           │   │
│     │ • sess["log"] = log[-8:]   (trim to 8 turns)      │   │
│     │ • return {reply, usage, character}                │   │
│     └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
       │
       │ 10. Response JSON
       ▼
┌─────────────┐
│  FRONTEND   │
│ Typewriter  │
│   Effect    │
└─────────────┘
```

---

### World Graph System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      WORLD GRAPH SYSTEM                        │
└────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     INITIALIZATION (Startup)                    │
│                                                                 │
│  story_loader.load_story("iu_murder_mystery")                  │
│           ↓                                                     │
│  WorldLoader.try_load_story_world("iu_murder_mystery")         │
│           ↓                                                     │
│  WorldLoader.load_from_file("iu_murder_mystery_world.json")    │
│           ↓                                                     │
│  Parse JSON → WorldLoadResult:                                 │
│    • WorldGraph (locations + edges)                            │
│    • WorldClock (time tracker)                                 │
│    • TravelResolver (movement executor)                        │
│    • TravelRules (pathfinding + seeded RNG)                    │
│    • ExposureResolver (event probabilities)                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    RUNTIME (Movement Turn)                      │
│                                                                 │
│  User: "go to Gangnam Station"                                 │
│           ↓                                                     │
│  gameplay.advance_time(state, "go to Gangnam Station")         │
│           ↓                                                     │
│  Detect movement regex: ✓                                      │
│           ↓                                                     │
│  _resolve_destination_id(world_graph, "Gangnam Station")       │
│           ↓                                                     │
│  Normalize: "gangnamstation" → Match: "gangnam_station"        │
│           ↓                                                     │
│  travel_resolver.resolve(from_id, to_id)                       │
│           ↓                                                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              TravelResolver.execute()                     │ │
│  │                                                           │ │
│  │  1. TravelRules.resolve_route(from, to)                  │ │
│  │     ├─ Try direct edge: A → B                            │ │
│  │     ├─ Try 1-intermediate: A → C → B                     │ │
│  │     ├─ Try BFS pathfinding: A → C → D → ... → B         │ │
│  │     └─ Fallback: Create dynamic edge (island detected!)  │ │
│  │                                                           │ │
│  │  2. WorldClock.advance(exit_time)  # 1 minute            │ │
│  │                                                           │ │
│  │  3. For each edge in route:                              │ │
│  │        WorldClock.advance(edge.minutes)                  │ │
│  │                                                           │ │
│  │  4. ExposureResolver.roll(intermediate_id)               │ │
│  │     ├─ Roll p_exit_A (0.2)                               │ │
│  │     ├─ Roll p_pass_C (0.5) if intermediate exists        │ │
│  │     ├─ Roll p_event_at_C (0.25) if passed intermediate   │ │
│  │     ├─ Roll p_enter_B (0.2)                              │ │
│  │     └─ Roll p_describe_B (0.6)                           │ │
│  │                                                           │ │
│  │  5. Return TravelResult:                                 │ │
│  │     • route: [edge1, edge2, ...]                         │ │
│  │     • exposure: {exit_event, pass_C, event_C, ...}       │ │
│  │     • start_minute: 47                                   │ │
│  │     • end_minute: 62  (15 min travel)                    │ │
│  └───────────────────────────────────────────────────────────┘ │
│           ↓                                                     │
│  Update state:                                                 │
│    • state.location_id = "gangnam_station"                     │
│    • state.location = "Gangnam Station" (display name)         │
│    • state.minute = 62  (synced from WorldClock)               │
│    • state.last_travel_from_id = "nonhyeon_dong"               │
│    • state.last_travel_to_id = "gangnam_station"               │
│    • state.last_travel_exposure = <ExposurePacket>             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    GRAPH STRUCTURE EXAMPLE                      │
│                                                                 │
│  WorldGraph:                                                    │
│    Locations:                                                   │
│      • "nonhyeon_dong" (Nonhyeon-dong Officetel)               │
│      • "gangnam_station" (Gangnam Station)                     │
│      • "edam_entertainment" (EDAM Entertainment Building)      │
│      • "subway_line2" (Subway Line 2) [transit node]           │
│                                                                 │
│    Edges:                                                       │
│      nonhyeon_dong → gangnam_station (15 min, direct)          │
│      nonhyeon_dong → subway_line2 (5 min, transit)             │
│      subway_line2 → gangnam_station (10 min, transit)          │
│      gangnam_station → edam_entertainment (8 min, direct)      │
│                                                                 │
│  Example Routes:                                                │
│    nonhyeon_dong → gangnam_station:                            │
│      Option 1: Direct (15 min)                                 │
│      Option 2: Via subway_line2 (5 + 10 = 15 min)              │
│      → TravelRules chooses via seeded RNG                      │
└─────────────────────────────────────────────────────────────────┘
```

---

### Knowledge Retrieval System

```
┌────────────────────────────────────────────────────────────────┐
│              KNOWLEDGE SYSTEM ARCHITECTURE                     │
└────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  BUILD PHASE (Offline, Pre-Deployment)          │
│                                                                 │
│  Source: knowledge/characters/<char_dir>/knowledge.json         │
│           ↓                                                     │
│  Manual chunking → chunks.jsonl                                │
│           ↓                                                     │
│  build_index.py (auto-discovers character dirs)                │
│           ↓                                                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  1. Load chunks.jsonl                                     │ │
│  │     • Validate required fields:                           │ │
│  │       {chunk_id, character_id, type, text, confidence}    │ │
│  │                                                           │ │
│  │  2. Generate embeddings (sentence-transformers)           │ │
│  │     • Model: all-MiniLM-L6-v2                             │ │
│  │     • Normalize vectors (for cosine similarity)           │ │
│  │     • Save: embeddings.npy                                │ │
│  │                                                           │ │
│  │  3. Build FAISS index                                     │ │
│  │     • Type: FlatIP (inner product, exact search)          │ │
│  │     • Add normalized embeddings                           │ │
│  │     • Save: faiss.index                                   │ │
│  │                                                           │ │
│  │  4. Build BM25 index                                      │ │
│  │     • Tokenizer: regex_v1 (lowercase, alphanumeric)       │ │
│  │     • Parameters: k1=1.5, b=0.75                          │ │
│  │     • Save: bm25.json (includes corpus, IDF, avgdl)       │ │
│  │                                                           │ │
│  │  5. Compute fingerprint                                   │ │
│  │     • Hash: chunks file + embedder info + configs         │ │
│  │     • Save: build_info.json                               │ │
│  └───────────────────────────────────────────────────────────┘ │
│           ↓                                                     │
│  Artifacts (deployed in Docker image or persistent cache):     │
│    • chunks.jsonl                                              │
│    • embeddings.npy                                            │
│    • faiss.index                                               │
│    • bm25.json                                                 │
│    • build_info.json                                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  RUNTIME PHASE (Per Request)                    │
│                                                                 │
│  User query: "Tell me about the character"                      │
│           ↓                                                     │
│  retrieve_knowledge(query, k_bm25=8, k_faiss=8, k_final=8)     │
│           ↓                                                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  IndexService.get(active_character_id)                    │ │
│  │           ↓                                                │ │
│  │  Thread-safe cache lookup                                 │ │
│  │           ↓                                                │ │
│  │  Cache miss? → load_character_indexes(character_id)       │ │
│  │                 • Load chunks.jsonl                        │ │
│  │                 • Load bm25.json → BM25Okapi instance      │ │
│  │                 • Load faiss.index → FAISS index           │ │
│  │                 → CharacterIndexBundle                     │ │
│  │           ↓                                                │ │
│  │  Cache hit! → Return bundle                               │ │
│  └───────────────────────────────────────────────────────────┘ │
│           ↓                                                     │
│  bundle = {chunks, bm25, faiss_index}                          │
│           ↓                                                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              HYBRID RETRIEVAL                             │ │
│  │                                                           │ │
│  │  1. BM25 Lexical Search                                   │ │
│  │     • Tokenize: ["tell", "me", "about", "iu", "songs"]    │ │
│  │     • BM25 score all 150 chunks                           │ │
│  │     • Top 8 by score:                                     │ │
│  │       [idx: 42, score: 8.7],                              │ │
│  │       [idx: 89, score: 7.2], ...                          │ │
│  │                                                           │ │
│  │  2. FAISS Semantic Search                                 │ │
│  │     • Embed query → 384-dim vector                        │ │
│  │     • FAISS search (inner product, k=8)                   │ │
│  │     • Top 8 by similarity:                                │ │
│  │       [idx: 42, score: 0.87],                             │ │
│  │       [idx: 103, score: 0.81], ...                        │ │
│  │                                                           │ │
│  │  3. Reciprocal Rank Fusion                                │ │
│  │     • BM25 ranks: {42: 1, 89: 2, ...}                     │ │
│  │     • FAISS ranks: {42: 1, 103: 2, ...}                   │ │
│  │     • Fused score = 1/(60+rank1) + 1/(60+rank2)           │ │
│  │     • idx 42: 1/61 + 1/61 = 0.0328 (appears in both!)     │ │
│  │     • idx 89: 1/62 + 0 = 0.0161                           │ │
│  │     • idx 103: 0 + 1/62 = 0.0161                          │ │
│  │     • Sort by fused score → Top 8 final results           │ │
│  └───────────────────────────────────────────────────────────┘ │
│           ↓                                                     │
│  Retrieved chunks (8):                                         │
│    [                                                           │
│      {                                                         │
│        "chunk_id": "char_song_01",                             │
│        "character_id": "<character_id>",                       │
│        "type": "discography",                                  │
│        "text": "Example song text for character retrieval...", │
│        "confidence": "high"                                    │
│      },                                                        │
│      ...                                                       │
│    ]                                                           │
│           ↓                                                     │
│  Format into memory block → inject into system prompt          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary Statistics

### Backend

| Metric | Count |
|--------|-------|
| Total Python files | 48 |
| Total lines of code | ~5,000+ |
| API endpoints | 6 |
| Dataclasses | 15+ |
| Functions/methods | 120+ |

### Frontend

| Metric | Count |
|--------|-------|
| Total HTML/JS files | 1 |
| Total lines of code | 568 |
| JavaScript functions | 25+ |

### Issues Found

| Category | Count |
|----------|-------|
| Unused files | 1 |
| Redundant functions | 4 pairs |
| Unused fields | 3 |
| Debug statements | 5+ |
| Potential simplifications | 6 |

---

## Recommendations

### Immediate Actions (High Priority)

1. **DELETE** `backend/app/api/game_logic.py` (unused endpoint)
2. **CONSOLIDATE** duplicate logging functions into `backend/app/utils/logging.py`
3. **REPLACE** DEBUG print statements with proper logging
4. **REMOVE** unused `router.php` if no longer deploying with PHP
5. ~~**DOCUMENT** unused `state.evidence` field~~ — DONE (removed)

### Medium Priority

6. **Refactor** name extraction regex patterns (consolidate overlapping patterns)
7. **Review** `world_json.py` for unused schema validators
8. **Add docstrings** marking backward-compatibility methods as deprecated
9. **Verify** if `normalizeNewlines()` is actually needed in frontend

### Low Priority (Code Quality)

10. **Add type hints** to remaining untyped functions
11. **Standardize** error handling (some functions return empty dict, others raise)
12. **Extract constants** for magic numbers (e.g., 60 in reciprocal rank fusion)
13. **Add integration tests** for end-to-end gameplay flow

---

## Conclusion

This MVP Chat codebase is **well-structured** with clear separation of concerns:
- **API layer** handles HTTP/REST
- **Engine layer** implements game logic
- **Knowledge layer** provides AI context retrieval
- **World layer** manages graph-based movement

**Code quality** is generally high with:
- Comprehensive dataclasses
- Type hints in newer code
- Thread-safe caching
- Atomic file operations
- Detailed logging

**Main issues** are:
- Minor code duplication (logging, truncation)
- Dead v2 modules and evidence field removed; codebase is now generic
- Inconsistent error handling patterns
- Debug print statements mixed with production code

Overall, the codebase is **production-ready** with room for polish. The hybrid knowledge retrieval system and world graph mechanics are particularly sophisticated.

---

**End of Documentation**
