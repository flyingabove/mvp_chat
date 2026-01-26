# MVPChat Codebase Documentation

Complete reference for all backend and frontend files, methods, and dependencies in the StoriesChat narrative game engine.

**Last Updated**: Post-location-extractor-refactor (LLM-driven instead of regex)

---

## Table of Contents

- [Backend API Layer](#backend-api-layer)
- [Backend Engine Layer](#backend-engine-layer)
  - [Game State & Management](#game-state--management)
  - [Story Loading & Gameplay](#story-loading--gameplay)
  - [Location & Movement](#location--movement)
  - [World System](#world-system)
- [Backend Knowledge Layer](#backend-knowledge-layer)
  - [Retrieval Runtime](#retrieval-runtime)
  - [Index Building](#index-building)
- [Backend Infrastructure](#backend-infrastructure)
  - [Configuration](#configuration)
  - [Middleware](#middleware)
  - [Entry Point](#entry-point)
- [Frontend](#frontend)
- [Unused Code](#unused-code)

---

## Backend API Layer

### `backend/app/api/chat.py` – Main Chat Endpoint

**Purpose**: Orchestrates entire game turn flow including command parsing, session management, location extraction, knowledge retrieval, LLM invocation, and state updates.

**Key Variables**:
- `SESSIONS: Dict[str, tuple]` – In-memory session storage (session_id → (state, message_log, debug_mode))
- `_LOCATION_EXTRACTOR: LocationExtractor` – Global singleton for location extraction

#### Functions

**`_box(title: str, content: str, width: int = 60) -> str`**
- **Signature**: Returns ASCII box containing title and multi-line content
- **Purpose**: Creates formatted ASCII box for displaying debug info or system messages
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`_log(event: dict)`**
- **Signature**: Takes event dictionary
- **Purpose**: JSON logging to stdout for Railway Deploy Logs; enables traceability and monitoring
- **Calls**: None
- **Called By**: `chat_handler`, `_truncate`
- **Used**: Yes

**`_truncate(s: str, n: int = 6000) -> str`**
- **Signature**: Returns truncated string
- **Purpose**: Safely truncates strings to max length for logging without overflow
- **Calls**: `_log`
- **Called By**: `chat_handler`, `_log`
- **Used**: Yes

**`extract_user_name_from_text(text: str, gender: str) -> tuple[str, bool]`**
- **Signature**: Returns (name, confirmed)
- **Purpose**: Regex-based pattern matching to detect "my name is X" statements; confirms names using regex patterns
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`handle_name_confirmation(state: MurderGameState, user_text: str) -> bool`**
- **Signature**: Returns whether confirmation succeeded
- **Purpose**: Handles yes/no response to name confirmation prompts
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`apply_placeholders(text: str, state: MurderGameState) -> str`**
- **Signature**: Returns text with placeholders substituted
- **Purpose**: Replaces template strings like `{{PLAYER_NAME}}`, `{{HONORIFIC}}` in story text with actual values
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`sanitize_korean_terms(text: str, state: MurderGameState) -> str`**
- **Signature**: Returns filtered text
- **Purpose**: Relationship-based filtering of Korean address terms (removes formal terms when relationship is high)
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`get_session(session_id: str) -> tuple`**
- **Signature**: Returns (state, log, debug_mode)
- **Purpose**: Session retrieval/creation; initializes new session if not found
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`chat_handler(data: dict) -> dict`** [FastAPI POST endpoint]
- **Signature**: `@router.post('/chat')` – Returns dict with reply, over, debug_info
- **Purpose**: Main chat endpoint orchestrating entire turn flow
- **Flow**:
  1. Extract session_id, message, story_id from request
  2. Get or create session
  3. Parse commands (`__cmd_reset__`, `__cmd_newgame__:`)
  4. Handle debug toggle (`[D]`, `[DEBUG]`)
  5. Load story and initialize state if new game
  6. Extract user name if needed
  7. Canonicalize movement intents via location extractor
  8. Retrieve knowledge chunks via hybrid BM25+FAISS
  9. Build LLM prompt
  10. Call OpenAI API
  11. Parse state tags from response
  12. Update world time
  13. Check win condition (confession)
  14. Format debug info box if debug_mode
  15. Return reply + game state flags
- **Calls**: 
  - `get_session`
  - `load_story`
  - `init_state`
  - `WorldLoader.load_from_file`
  - `WorldLoader.try_load_story_world`
  - `apply_placeholders`
  - `CharacterState` constructor
  - `IndexService.set_active_character`
  - `retrieve_knowledge`
  - `LocationExtractor.extract`
  - `build_messages`
  - `extract_state_tag`
  - `sanitize_korean_terms`
  - `apply_state_tag`
  - `confession_detected`
  - `WorldTimeFormatter.compute`
  - `_box`
  - `_log`
  - `_truncate`
- **Called By**: FastAPI router (HTTP POST)
- **Used**: Yes (core endpoint)

---

### `backend/app/api/stories.py` – Story List Endpoint

**Purpose**: Enables frontend to dynamically build story menu from available story JSON files.

#### Functions

**`_stories_dir() -> Path`**
- **Signature**: Returns Path object
- **Purpose**: Returns path to `backend/app/stories` directory
- **Calls**: None
- **Called By**: `list_stories`
- **Used**: Yes

**`list_stories()` [FastAPI GET endpoint]**
- **Signature**: `@router.get('/stories')` – Returns list of story IDs
- **Purpose**: API endpoint that enables frontend to build dynamic story menu from JSON files
- **Calls**: `_stories_dir`
- **Called By**: FastAPI router
- **Used**: Yes

---

### `backend/app/api/story.py` – Story Metadata Endpoint

**Purpose**: Returns metadata for a specific story (title, goal, rules) for UI display.

#### Functions

**`get_story_meta(story_id: str)` [FastAPI GET endpoint]**
- **Signature**: `@router.get('/story/{story_id}')` – Returns story metadata dict
- **Purpose**: Returns metadata for a specific story (title, goal, rules) for UI display
- **Calls**: `load_story`
- **Called By**: FastAPI router
- **Used**: Yes

---

### `backend/app/api/health.py` – Health Check Endpoint

**Purpose**: Liveness probe for deployment; indicates server health and build info.

#### Functions

**`health()` [FastAPI GET endpoint]**
- **Signature**: `@router.get('/health')` – Returns health status dict
- **Purpose**: Returns server health status with version, timestamp, and working directory
- **Calls**: None
- **Called By**: FastAPI router
- **Used**: Yes

---

### `backend/app/api/echo.py` – Debug Echo Endpoint

**Purpose**: Debug endpoint for request inspection; mirrors HTTP method, raw body, and parsed JSON.

#### Functions

**`echo(request: Request)` [FastAPI POST endpoint]**
- **Signature**: `@router.post('/echo')` – Returns echo dict
- **Purpose**: Debug endpoint that echoes back request method, raw body, and parsed JSON
- **Calls**: None
- **Called By**: FastAPI router
- **Used**: Yes (debug only)

---

### `backend/app/api/game_logic.py` – Future Game Logic

**Purpose**: Placeholder for future game logic endpoints.

#### Functions

**`game_logic()` [FastAPI GET endpoint]**
- **Signature**: `@router.get('/game-logic')` – Returns placeholder
- **Purpose**: Placeholder endpoint for future game logic features
- **Calls**: None
- **Called By**: FastAPI router
- **Used**: **No (unused)**

---

## Backend Engine Layer

### Game State & Management

#### `backend/app/engine/state.py` – State Dataclasses

**Purpose**: Define immutable dataclasses for game state, character state, and user state.

#### Dataclasses

**`UserState`**
- **Fields**: `formal_name: str`, `display_name: str`, `gender: str`
- **Purpose**: Player metadata (formal name for endings, display name for dialogue, gender for pronouns)

**`CharacterState`**
- **Fields**: `key: str`, `name: str`, `role: str`, `emotion: str`, `relationship: int`
- **Purpose**: NPC state (key for story lookup, emotion/relationship dynamics)

**`MurderGameState`**
- **Fields**:
  - `story_cfg: dict` – Loaded story JSON
  - `player_name: str`, `gender: str` – Player info
  - `characters: Dict[str, CharacterState]` – NPCs
  - `user: UserState` – Player metadata
  - `emotion: str`, `relationship: int` – Main character dynamics
  - `location_id: str`, `location: str` – World position (graph key + display text)
  - `minute: int` – World time in minutes
  - `turns: int` – Turn counter
  - `over: bool` – Game end flag
  - `world_runtime: Optional[WorldLoadResult]` – Loaded world graph/clock/resolver
  - `world_start_datetime: str` – ISO datetime for world time calculation
  - `knowledge_character_id: str` – Character dir for retrieval
  - `main_character_id: str` – Main NPC key for story
  - `last_assistant_guess_name: Optional[str]` – For name confirmation
  - `user_loc_prev: Optional[str]` – Previous location (for delta calculation)
- **Purpose**: Complete game session state container

#### Functions

**`init_state() -> MurderGameState`**
- **Signature**: Creates and returns new state
- **Purpose**: Factory function to initialize a fresh MurderGameState for a new game session
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`apply_state_tag(state: MurderGameState, tag: dict)`**
- **Signature**: Mutates state in-place
- **Purpose**: Parses and applies emotion and relationship delta changes from LLM output to game state
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`extract_state_tag(reply: str)`**
- **Signature**: Returns tuple (cleaned_text, state_dict or None)
- **Purpose**: Extracts JSON state tag from end of LLM response (`[[STATE: {...}]]`); returns cleaned text and parsed dict
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

---

### Story Loading & Gameplay

#### `backend/app/engine/story_loader.py` – Story Loading

**Purpose**: Load story JSON configuration files from disk.

#### Functions

**`load_story(story_id: str) -> dict`**
- **Signature**: Returns story config dict
- **Purpose**: Loads story configuration JSON from disk; handles encoding issues (BOM); returns empty dict on error
- **Calls**: None
- **Called By**: `chat_handler`, `story.py`
- **Used**: Yes

---

#### `backend/app/engine/gameplay.py` – Time & Win Condition

**Purpose**: Manage turn timing, character manifestation state, and detect game end.

#### Functions

**`word_count(s: str) -> int`**
- **Signature**: Returns word count
- **Purpose**: Counts whitespace-separated words in a string
- **Calls**: None
- **Called By**: `advance_time`
- **Used**: Yes

**`sanitize_location(loc: str) -> str`**
- **Signature**: Returns sanitized location
- **Purpose**: Removes HTML tags and normalizes whitespace in location strings
- **Calls**: None
- **Called By**: `advance_time`
- **Used**: Yes

**`manifest_mode(state) -> str`**
- **Signature**: Returns "manifests" or "whispers"
- **Purpose**: Checks if player location contains apartment keywords to determine ghost visibility (story rule-based)
- **Calls**: None
- **Called By**: `prompt_builder`
- **Used**: Yes

**`advance_time(state: MurderGameState, player_text: str) -> None`**
- **Signature**: Mutates state.minute in-place
- **Purpose**: Updates world time based on message length; travels via world_runtime.travel_resolver if location changed
- **Calls**: 
  - `word_count`
  - `sanitize_location`
  - `world_runtime.travel_resolver.resolve` (if location changed)
- **Called By**: `chat_handler`
- **Used**: Yes

**`confession_detected(text: str, state) -> bool`**
- **Signature**: Returns boolean
- **Purpose**: Checks if LLM response contains confession patterns from story config to trigger game end
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

---

#### `backend/app/engine/prompt_builder.py` – LLM Prompt Construction

**Purpose**: Build OpenAI message list with system prompt, memory, and retrieved context.

#### Functions

**`_jlog(obj: dict)`**
- **Signature**: Writes to stdout
- **Purpose**: JSON-line logging to stdout; shows up in Railway Deploy Logs
- **Calls**: None
- **Called By**: `build_messages`
- **Used**: Yes

**`_truncate(s: str, max_len: int = 6000) -> str`**
- **Signature**: Returns truncated string
- **Purpose**: Safely truncates strings to prevent token explosion in LLM calls
- **Calls**: None
- **Called By**: `build_messages`
- **Used**: Yes

**`_format_memory_block(retrieved_chunks: List[dict], character_name: str) -> str`**
- **Signature**: Returns formatted memory text block
- **Purpose**: Formats retrieved knowledge chunks as canon facts for LLM system context
- **Calls**: None
- **Called By**: `build_messages`
- **Used**: Yes

**`build_messages(state: MurderGameState, log: List[tuple], user_msg: str, retrieved_chunks: List[dict]) -> List[dict]`**
- **Signature**: Returns OpenAI message list
- **Purpose**: Constructs full message list with:
  1. System prompt (character role, world context, manifestation state)
  2. Memory block (retrieved chunks as canon)
  3. Conversation history (last N turns)
- **Calls**: `_format_memory_block`, `_jlog`, `_truncate`
- **Called By**: `chat_handler`
- **Used**: Yes

---

### Location & Movement

#### `backend/app/engine/extractors/location_extractor.py` – LLM-Powered Location Extraction

**Purpose**: Extract movement intent and destination location from natural language using two-stage LLM pipeline.

**Architecture**: 
- First LLM call: Classify if message expresses movement intent
- Second LLM call: Extract destination_id from world graph locations
- Returns structured `LocationExtraction` result

#### Enums

**`LocationIntent`** (Enum)
- Values: `NONE`, `MOVE`
- Purpose: Intent classification result

#### Dataclasses

**`LocationExtraction`**
- **Fields**: 
  - `intent: LocationIntent` – MOVE or NONE
  - `destination_id: Optional[str]` – Location ID if movement detected
  - `confidence: float` – Confidence 0.0-1.0
  - `destination_text: Optional[str]` – Display name of destination
- **Purpose**: Structured result of location extraction

#### Classes

**`LocationExtractor`**

**`__init__(self, model: str | None = None)`**
- **Signature**: Initializes extractor
- **Purpose**: Initializes location extractor with optional model override
- **Calls**: None
- **Called By**: Module initialization
- **Used**: Yes

**`async _should_attempt(self, user_msg: str) -> bool`** [CHANGED: LLM-driven]
- **Signature**: Returns boolean
- **Purpose**: Async LLM call to classify if message expresses movement intent; handles natural language variations like "actually I'm heading to X", "let's go to X"
- **Calls**: OpenAI API (async httpx)
- **Called By**: `extract`
- **Used**: Yes

**`_build_locations_block(self, world_graph) -> str`**
- **Signature**: Returns formatted text block
- **Purpose**: Formats known locations from world graph as prompt text for LLM
- **Calls**: None
- **Called By**: `extract`
- **Used**: Yes

**`_parse_json(self, content: str) -> Optional[LocationExtraction]`**
- **Signature**: Returns parsed LocationExtraction or None
- **Purpose**: Parses JSON response from LLM into LocationExtraction dataclass
- **Calls**: None
- **Called By**: `extract`
- **Used**: Yes

**`async extract(self, user_msg: str, *, world_graph) -> LocationExtraction`**
- **Signature**: Returns LocationExtraction result
- **Purpose**: Main method to extract location intent and destination from user message
- **Flow**:
  1. Check if attempt should be made via LLM classification
  2. Build location list prompt
  3. Call LLM to extract destination
  4. Parse and return structured result
- **Calls**: `_should_attempt`, `_build_locations_block`, `_parse_json`
- **Called By**: `chat_handler`
- **Used**: Yes

**Debug Logging**: Extensive JSON logging at each stage (called, skipped, calling_llm, llm_response, result) for Railway Deploy Logs visibility.

---

### World System

#### `backend/app/engine/world/world_loader.py` – World Parsing & Loading

**Purpose**: Parse world JSON and instantiate runtime graph, clock, and travel resolver.

#### Dataclasses

**`WorldLoadResult`**
- **Fields**: 
  - `graph: WorldGraph`
  - `clock: WorldClock`
  - `travel_resolver: TravelResolver`
- **Purpose**: Container for loaded world runtime objects

#### Classes

**`WorldLoader`**

**`@classmethod load_from_file(cls, filepath: str, seed: int = 0) -> WorldLoadResult`**
- **Signature**: Returns WorldLoadResult
- **Purpose**: Loads flat World JSON into runtime classes (graph, clock, resolver)
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`@classmethod try_load_story_world(cls, story_id: str, stories_dir: str, seed: int = 0) -> Optional[WorldLoadResult]`**
- **Signature**: Returns WorldLoadResult or None
- **Purpose**: Convenience: load `backend/app/stories/<story_id>_world.json` if present; returns None if file not found
- **Calls**: `load_from_file`
- **Called By**: `chat_handler`
- **Used**: Yes

---

#### `backend/app/engine/world/world_json.py` – World JSON Parsing

**Purpose**: Parse and validate world definition JSON.

#### Dataclasses

**`WorldDefinition`**
- **Fields**: `locations: List[Location]`, `edges: List[PathEdge]`
- **Purpose**: Parsed world structure

#### Classes

**`WorldDefinitionLoader`**

**`from_json_str(self, json_text: str) -> WorldDefinition`**
- **Signature**: Returns WorldDefinition
- **Purpose**: Parses JSON string into WorldDefinition
- **Calls**: `from_dict`
- **Called By**: External callers
- **Used**: Yes

**`from_dict(self, data: Dict[str, Any]) -> WorldDefinition`**
- **Signature**: Returns WorldDefinition
- **Purpose**: Parses dict into WorldDefinition with validation
- **Calls**: None
- **Called By**: `from_json_str`
- **Used**: Yes

---

#### `backend/app/engine/world/graph.py` – World Graph Structure

**Purpose**: Container for locations and edges; provides lookup and traversal methods.

#### Dataclasses

**`EdgeList`**
- **Fields**: Immutable tuple of PathEdge objects
- **Purpose**: Immutable list of edges

**Methods**:
- `to_tuple() -> Tuple[PathEdge, ...]` – Returns immutable tuple of edges

**`LocationId`** (Type alias)
- Maps string location IDs to structured type

#### Classes

**`WorldGraph`**

**`__init__(self) -> None`**
- **Signature**: Initializes empty graph
- **Purpose**: Initializes empty world graph
- **Calls**: None
- **Called By**: WorldGraph instantiation
- **Used**: Yes

**`locations` (property)**
- **Signature**: Returns `Dict[str, Location]`
- **Purpose**: Provides access to all locations in the graph
- **Calls**: None
- **Called By**: Loaders, tests, chat_handler
- **Used**: Yes

**`add_location(self, location: Location) -> None`**
- **Signature**: Mutates graph in-place
- **Purpose**: Adds location to graph
- **Calls**: None
- **Called By**: WorldLoader
- **Used**: Yes

**`add_edge(self, edge: PathEdge) -> None`**
- **Signature**: Mutates graph in-place
- **Purpose**: Adds edge to graph
- **Calls**: None
- **Called By**: WorldLoader
- **Used**: Yes

**`get_location(self, location_id: str | LocationId) -> Optional[Location]`**
- **Signature**: Returns Location or None
- **Purpose**: Looks up location by ID
- **Calls**: None
- **Called By**: Travel resolver, tests
- **Used**: Yes

**`get_outgoing(self, from_id: str | LocationId) -> EdgeList`**
- **Signature**: Returns EdgeList
- **Purpose**: Returns list of outgoing edges from a location
- **Calls**: None
- **Called By**: travel_rules
- **Used**: Yes

**`get_direct_edges(self, from_id: str | LocationId, to_id: str | LocationId) -> EdgeList`**
- **Signature**: Returns EdgeList
- **Purpose**: Returns list of direct edges between two specific locations
- **Calls**: None
- **Called By**: travel_rules
- **Used**: Yes

---

#### `backend/app/engine/world/location.py` – Location Definition

**Purpose**: Define world locations with metadata (tags, phone access, transit status).

#### Dataclasses

**`Location`**
- **Fields**: 
  - `id: str` – Unique location ID
  - `name: str` – Display name
  - `description: str` – Long description
  - `tags: Tuple[str, ...]` – Category tags
  - `allows_phone: bool = False` – Can use phone here
  - `is_transit: bool = False` – Transit location (doesn't allow phone)
- **Methods**:
  - `__post_init__()` – Coerces string IDs to LocationId, normalizes tags tuple, validates name
- **Purpose**: Represents a single location in the world

---

#### `backend/app/engine/world/edge.py` – Movement Edges

**Purpose**: Define traversal routes between locations.

#### Dataclasses

**`PathEdge`**
- **Fields**: 
  - `from_id: str | LocationId`
  - `to_id: str | LocationId`
  - `minutes: int` – Travel time
  - `is_transit: bool = False` – Whether this is a transit route
  - `blocked: bool = False` – Whether this edge is currently blocked
- **Methods**:
  - `__post_init__()` – Coerces string IDs to LocationId objects and validates edge properties
- **Purpose**: Represents single path between two locations

---

#### `backend/app/engine/world/clock.py` – World Time

**Purpose**: Track in-world time for travel and narrative progression.

#### Classes

**`WorldClock`**

**`__init__(self, start_minute: int = 0)`**
- **Signature**: Initializes clock
- **Purpose**: Initializes world clock with starting minute
- **Calls**: None
- **Called By**: WorldClock instantiation
- **Used**: Yes

**`minute` (property)**
- **Signature**: Returns int
- **Purpose**: Returns current world time in minutes
- **Calls**: None
- **Called By**: advance_time, chat_handler, tests
- **Used**: Yes

**`now_minute(self) -> int`**
- **Signature**: Returns int
- **Purpose**: Returns current world time (alias for minute property)
- **Calls**: None
- **Called By**: travel_resolver
- **Used**: Yes

**`advance(self, minutes: int) -> None`**
- **Signature**: Mutates clock in-place
- **Purpose**: Advances world time by specified minutes (alias for advance_minutes)
- **Calls**: `advance_minutes`
- **Called By**: advance_time
- **Used**: Yes

**`advance_minutes(self, minutes: int) -> None`**
- **Signature**: Mutates clock in-place
- **Purpose**: Advances world time by specified minutes with validation
- **Calls**: None
- **Called By**: `advance`, travel_resolver
- **Used**: Yes

---

#### `backend/app/engine/world/travel_rules.py` – Travel Logic

**Purpose**: Determine valid travel routes and resolve path finding.

#### Dataclasses

**`TravelSegment`**
- **Fields**: `from_id: LocationId`, `to_id: LocationId`, `minutes: int`, `blocked: bool`
- **Purpose**: Single segment of a travel route

**`TravelRoute`**
- **Fields**: `segments: List[TravelSegment]`
- **Purpose**: Complete multi-segment route from source to destination

#### Classes

**`TravelRules`**

**`__init__(self, graph: WorldGraph, seed: int = 0)`**
- **Signature**: Initializes rules
- **Purpose**: Initializes travel rules with graph reference and RNG seed
- **Calls**: None
- **Called By**: TravelResolver
- **Used**: Yes

**`choose_edge(self, edges) -> Optional[PathEdge]`**
- **Signature**: Returns edge or None
- **Purpose**: Chooses an unblocked edge deterministically using seeded RNG
- **Calls**: None
- **Called By**: `resolve_route`
- **Used**: Yes

**`resolve_route(self, graph: WorldGraph, from_id: LocationId, to_id: LocationId) -> TravelRoute`**
- **Signature**: Returns TravelRoute
- **Purpose**: Resolves path from source to destination (direct edge or with one intermediate hop)
- **Calls**: `choose_edge`
- **Called By**: TravelResolver.execute
- **Used**: Yes

---

#### `backend/app/engine/world/travel_resolver.py` – Travel Execution

**Purpose**: Execute travel requests, compute timing and exposure.

#### Dataclasses

**`TravelRequest`**
- **Fields**: `from_id: str`, `to_id: str`
- **Purpose**: Travel request parameters

**`TravelTiming`**
- **Fields**: `exit_minutes: int`, `base_minutes: int`
- **Methods**: `validate()` – Validates that exit_minutes is positive
- **Purpose**: Timing configuration for travel

**`TravelResult`**
- **Fields**: `route: TravelRoute`, `total_minutes: int`, `exposure: TravelExposure`
- **Purpose**: Result of travel execution

#### Classes

**`TravelResolver`**

**`__init__(self, graph: WorldGraph, clock: WorldClock, rules: TravelRules, exposure_resolver: ExposureResolver, timing: TravelTiming | None = None)`**
- **Signature**: Initializes resolver
- **Purpose**: Initializes travel resolver with graph, clock, rules, and exposure
- **Calls**: `validate`
- **Called By**: WorldLoader
- **Used**: Yes

**`execute(self, request: TravelRequest) -> TravelResult`**
- **Signature**: Returns TravelResult
- **Purpose**: Executes travel: resolves route, advances clock, generates exposure
- **Calls**: None
- **Called By**: `resolve`
- **Used**: Yes

**`resolve(self, from_id: str, to_id: str) -> TravelExposure`**
- **Signature**: Returns TravelExposure
- **Purpose**: Legacy API that executes travel and returns TravelExposure (for unit tests)
- **Calls**: `execute`
- **Called By**: advance_time, tests
- **Used**: Yes

**`current_minute(self) -> int`**
- **Signature**: Returns int
- **Purpose**: Returns current world clock minute
- **Calls**: None
- **Called By**: External
- **Used**: Yes

---

#### `backend/app/engine/world/exposure.py` – Character Exposure During Travel

**Purpose**: Generate random exposure packets when character travels (determines if player sees NPC).

#### Dataclasses

**`ExposureConfig`**
- **Fields**: `start_prob: float`, `end_prob: float`, `intermediate_prob: float`
- **Methods**: `validate()` – Validates that all probability values are in range [0.0, 1.0]
- **Purpose**: Probability configuration for exposure

**`ExposurePacket`**
- **Fields**: `is_exposed: bool`, `exposure_location_id: Optional[str]`
- **Purpose**: Random exposure result packet

**`TravelExposure`**
- **Fields**: `is_exposed: bool`, `exposure_location_id: Optional[str]`
- **Methods**: 
  - `from_packet(packet: ExposurePacket)` – Converts packet to exposure
  - `minutes_spent()` – Calculates total minutes spent in travel
- **Purpose**: Final exposure result

#### Classes

**`ExposureResolver`**

**`__init__(self, config: ExposureConfig)`**
- **Signature**: Initializes resolver
- **Purpose**: Initializes exposure resolver with probability config
- **Calls**: None
- **Called By**: WorldLoader
- **Used**: Yes

**`roll(self, intermediate_id: Optional[LocationId]) -> TravelExposure`**
- **Signature**: Returns TravelExposure
- **Purpose**: Generates random exposure packet based on probability config
- **Calls**: `_rng`, `from_packet`
- **Called By**: TravelResolver.execute
- **Used**: Yes

---

#### `backend/app/engine/time_utils.py` – World Time Formatting

**Purpose**: Convert world time to human-readable timestamps.

#### Classes

**`WorldTimestamp`**
- **Fields**: `iso_timestamp: str`, `readable: str`
- **Purpose**: Timestamp in both ISO and readable formats

**`WorldTimeFormatter`**

**`@classmethod compute(cls, start_dt_str: str, minute: int) -> WorldTimestamp`**
- **Signature**: Returns WorldTimestamp
- **Purpose**: Converts start datetime string and minute offset into ISO and human-readable timestamps
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

---

## Backend Knowledge Layer

### Retrieval Runtime

#### `backend/app/knowledge/runtime/retrieve.py` – Hybrid Retrieval Entry

**Purpose**: Unified entry point for hybrid BM25 + FAISS knowledge retrieval.

#### Functions

**`retrieve_knowledge(query: str) -> List[dict]`**
- **Signature**: Returns list of retrieved chunks
- **Purpose**: Main retrieval function; performs hybrid BM25+FAISS search and fuses results by relevance
- **Calls**: IndexService methods, BM25 and FAISS search functions
- **Called By**: `chat_handler`
- **Used**: Yes

---

#### `backend/app/knowledge/runtime/index_service.py` – Index Caching & Management

**Purpose**: Thread-safe cache for character-specific index bundles (BM25 + FAISS).

#### Classes

**`IndexService`**

**`get_indexes(character_id: str) -> CharacterIndexBundle`**
- **Signature**: Returns CharacterIndexBundle
- **Purpose**: Retrieves or loads character index bundle with caching
- **Calls**: None
- **Called By**: External
- **Used**: Yes

**`set_active_character(character_id: str)`**
- **Signature**: Sets context variable
- **Purpose**: Sets active character for current context (for multi-character scenarios)
- **Calls**: None
- **Called By**: `chat_handler`
- **Used**: Yes

**`reset_for_tests()`**
- **Signature**: Clears cache
- **Purpose**: Clears in-memory cache for test isolation
- **Calls**: None
- **Called By**: Tests
- **Used**: Yes

---

#### `backend/app/knowledge/runtime/load_indexes.py` – Index Loading

**Purpose**: Load pre-built FAISS + BM25 artifacts from disk.

#### Functions

**`_load_chunks_jsonl(path: Path) -> List[dict]`**
- **Signature**: Returns list of chunk dicts
- **Purpose**: Loads JSONL file of chunks
- **Calls**: None
- **Called By**: `load_character_indexes`
- **Used**: Yes

**`_has_required(d: Path) -> bool`**
- **Signature**: Returns boolean
- **Purpose**: Checks if directory has all required artifact files (FAISS index, BM25, chunks)
- **Calls**: None
- **Called By**: `load_character_indexes`
- **Used**: Yes

**`load_character_indexes(char_id: str) -> CharacterIndexBundle`**
- **Signature**: Returns CharacterIndexBundle
- **Purpose**: Loads character-specific indexes from cache directory
- **Calls**: `_has_required`, `_load_chunks_jsonl`
- **Called By**: IndexService
- **Used**: Yes

---

#### `backend/app/knowledge/runtime/faiss_runtime.py` – FAISS Search

**Purpose**: Semantic search via FAISS index.

#### Functions

**`search_faiss(index, embeddings: np.ndarray, query_embedding: np.ndarray, k: int = 5) -> tuple`**
- **Signature**: Returns (distances, indices)
- **Purpose**: Searches FAISS index and returns top-k indices and similarity scores
- **Calls**: None
- **Called By**: `retrieve_knowledge`
- **Used**: Yes

---

#### `backend/app/knowledge/runtime/bm25_runtime.py` – BM25 Search

**Purpose**: Lexical search via BM25 index.

#### Functions

**`search_bm25(bm25: Any, chunks: list, query: str, k: int = 5) -> List[dict]`**
- **Signature**: Returns list of matching chunks
- **Purpose**: Performs BM25 keyword search on chunks
- **Calls**: None
- **Called By**: `retrieve_knowledge`
- **Used**: **No (unused – search implemented in retrieve.py)**

---

#### `backend/app/knowledge/runtime/ensure_cache.py` – Cache Initialization

**Purpose**: Ensure knowledge artifacts are copied to cache directory if needed.

#### Functions

**`artifacts_present(d: Path) -> bool`**
- **Signature**: Returns boolean
- **Purpose**: Checks if all required artifact files exist in directory
- **Calls**: None
- **Called By**: `main`
- **Used**: Yes

**`main()`**
- **Signature**: Entry point
- **Purpose**: Ensures artifacts are copied from repo to cache directory if needed
- **Calls**: `artifacts_present`
- **Called By**: CLI
- **Used**: Yes

---

### Index Building

#### `backend/app/knowledge/build/build_index.py` – Main Build Orchestration

**Purpose**: Build complete knowledge indexes (embeddings, FAISS, BM25) from character markdown chunks.

#### Functions

**`_get_paths(character_dirname: str) -> dict`**
- **Signature**: Returns dict of paths
- **Purpose**: Computes paths for source chunks and cache artifacts
- **Calls**: None
- **Called By**: `main`
- **Used**: Yes

**`_purge_existing_cache(char_dir: Path) -> None`**
- **Signature**: Removes cache directory
- **Purpose**: Deletes existing cache artifacts for clean rebuild
- **Calls**: None
- **Called By**: `main`
- **Used**: Yes

**`_atomic_save_json(path: Path, obj: dict) -> None`**
- **Signature**: Writes file atomically
- **Purpose**: Atomically writes JSON file (writes to temp file then renames)
- **Calls**: None
- **Called By**: `main`
- **Used**: Yes

**`_atomic_save_npy(path: Path, arr: np.ndarray) -> None`**
- **Signature**: Writes file atomically
- **Purpose**: Atomically saves NumPy array (writes to temp file then renames)
- **Calls**: None
- **Called By**: `main`
- **Used**: Yes

**`main(character_dirname: str | None = None) -> None`**
- **Signature**: Main entry point
- **Purpose**: Main build orchestration: validates chunks, builds embeddings/FAISS/BM25, writes artifacts
- **Flow**:
  1. Get source and cache paths
  2. Purge existing cache
  3. Validate chunks exist and are valid
  4. Load previous build fingerprint
  5. Skip if unchanged (fingerprint matches)
  6. Generate embeddings for all chunks
  7. Build FAISS index from embeddings
  8. Build BM25 index from chunks
  9. Write all artifacts atomically
  10. Save fingerprint for next build
- **Calls**: 
  - `_get_paths`, `_purge_existing_cache`, `validate_chunks`, `load_previous_build`, `should_skip`,
  - `Embedder.embed_text`, `build_faiss_index`, `build_bm25_index`,
  - `_atomic_save_json`, `_atomic_save_npy`
- **Called By**: CLI, Docker build
- **Used**: Yes

---

#### `backend/app/knowledge/build/embedder.py` – Embedding Generation

**Purpose**: Generate sentence embeddings for semantic search.

#### Classes

**`Embedder`**

**`embed_text(text: str) -> np.ndarray`**
- **Signature**: Returns embedding vector
- **Purpose**: Generates sentence embedding for text
- **Calls**: Sentence-transformers model
- **Called By**: `build_index.main`
- **Used**: Yes

---

#### `backend/app/knowledge/build/faiss_utils.py` – FAISS Index Building

**Purpose**: Build FAISS index for semantic search.

#### Functions

**`build_faiss_index(embeddings: np.ndarray) -> Any`**
- **Signature**: Returns FAISS index object
- **Purpose**: Constructs FAISS index from embedding vectors
- **Calls**: None
- **Called By**: `build_index.main`
- **Used**: Yes

---

#### `backend/app/knowledge/build/bm25_utils.py` – BM25 Index Building

**Purpose**: Build BM25 index for lexical search.

#### Functions

**`load_chunks_jsonl(path: Path) -> List[Dict[str, Any]]`**
- **Signature**: Returns list of chunks
- **Purpose**: Loads chunks from JSONL file
- **Calls**: None
- **Called By**: `build_index`
- **Used**: Yes

**`tokenize(text: str) -> List[str]`**
- **Signature**: Returns list of tokens
- **Purpose**: Tokenizes text for BM25 using regex supporting English and Korean
- **Calls**: None
- **Called By**: `build_bm25_index`, `bm25_search`
- **Used**: Yes

**`build_bm25_index(chunks: List[dict]) -> Any`**
- **Signature**: Returns BM25 index object
- **Purpose**: Builds BM25 keyword search index from chunks
- **Calls**: `tokenize`
- **Called By**: `build_index`
- **Used**: Yes

---

#### `backend/app/knowledge/build/fingerprint.py` – Build Caching

**Purpose**: Fingerprint knowledge artifacts to detect changes and skip rebuilds.

#### Functions

**`should_skip(prev_fingerprint: dict, chunks_dir: Path) -> bool`**
- **Signature**: Returns boolean
- **Purpose**: Checks if fingerprint matches current chunks (skip rebuild if unchanged)
- **Calls**: None
- **Called By**: `build_index.main`
- **Used**: Yes

**`load_previous_build(cache_dir: Path) -> Optional[dict]`**
- **Signature**: Returns fingerprint dict or None
- **Purpose**: Loads previous build fingerprint from cache
- **Calls**: None
- **Called By**: `build_index.main`
- **Used**: Yes

**`save_fingerprint(cache_dir: Path, fingerprint: dict) -> None`**
- **Signature**: Writes fingerprint
- **Purpose**: Saves fingerprint for next build comparison
- **Calls**: None
- **Called By**: `build_index.main`
- **Used**: Yes

---

#### `backend/app/knowledge/build/hybrid.py` – Hybrid Retrieval Fusion

**Purpose**: Fuse BM25 and FAISS results by relevance score.

#### Functions

**`hybrid_retrieve(bm25_results: List[dict], faiss_results: List[dict], k: int = 5) -> List[dict]`**
- **Signature**: Returns fused list of top-k chunks
- **Purpose**: Combines BM25 (lexical) and FAISS (semantic) results, ranks by fused score
- **Calls**: None
- **Called By**: `retrieve_knowledge`
- **Used**: Yes

---

#### `backend/app/knowledge/build/ensure_indexes.py` – Index Initialization

**Purpose**: Ensure indexes exist; build or require them at startup.

#### Functions

**`get_indexes() -> dict`**
- **Signature**: Returns dict of character indexes
- **Purpose**: Gets or builds all character indexes (depends on REQUIRE_INDEXES/FORCE_REBUILD env vars)
- **Calls**: `build_index.main`, `load_character_indexes`
- **Called By**: `main.py` startup
- **Used**: Yes

---

#### `backend/app/knowledge/contracts/index_bundle.py` – Index Container

**Purpose**: Type definition for character index bundles.

#### Dataclasses

**`CharacterIndexBundle`**
- **Fields**: 
  - `chunks: List[dict]` – Original chunks
  - `faiss_index: Any` – FAISS index object
  - `bm25_index: Any` – BM25 index object
  - `embeddings: np.ndarray` – Embedding vectors
- **Purpose**: Container for all indexes for a single character

---

#### `backend/app/knowledge/authoring_checklist.py` – Validation

**Purpose**: Validate character knowledge artifacts before building indexes.

#### Functions

**`validate_chunks(chunks_dir: Path) -> List[dict]`**
- **Signature**: Returns validated chunks
- **Purpose**: Loads and validates chunks from character knowledge directory
- **Calls**: None
- **Called By**: `build_index.main`
- **Used**: Yes

---

## Backend Infrastructure

### Configuration

#### `backend/app/config/settings.py` – Game Constants

**Purpose**: Centralized configuration for game rules, timing, and constraints.

**Key Constants**:
- `MINS_PER_WORD` – Minutes added per word in player message
- `BASE_TURN_MINS` – Minimum time per turn
- `TRAVEL_MINS` – Time cost for movement
- `RELATIONSHIP_MIN/MAX` – Bounds for relationship score
- `EMOTION_BOUNDS` – Valid emotion values
- `MEMORY_TURNS` – Number of conversation turns to include in prompt

---

### Middleware

#### `backend/app/middleware/request_id.py` – Request Tracing

**Purpose**: Add/preserve X-Request-ID header for distributed tracing.

#### Functions

**`request_id_middleware(request: Request, call_next) -> Response`**
- **Signature**: FastAPI middleware
- **Purpose**: FastAPI middleware that adds/preserves X-Request-ID header for request tracing
- **Calls**: None
- **Called By**: FastAPI middleware stack
- **Used**: Yes

---

### Entry Point

#### `backend/app/main.py` – FastAPI Application

**Purpose**: Initialize FastAPI app with startup hooks and endpoint registration.

#### Functions

**`warm_indexes() -> None`**
- **Signature**: Async background function
- **Purpose**: Asynchronously loads FAISS and BM25 indexes in background thread during startup to reduce first-request latency
- **Calls**: `get_indexes`
- **Called By**: `_startup_event`
- **Used**: Yes

**`_startup_event()`**
- **Signature**: `@app.on_event('startup')`
- **Purpose**: Called on app startup; either requires indexes (REQUIRE_INDEXES=1) or warmly loads them in background
- **Calls**: `get_indexes`, `warm_indexes`
- **Called By**: FastAPI startup hook
- **Used**: Yes

**`version()` [FastAPI GET endpoint]**
- **Signature**: `@router.get('/version')` – Returns version info
- **Purpose**: Returns application version and build info
- **Calls**: None
- **Called By**: FastAPI router
- **Used**: Yes

---

## Frontend

#### `frontend/index.html` – Terminal UI

**Purpose**: Interactive terminal-style interface for playing narrative game; sends messages to backend via `/chat` endpoint.

**Architecture**: Standalone HTML with embedded JavaScript (no build step).

### JavaScript Functions

**UI Management Functions**

**`showErr(msg)`**
- **Signature**: Takes error message string
- **Purpose**: Displays error message in error box
- **Calls**: None
- **Called By**: `onerror`, `onunhandledrejection`
- **Used**: Yes

**`scrollToBottom(force)`**
- **Signature**: Optional force parameter
- **Purpose**: Scrolls terminal to bottom (auto-scroll during typewriter effect)
- **Calls**: None
- **Called By**: `typewrite`, `writeLine`
- **Used**: Yes

**`writeBox(content, title, style)`**
- **Signature**: Takes content, optional title, optional style dict
- **Purpose**: Writes formatted box to terminal
- **Calls**: `writeLine`, `scrollToBottom`
- **Called By**: Multiple (rendering dialogue, debug info, etc.)
- **Used**: Yes

**`writeLine(content, style)`**
- **Signature**: Takes content string, optional style object
- **Purpose**: Writes single line of text to terminal output
- **Calls**: `scrollToBottom`
- **Called By**: Multiple (dialogue, narration, etc.)
- **Used**: Yes

**`typewrite(content, speed, done_callback)`**
- **Signature**: Takes content, speed ms, optional callback
- **Purpose**: Animated typewriter effect for dialogue/responses
- **Calls**: `writeLine`, `scrollToBottom`
- **Called By**: `send`
- **Used**: Yes

**State Management Functions**

**`setState(obj)`**
- **Signature**: Takes state object
- **Purpose**: Updates UI state tracker for session tracking
- **Calls**: None
- **Called By**: `send`
- **Used**: Yes

**`getState()`**
- **Signature**: No parameters
- **Purpose**: Retrieves current UI state
- **Calls**: None
- **Called By**: `commitLine`, `handleMenu`
- **Used**: Yes

**Network Functions**

**`setHeader(name, value)`**
- **Signature**: Takes header name and value
- **Purpose**: Configures custom HTTP headers for API requests
- **Calls**: None
- **Called By**: Initialization
- **Used**: Yes

**`fetchStoryMeta(storyId)`**
- **Signature**: Takes story ID string
- **Purpose**: Fetches story metadata from server
- **Calls**: None
- **Called By**: `handleMenu`
- **Used**: Yes

**`send(msg, done, typeOpt)`**
- **Signature**: Takes message string, done callback, optional type options
- **Purpose**: Sends message to `/chat` endpoint and displays response with typewriter effect
- **Calls**: `typewrite`, `writeLine`, `setState`
- **Called By**: `commitLine`
- **Used**: Yes

**Game Flow Functions**

**`renderInstructions(meta)`**
- **Signature**: Takes story metadata object
- **Purpose**: Displays game rules and objectives from story metadata
- **Calls**: `writeBox`
- **Called By**: `handleMenu`
- **Used**: Yes

**`handleMenu()`**
- **Signature**: No parameters
- **Purpose**: Renders story selection menu and name/gender selection flow
- **Calls**: `fetchStoryMeta`, `renderInstructions`, `writeLine`, `commitLine`
- **Called By**: Game initialization
- **Used**: Yes

**`commitLine()`**
- **Signature**: No parameters
- **Purpose**: Processes user input from terminal and sends to backend
- **Calls**: `getState`, `send`
- **Called By**: Input handler (Enter key)
- **Used**: Yes

**Text Processing Functions**

**`formatResponse(text)`**
- **Signature**: Takes response text
- **Purpose**: Formats LLM response for terminal display (handles newlines, box drawing, etc.)
- **Calls**: None
- **Called By**: `typewrite`
- **Used**: Yes

**`parseDebugInfo(text)`**
- **Signature**: Takes response text
- **Purpose**: Extracts debug info box from response for separate display
- **Calls**: None
- **Called By**: Response handler
- **Used**: Yes

---

## Unused Code

**Functions marked as unused (not called by any code path)**:

1. **`backend/app/api/game_logic.py::game_logic()`**
   - Placeholder endpoint for future game logic features
   - No callers
   - Can be removed or repurposed

2. **`backend/app/knowledge/runtime/bm25_runtime.py::search_bm25()`**
   - BM25 search function never called
   - Retrieval is implemented inline in `retrieve.py`
   - Can be removed or consolidated

---

## Architecture Summary

### Request Flow (Typical Chat Turn)

```
Frontend (index.html)
    ↓ POST /chat {session_id, message, story_id}
Backend API Layer (chat.py)
    ├─ Session management (get_session)
    ├─ Command parsing (__cmd_*)
    ├─ Story loading (load_story)
    ├─ Location extraction (LocationExtractor.extract)
    │   ├─ Classification LLM (_should_attempt)
    │   └─ Destination LLM extraction (extract)
    ├─ Knowledge retrieval (retrieve_knowledge)
    │   ├─ BM25 search
    │   ├─ FAISS search
    │   └─ Hybrid fusion
    ├─ Prompt building (build_messages)
    ├─ LLM invocation (OpenAI API)
    ├─ State tag parsing (extract_state_tag)
    ├─ State update (apply_state_tag)
    ├─ Time advancement (advance_time)
    │   └─ Travel resolution (travel_resolver.resolve)
    ├─ Win condition check (confession_detected)
    └─ Response formatting
        ↓ {reply, over, debug_info}
Frontend (index.html)
    ↓ Display with typewriter effect
```

### Data Dependencies

```
MurderGameState (core container)
├── story_cfg (from story_loader.load_story)
├── characters (indexed by key)
├── world_runtime (optional, from WorldLoader)
│   ├── graph (WorldGraph with locations/edges)
│   ├── clock (WorldClock)
│   └── travel_resolver (TravelResolver)
└── emotion/relationship (updated by state tags)

Knowledge Retrieval Pipeline
├── IndexService (thread-safe cache)
│   └── CharacterIndexBundle (per character)
│       ├── FAISS index (semantic)
│       ├── BM25 index (lexical)
│       ├── chunks (original documents)
│       └── embeddings (vector data)
└── hybrid_retrieve (fusion result)
```

### Deployment Configuration

**Environment Variables**:
- `OPENAI_API_KEY` – Required for LLM calls
- `KNOWLEDGE_CACHE_DIR` – Where FAISS/BM25 artifacts stored (default: `/data/knowledge_cache`)
- `REQUIRE_INDEXES` – Fail startup if indexes unavailable
- `FORCE_REBUILD_INDEX` – Force rebuild on startup
- `PYTHONPATH=/srv` – Points to `/srv/backend`

**Knowledge Artifacts** (built at Docker build time):
- `/data/knowledge_cache/<character_id>/chunks.jsonl` – Original chunks
- `/data/knowledge_cache/<character_id>/embeddings.npy` – Embeddings
- `/data/knowledge_cache/<character_id>/faiss.index` – FAISS index
- `/data/knowledge_cache/<character_id>/bm25.pkl` – BM25 index

---

## Key Design Patterns

### State Management
- **Immutable dataclasses** for game state (MurderGameState, CharacterState, UserState)
- **In-memory session dict** for fast access (no database)
- **State tags** (`[[STATE: {...}]]`) appended to LLM responses for structured updates

### Knowledge Retrieval
- **Hybrid fusion** of BM25 (lexical) + FAISS (semantic) for relevance
- **Per-character indexes** for multi-character scenarios
- **Lazy loading** of FAISS/BM25 with background warmup at startup

### LLM Integration
- **Two-stage location extraction** (classification + destination parsing)
- **Manifestation rules** (location-based visibility)
- **Relationship/emotion dynamics** (state tags from LLM)
- **Confession detection** (regex patterns for game end)

### World System
- **JSON-based world definitions** (locations, edges, timing)
- **Deterministic path finding** (seeded RNG for reproducible routes)
- **Exposure rolls** (random character sightings during travel)
- **Clock-based time advancement** (minute counter for narrative progression)

### Logging & Debugging
- **JSON line logging** to stdout (visible in Railway Deploy Logs)
- **Debug mode toggle** via `[D]` in chat
- **ASCII debug box** with location, character list, timestamp
- **Comprehensive stage logging** in location extractor and chat handler

---

## Testing Guidance

- **Unit tests**: Mock LLM calls, test extraction logic, state transitions
- **Integration tests**: Real API calls, end-to-end chat turns, world navigation
- **Test utilities**: `conftest.py` fixtures for session setup, world graphs, mock LLM responses

---

## Common Debugging Tasks

1. **Location extraction not working**: Check `_should_attempt()` LLM classification via JSON logs
2. **Chat response has wrong timestamp**: Verify debug_mode is False (timestamps only in debug box)
3. **Knowledge retrieval empty**: Check `KNOWLEDGE_CHARACTER_ID` mapping, verify indexes built
4. **Travel not advancing time**: Check `world_runtime` exists and `travel_resolver.resolve()` called
5. **Game won't end**: Verify confession patterns in story config match LLM response

