Game Structure (Data Model)
====================================

## Core Design Philosophy: Discovery Over Introduction

**Characters must be discovered through gameplay, never pre-announced.**

Like the Legend of Zelda — you don't need a Ganondorf introduction before you meet him.
You encounter characters organically by exploring locations and following the story.
If a player agent (or real user) cannot discover a character through natural conversation
and exploration, the game is broken and must be fixed. The solution is NEVER to leak
character names to the player upfront.

Consequences:
- Player agent briefs NEVER include character names or roles (see debug_engine.py)
- Story design MUST place characters in discoverable locations with clear narrative hooks
- The NPC should naturally reference or introduce other characters during play
- If nobody is ever mentioned, the knowledge base or scene design needs work

This principle applies equally to real users and LLM player agents.
The test for a well-designed game: does a player starting from zero naturally
stumble upon every relevant character within a reasonable run?



Key artifacts per game (one folder per game)
- Naming: folders use `<integer>_<slug>` and the integer must be unique per game (1, 2, 3, …). If an integer collides, fix the overlap before proceeding.

Knowledge (retrieval inputs)
- Path: backend\app\knowledge\characters\<id>/
- knowledge.json: canonical fact source you author. Plain JSON list of facts.
- chunks.jsonl: derived from knowledge.json; flattened, windowed chunks with metadata for retrieval.
- Artifacts produced by build pipeline: BM25/FAISS index files alongside chunks.jsonl. These are what the app loads at runtime; knowledge.json itself is authoring-time only.

Player Visibility Labeling (REQUIRED understanding for game authors)
---------------------------------------------------------------------
At game init, every knowledge artifact is labeled player_visible or player_hidden.
This determines what the debug player agent (and future real-user memory systems)
can retrieve during gameplay.

DEFAULT RULES (no authoring needed for most games):
  chunks.jsonl          → player_visible = true  (public biographical/world knowledge)
  canonical_facts       → player_visible = false (game secrets — the mystery itself)
  character_self_knowledge → always hidden        (NPC private identity)
  beliefs               → always hidden           (NPC private thoughts)
  character_graph edges → always hidden           (NPC private relationships)
  location descriptions → always visible          (shown on the public map)

OVERRIDES:
  To hide a specific chunk (e.g., "IU was found dead in her apartment" is a public
  fact the player should NOT start knowing):
    Add "player_visible": false to the chunk in chunks.jsonl.

  To expose a canonical fact the player starts knowing (e.g., "The story is set in Seoul"):
    Add "player" to the fact's known_by array in the story JSON:
      { "id": "setting_fact", "text": "...", "known_by": ["all_characters", "player"], "confidence": 1.0 }

Runtime: _seed_player_visibility() in prompt_engine._cmd_newgame populates
state.player_visible_chunk_ids at game init. The debug player agent calls
_retrieve_player_context() each turn to retrieve only visible chunks via the same
FAISS/BM25 pipeline the story master uses. This lets the player agent draw on the same
public knowledge a real fan/player would bring to the game — without ever seeing secrets.

Story content
- Path: backend\app\stories\<folder>/ where <folder> = `<int>_<slug>` (e.g., `1_iu_murder_mystery`, `2_jennie_murder_mini`)
- Story JSON: either `<story_id>.json` or `<story_id>_story.json` (loader tries both).
  Runtime canonical story object is projected to generic keys only:
  `id,title,theme,instance,opening,world,time,emotion,goal,win_detection,epistemic_seed,canonical_truth,characters,relationships`.
  Non-canonical top-level fields are not kept in the canonical story object; they are serialized into transient context.
- `<story_id>_world.json`: world graph (locations, edges). Descriptions should encode specifics (e.g., "Interview Room A is Steve's room"). When loaded, Location.description carries this text.
- Map image: `<folder>.png` (convention: folder name = image name). Auto-discovered by _discover_map_image().
  Also supports explicit path via world.world_map_image field in the story JSON.
  Served to the frontend via GET /api/story-image/{path}.
- Deterministic UUIDs: every character and location includes a `uuid` following `<user>-<story>-<instance>-<entity>`.
  - `user` defaults to `default_user` until auth is wired.
  - `story` is the story id (slugged); `instance` defaults to `1` in JSON (increment per save slot/checkpoint if needed later).
  - `entity` is the character key or location id (slugged, lowercase).
- IMPORTANT: world.file and world.world_map_image paths in story JSON must use the ACTUAL folder name (e.g., "2_jennie_murder_mini/..."), not short aliases.

Character Location Tracking (REQUIRED in every story)
------------------------------------------------------
Every character must have a declared starting location. This ensures the engine knows
who is at each location at game start, and prevents the engine from fabricating speakers.

Schema — in the story JSON `world` section:
  "world": {
    "start_location_id": "some_location_id",        ← player's starting location
    "character_start_locations": {                  ← REQUIRED: where each character begins
      "<character_key>": "<location_id>",
      ...
    }
  }

Runtime: At game start, `state.character_locations` (Dict[str, str]) is populated from
`character_start_locations`. As characters move during gameplay, update `state.character_locations[key]`
to their new location. Every location implicitly tracks who is there by inverting this dict.

Rules:
- EVERY named character must appear in `character_start_locations`.
- Location IDs must match keys in the `<story_id>_world.json` `locations` object.
- The player's start position is `start_location_id` (separate from character positions).
- `state.character_locations` is the runtime source of truth. The static
  `location_speakers` legacy field in world config is only used as a fallback for
  stories that haven't yet defined `character_start_locations`.

Engine behavior when nobody is at the player's location:
- Debug box shows no speakers (empty) — never fabricates.
- Prompt scene cast contains only the focal NPC and player.
- The LLM may still narrate descriptions of an empty location; it will not
  force a character to speak who is not physically present.

Character identity & canonical facts (REQUIRED in every story JSON)
- Characters store only generic/basic attributes in runtime objects (`key,name,role,is_main,is_suspect,knowledge_character_id,uuid,tags`).
  Any extra per-character authoring fields are treated as non-canonical metadata and moved into transient context.
- `tags` are story-level labels (e.g., `["ghost"]`, `["suspect"]`). They are narrative metadata only —
  the engine does NOT interpret any tag as special behavior. In particular, there is no "victim" concept
  at the engine level. Game-specific roles like "victim" or "ghost" are purely story labels that have
  no effect on speaker selection, scene casting, or any engine logic.
  WRONG: Using tags to exclude a character from speaking (old "victim" fallback — removed).
  RIGHT: Use `character_start_locations` to put characters in specific locations where they
  are or aren't present.
- `epistemic_seed.canonical_facts`: array of fact objects. These are authoritative game-world
  truths. Canonical facts are included in the epistemic knowledge stack and must be explicitly
  labeled with visibility metadata.
  Required fields per fact:
    - `id`: unique string identifier (snake_case)
    - `text`: the canonical truth as a plain sentence
    - `known_by`: array of character keys who know this fact (e.g., ["iu"], ["steve", "bob"], or ["all_characters"] for common knowledge)
    - `not_known_by`: array of character keys that explicitly do not know this fact
    - `maybe_known_by`: array of character keys that might know this fact
    - `confidence`: ALWAYS 1.0. These are canonical (authoritative) facts, not beliefs.
      Beliefs with varying confidence belong in `epistemic_seed.belief_seeds`, not here.
  Rules:
    - Every story MUST have at least one canonical fact.
    - confidence is always 1.0 — never use 0.9, 0.7, etc. for canonical facts.
    - Use lowercase character keys matching `characters[].key`.
    - Use `known_by: ["all_characters"]` only for true common knowledge facts.
    - Canonical facts are rendered with source/tier/certainty + visibility labels in prompt order
      (most canonical to least canonical).
- `epistemic_seed.belief_seeds`: dict keyed by character key. These are subjective beliefs
  characters hold (not authoritative truth). Confidence CAN vary here (0.0–1.0) because
  beliefs may be wrong, uncertain, or self-serving.
  Optional per-claim visibility metadata is also supported:
    - `known_by`
    - `not_known_by`
    - `maybe_known_by`

Frontend/meta
- index.html fetches /api/stories and uses world_map_image from story meta to render map + location list.
- version.json bumps to bust cache when assets change.

Prompt context contract (runtime)
- Prompt input can only come from:
  1) BM25/FAISS retrieved chunks,
  2) character basics,
  3) story canonical truths (`canonical_facts` with explicit visibility labels),
  4) character relationship graph,
  5) belief graph,
  6) places graph,
  7) runtime transient buffer (internal only; not rendered directly into prompt text).
- Runtime prompt rendering uses an epistemic knowledge stack ordered:
  CANONICAL_CORE → CANONICAL_GRAPH → SUBJECTIVE_BELIEF → RETRIEVED_MEMORY.
- System prompt delivery mode is storyteller-first (paragraph narrative contract) rather than single-NPC chatbot framing.
- The main character remains focal, but prompt instructions allow multi-character scene narration when relevant to continuity and tension.
- Character-graph context is rendered once in a dedicated prose relationship section (no duplicated raw `from->to` telemetry inside epistemic stack).
- Character-graph and character-extra prompt data must be scoped by active-character markers only.
  Active characters are derived from current-turn mentions, scene co-presence (location_speakers), and on-call transient markers,
  stored as transient marker text entries prefixed with `__active_character_marker__:` and refreshed each turn.
  Optional phone-call markers use `__on_call_character_marker__:`.
  System-prompt log content and stale prior-turn mentions are excluded from active-character extraction.
- For chunks without explicit `known_by` and without explicit `not_known_by` for the active speaker,
  the LLM is instructed to make a best reasonable determination from dialogue context.
- After each reply, `KnowledgeResolutionExtractor` evaluates unknown chunks and writes explicit
  `knows` / `does_not_know` updates into the speaker belief graph (`KnowledgeChunk` with `kind='claim'`).
- Each resolved knowledge object is also written to transient buffer as `TransientKnowledge(text, turns_remaining)`
  with fixed turn TTL from `backend/app/config/settings.py` (`TRANSIENT_KNOWLEDGE_TURNS = 8`).
- No other free-form story JSON fields are injected directly into prompt text.

Loading flow (runtime)
1) Story selection loads /api/story/<story_id> which:
   - Loads story JSON and world JSON (via WorldLoader) to expose known_locations and map path.
   - Discovers map image using world_map_image field or naming conventions.
2) New game (__cmd_newgame__) canonicalizes story config, sets knowledge_character_id, seeds epistemic facts/beliefs, loads world graph, and seeds non-canonical story/character extras into transient entries.
3) Retrieval: IndexService activates the character bundle; FAISS/BM25 artifacts (built from chunks.jsonl) are loaded from backend\app\knowledge\runtime.

Instructions for AI to create a game
1) Pick a unique id/folder `<int>_<slug>` (no integer reuse). Example: `3_newcase`.
2) Author knowledge.json under backend\app\knowledge\characters\<id>/ with solid, sourced facts. If the person/entity is ambiguous, ask for clarification—do not invent.
3) Generate chunks.jsonl from knowledge.json (windowed passages). Run the index builder so FAISS/BM25 artifacts exist beside chunks.jsonl.
4) Create story JSON under backend\app\stories\<folder>/ as `<story_id>_story.json`. Include: goal, opening, rules, canonical_truth (explicit facts), knowledge_character_id, world_context array.
   Set the world.file path using the actual folder name: "<folder>/<story_id>_world.json".
5) Create world JSON (<story_id>_world.json) with locations/edges. Ensure descriptions encode ownership details (e.g., "Interview Room A is Steve's room"; "Interview Room B is Bob's room") so Location.description carries them after load.
   Also add `character_start_locations` to the story JSON's `world` section — every character needs a starting location.
   The player's start position goes in `start_location_id` (separate from character positions).
6) Produce a coherent map image named `<folder>.png` inside the story folder. Keep scale/layout believable. Auto-discovery will find it by convention.
7) Verify frontend: story appears in /api/stories, map renders, location list shows descriptions.
8) Add/extend integration tests to load the story, world, and map; ensure data paths resolve. Run full test suite (python -m pytest).
9) If anything is unclear, stop and ask for clarification before proceeding.