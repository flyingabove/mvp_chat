# Character graph, epistemics, transient buffer, data models

> This file merges several design documents (each keeps its own section, with its original status notes). Open work is in [../BACKLOG.md](../BACKLOG.md).

## Character Graph Design

> **What this doc is for:** Design of the character relationship graph (nodes, edges, 4D state, query API). Edit this doc when the character graph schema, edge types, or query API changes.

Last updated: 2026-02-26

### What Is the Character Graph?

The character graph is a directed graph that models every participant in the story — including the human player — and how they relate to each other. Every participant is a **node** (a `Character` object). Every relationship between two participants is a **directed edge** (`RelationshipEdge`) carrying structured numeric state plus human-readable prose.

The graph serves three purposes:
1. **Prompt construction** — tell the AI how a character feels about the people in the scene so it can calibrate tone, hostility, and willingness to cooperate.
2. **Game mechanics** — relationship thresholds can gate behaviors (e.g., a suspect only confesses when `trust > 0.5` and `fear > 0.7`).
3. **Debug visibility** — the developer can inspect the full relationship state at any point to verify the AI's behavior makes sense.

---

### Character Types

Every participant — including the human player — is a `Character` object with a `CharacterType`. The `character_type` field is the engine-level structural role, distinct from the free-form story `role` string (e.g. "ghost", "ally").

| CharacterType | Key convention | Description |
|---|---|---|
| `USER` | `"player"` | The human player. Auto-created at game init via `make_player_character()`. Not defined in story JSON. Has authored relationship edges to all authored NPCs. |
| `MAIN` | set by author | The focal NPC of the session (`is_main: true` in story JSON). Has a full knowledge/lore bundle and is the primary conversation partner. Inferred automatically from `is_main`. |
| `CANONICAL` | set by author | Authored NPC with a defined story role and optional knowledge bundle. Fully scripted backstory, motivations, and relationships. Default for any authored character without a `character_type` field. |
| `NPC` | any | Incidental or emergent character. May be introduced by the LLM in dialogue. No authored knowledge bundle; exists at runtime only. |

Story JSON does not define a `USER` character — the engine creates it automatically:
```python
from backend.app.engine.state import make_player_character
player = make_player_character(display_name="Player")
# → Character(key="player", character_type=CharacterType.USER, ...)
```

---

### Graph Structure

`CharacterGraph` stores both nodes and edges:

```
CharacterGraph
├── characters: Dict[str, Character]         # key → Character node
└── edges: Dict[str, RelationshipEdge]       # "{from_id}->{to_id}" → edge
```

**Edge uniqueness**: exactly one directed edge per `(from_id, to_id)` pair. Internally keyed as `"{from_id}->{to_id}"` for O(1) lookup. Uniqueness is enforced on write — no duplicate edges can exist.

**Directed means asymmetric**: IU's feelings toward the player are a separate edge from the player's feelings toward IU. They can differ.

---

### Node: Character

The `Character` dataclass (in `state.py`) is the node type:

```
Character:
  key: str                        # unique identifier (e.g. "iu", "steve", "player")
  name: str                       # display name (e.g. "IU")
  role: str                       # story-level role (free-form: "ghost", "suspect", "ally")
  character_type: CharacterType   # engine-level type: USER / MAIN / CANONICAL / NPC
  is_main: bool                   # True for the focal NPC (drives character_type=MAIN)
  is_suspect: bool
  knowledge_character_id: str     # FAISS/BM25 index bundle directory
  uuid: str
  tags: List[str]
  self_knowledge: List[str]       # first-person identity facts injected into prompt
  emotion: str                    # current emotional descriptor
  relationship: int               # legacy -5..+5 score (kept for backward compat)
```

Characters are also stored in `CharacterGraph.characters` so the graph is self-contained for lookups.

---

### Edge: RelationshipEdge

Each directed edge represents how `from_id` feels about `to_id`:

```
RelationshipEdge:
  id: str                           # canonical "{from_id}->{to_id}" storage key
  from_id: str                      # who holds this perspective
  to_id: str                        # about whom
  type: RelationshipType            # FRIEND, ENEMY, FAMILY, LOVER, EMPLOYER, EMPLOYEE,
                                    # SUSPECT, VICTIM, WITNESS, OTHER
  state: RelationshipState          # numeric dimensions (see below)
  label: str                        # static authored context, never changes at runtime
                                    # e.g. "former manager; contract dispute ended badly"
  narrative: str                    # dynamic runtime note, replaced on each update
                                    # e.g. "IU now believes Steve is hiding something"
  narrative_log: List[str]          # append-only session history of all narrative notes

  # ── Relationship History (see "Relationship History Fields" section below) ──
  met_at: Optional[int]             # game minute of first physical co-location this session.
                                    # None = haven't met yet. 0 = met before game started.
  last_met_at: Optional[int]        # game minute of most recent co-location event.
                                    # Updated each time process_first_meetings fires as a
                                    # new encounter. None until first meeting.
  meeting_count: int                # number of distinct encounters this session.
                                    # Incremented on each new room-entry co-location.
                                    # Pre-seeded from story JSON for pre-existing relationships.
  prior_relationship: bool          # True if characters have/had a romantic relationship
                                    # before or outside the current session. LLM-extracted.
  prior_intimacy: bool              # True if characters have been sexually intimate.
                                    # LLM-extracted from explicit dialogue.
  in_relationship: bool             # True if characters are currently in a relationship.
                                    # LLM-extracted.
```

`label` is set once by the story author and frozen. `narrative` is updated by the LLM via the STATE tag as the scene evolves. `narrative_log` records every narrative note ever written for this edge during the session.

#### Relationship History Fields

These fields track the shared history between two characters. They split into two update categories:

**Deterministic (engine-tracked):**

| Field | Updated by | Trigger |
|-------|-----------|---------|
| `met_at` | `process_first_meetings()` | First physical co-location; set once, never reset |
| `last_met_at` | `process_first_meetings()` | Each new encounter (`is_new_encounter=True`) |
| `meeting_count` | `process_first_meetings()` | Each new encounter (`is_new_encounter=True`) |

A "new encounter" is when the player enters a room where both characters are present (`is_new_encounter=True` is passed from `prompt_engine.py` when a location change is detected). NPC walk-ins (characters joining an existing room) also count.

`met_at = 0` is the convention for characters who knew each other before the game started (set via `met_before_game: true` in story JSON).

**LLM-extracted (via TurnExtractor):**

| Field | Meaning | When extracted |
|-------|---------|----------------|
| `prior_relationship` | Ever had a romantic relationship | Dialogue explicitly mentions a past romance |
| `prior_intimacy` | Ever been sexually intimate | Dialogue explicitly confirms or strongly implies |
| `in_relationship` | Currently in a relationship | Dialogue explicitly states current status |

The extractor only sets these when dialogue provides clear confirmation. Ambiguous or speculative references are ignored (omitted from the `relationship_history_updates` array).

**Familiarity** (derived, not stored): `meeting_count / total_game_days`. Left blank for most characters; can be computed on-demand when needed.

---

### Player as a Character

The player is a full first-class character in the graph (`character_type = USER`, key = `"player"`). Player→NPC edges are created by `process_first_meetings()` just like NPC→NPC edges. The player's relationship state toward each NPC is tracked independently and updated by three mechanisms:

| Update source | What it updates | When |
|---|---|---|
| `process_first_meetings()` | `met_at`, `last_met_at`, `meeting_count` on player→NPC edge | Each room entry |
| `TurnExtractor` `relationship_state_updates` | Trust/fear/affection/suspicion/jealousy deltas on player→NPC edge | Each turn — inferred from player's message |
| `TurnExtractor` `relationship_history_updates` | `prior_relationship`, `prior_intimacy`, `in_relationship` on player→NPC edge | When player's dialogue explicitly confirms |

#### Player Attitude Deltas (RelationshipStateUpdate)

`RelationshipStateUpdate` captures small incremental changes to the player's attitude toward an NPC, extracted from the player's current message:

```
RelationshipStateUpdate:
  from_id: str          # always "player"
  to_id: str            # NPC character key
  trust_delta: float    # [-0.10, +0.10] — negative = distrust, positive = trust
  fear_delta: float     # [0.0, +0.10]   — fear is 0..1, never decremented by extractor
  affection_delta: float # [-0.10, +0.10] — negative = coldness/anger, positive = warmth
  suspicion_delta: float # [0.0, +0.10]   — suspicion is 0..1
  jealousy_delta: float  # [0.0, +0.10]   — jealousy is 0..1
  reason: str            # brief extraction explanation
```

**Extraction rules:**
- Only from player's perspective (`from_id = "player"` always)
- Deltas are small: typically 0.05–0.10 per turn; never exceed 0.10
- Omit the entry entirely if the player's words are emotionally neutral
- Omit individual delta fields that are zero
- Multiple extractions per turn are allowed (one entry per NPC)

#### Player Attitude in the NPC's Prompt

The NPC's relationship context section (`[RELATIONSHIP CONTEXT IN THIS SCENE]`) shows the NPC→player edge as normal. Additionally, when the player→NPC reverse edge has been updated, a `[Player's attitude toward {NPC}: ...]` tag is appended to show the NPC how the player is currently treating them. This lets the NPC calibrate their response to the player's revealed attitude.

---

#### RelationshipState (multi-dimensional)

| Dimension   | Range  | Levels | What it means |
|-------------|--------|--------|---------------|
| `trust`     | -1..1  | 21 (0.1 step) | How much A trusts B. Negative = active distrust. |
| `fear`      | 0..1   | 21 (0.1 step) | How afraid A is of B. High fear + low trust = defensive/hostile. |
| `affection` | -1..1  | 21 (0.1 step) | Emotional warmth. Negative = resentment/hatred. |
| `suspicion` | 0..1   | 21 (0.1 step) | How much A suspects B of wrongdoing. |
| `jealousy`  | 0..1   | 5 (0.25 step) | How jealous A is toward B. Five named levels (see below). |

These dimensions are independent. A suspect can have high fear (0.9) AND moderate trust (0.3) toward the detective simultaneously — they're scared but believe the detective will honor a deal. This nuance is impossible with a single integer score.

#### Jealousy Levels (5 discrete word levels)

| Value | Word | Meaning |
|-------|------|---------|
| 0.00 | `secure` | No jealousy — relationship feels unthreatened |
| 0.25 | `mild` | Low-level envy or mild possessiveness |
| 0.50 | `moderate` | Noticeable jealousy influencing behavior |
| 0.75 | `strong` | Openly jealous, likely to act on it |
| 1.00 | `consuming` | Obsessive jealousy dominating all interactions |

#### Per-Interaction Increment Bounds

All five dimensions are bounded per turn. Constants stored in `backend/app/config/settings.py`:

| Constant | Value | Meaning |
|----------|-------|---------|
| `REL_TRAIT_DELTA_MIN` | 0.05 | Smallest non-zero change per interaction |
| `REL_TRAIT_DELTA_MAX` | 0.20 | Largest change per interaction |

A delta of 0 is also valid (nothing changed this turn). These are tunable without touching game logic.

#### RelationshipType

```
FRIEND, ENEMY, FAMILY, LOVER, EMPLOYER, EMPLOYEE, SUSPECT, VICTIM, WITNESS, OTHER
```

Set at story creation time. Can change during gameplay (e.g., FRIEND becomes ENEMY after a betrayal).

---

### Query Interface

All query methods return `RelationshipEdge` or `List[RelationshipEdge]`:

```python
# Node queries
graph.add_character(character)          # add/replace a character node
graph.get_character(key)                # → Character | None

# Single edge
graph.get_edge(from_id, to_id)          # → RelationshipEdge | None (O(1))

# Edge lists
graph.get_edges_from(character_id)      # → List[RelationshipEdge] — outgoing only
graph.get_edges_to(character_id)        # → List[RelationshipEdge] — incoming only
graph.get_all_relationships(character_id)  # → List[RelationshipEdge] — in + out

# Room-level: all edges between any pair in a set
graph.get_room_relationships({"player", "iu", "steve"})
# → every directed edge where both from_id AND to_id are in the set
```

---

### Layered Architecture: Data vs. Prose

**`CharacterGraph` is a pure data layer.** It stores nodes and edges and provides query methods that return raw `RelationshipEdge` objects. It never generates prose or makes decisions about formatting.

**All prose generation belongs in `prompt_builder.py`.** The prompt builder reads raw graph data and converts it to human-readable text for injection into the LLM system prompt.

```
CharacterGraph (character_graph.py)         prompt_builder.py
──────────────────────────────────          ──────────────────────────────────────────
stores nodes + edges                  →     _room_relationship_section(state, ids)
get_room_relationships(ids)                   calls graph.get_room_relationships()
  → List[RelationshipEdge]            →       passes raw edges to ↓
                                            _summarize_room_relationships(edges, chars)
                                              → deterministic prose paragraph
```

---

### Room Scenario: Location Entry Pipeline

When a player moves from location A to location B, the engine:

```python
# Step 1 — extractor detects movement, resolves who is at B
room_ids = {"player", "iu", "steve"}   # characters present at B

# Step 2 — pure data query (no prose, no formatting)
raw_edges = graph.get_room_relationships(room_ids)
# → List[RelationshipEdge]: iu→player, iu→steve, steve→player, steve→iu, ...

# Step 3 — prompt builder generates prose from raw data
section = _room_relationship_section(state, room_ids)
# internally calls graph.get_room_relationships() + _summarize_room_relationships()
# → "[ROOM DYNAMICS]\nIU regards Steve with deep suspicion..."

# Step 4 — also build per-speaker detail for the main NPC
speaker_detail = graph.format_for_prompt(
    speaker_id="iu",
    active_characters={"player", "steve"}
)
# → "[RELATIONSHIP CONTEXT IN THIS SCENE]\n1. IU currently reads..."
```

Both sections are injected into the system prompt before each LLM call.

---

### Relationship Summarizer (in prompt_builder.py)

`_summarize_room_relationships(edges, characters)` produces a deterministic (no LLM) prose paragraph from a list of raw edges. It detects:

| Pattern | Condition | Example output |
|---------|-----------|----------------|
| Mutual warmth | both `affection >= 0.3` | "IU and Steve share a warm rapport." |
| Deep bond | both `affection >= 0.6` | "IU and Steve share a deep, devoted bond." |
| Mutual hostility | both `affection <= -0.3` | "IU and Steve are openly hostile toward each other." |
| One-sided attraction | one `>= 0.4`, other `< 0.0` | "IU is drawn to Steve, who remains cold or indifferent." |
| Mutual fear | both `fear >= 0.5` | "IU and Steve are both afraid of each other." |
| One-sided fear | one `>= 0.5` | "IU is visibly afraid of Steve." |
| Mutual suspicion | both `suspicion >= 0.5` | "IU and Steve regard each other with mutual suspicion." |
| One-sided suspicion | one `>= 0.5` | "IU regards Steve with deep suspicion." |
| Jealousy triangle | A and B both `affection >= 0.4` toward C, A↔B have friction | "There is unspoken tension between IU and Steve, both drawn to the player." |
| Live narrative | edge has `narrative` set | narrative appended verbatim |

---

### Per-Speaker Detail (format_for_prompt)

`format_for_prompt(speaker_id, active_characters)` formats the active speaker's outgoing edges as structured prompt text, including both static context and live narrative:

```
- The Player (player) (witness): Trust is guarded; fear is watchful; affection is neutral; suspicion is doubtful.
  Behavior tendency: guarded defense, likely to hedge and reveal selectively.
  [Context] First meeting; IU initially treated them as a routine fan.
  [Now] IU grew colder after the player's evasive answer about the night of the incident.

- Steve (steve) (suspect): Trust is wary; fear is nervous; affection is cold; suspicion is highly_suspicious.
  Behavior tendency: defensive-hostile, likely to resist, deflect, or confront.
  [Context] Former manager; their relationship soured after the contract dispute.
  [Now] IU now believes Steve is hiding what happened that night.
```

`[Context]` = static `label` (authored, never changes). `[Now]` = dynamic `narrative` (current runtime note). Both are omitted if empty.

---

### Deterministic Language Layer

Numeric dimension values are converted to human-readable words deterministically (no LLM, no randomness):

- `trust` and `affection`: already on -1..1 scale.
- `fear` and `suspicion`: stored as 0..1, normalized to -1..1 via `(value * 2) - 1`.
- Each normalized value is clamped to [-1, 1], rounded to nearest 0.1, then mapped to a fixed vocabulary word.
- Runtime helper: `describe_relationship_state()` in `character_graph.py`.

---

### Edge Mutation

#### Legacy backward-compat (still works)
```python
graph.apply_rel_delta(from_id="iu", to_id="player", rel_delta=-1)
# Maps ±1 integer to ±0.1 affection delta. Preserved for existing story JSONs.
```

#### Full 4D update
```python
graph.update_edge(
    from_id="iu",
    to_id="steve",
    trust_delta=-0.1,
    suspicion_delta=0.2,
    narrative="IU now believes Steve is hiding what happened that night."
)
# Returns True if edge found and updated, False if edge doesn't exist.
# narrative replaces edge.narrative and is appended to narrative_log.
```

Only edges that already exist in the graph can be updated — the engine cannot hallucinate new edges.

#### STATE tag format (applied each turn by apply_state_tag())

Legacy (backward compat — updates affection on main NPC → player edge):
```json
[[STATE]]{"emotion": "cold", "rel_delta": -1}[[/STATE]]
```

Full 4D multi-edge updates (planned, see plan):
```json
[[STATE]]{
  "emotion": "suspicious",
  "rel_updates": [
    {
      "from": "iu", "to": "player",
      "affection_delta": -0.2, "suspicion_delta": 0.1,
      "narrative": "IU grew colder after the player's evasive answer."
    },
    {
      "from": "iu", "to": "steve",
      "trust_delta": -0.3, "suspicion_delta": 0.4,
      "narrative": "IU now believes Steve is hiding what happened that night."
    }
  ]
}[[/STATE]]
```

---

### Story JSON Format

```json
{
  "characters": [
    {
      "key": "iu",
      "name": "IU",
      "role": "ghost",
      "is_main": true,
      "character_type": "main"
    },
    {
      "key": "steve",
      "name": "Steve",
      "role": "ex-manager",
      "is_suspect": true,
      "character_type": "canonical"
    }
  ],
  "relationships": {
    "edges": [
      {
        "id": "iu_to_player",
        "from": "iu",
        "to": "player",
        "type": "WITNESS",
        "state": {"trust": 0.0, "fear": 0.1, "affection": 0.1, "suspicion": 0.3},
        "label": "First meeting; IU initially treated them as a routine fan."
      },
      {
        "id": "iu_to_steve",
        "from": "iu",
        "to": "steve",
        "type": "SUSPECT",
        "state": {"trust": -0.4, "fear": 0.2, "affection": -0.5, "suspicion": 0.7},
        "label": "Former manager; their relationship soured after the contract dispute.",
        "met_before_game": true,
        "meeting_count": 50,
        "prior_relationship": false,
        "in_relationship": false
      },
      {
        "id": "steve_to_iu",
        "from": "steve",
        "to": "iu",
        "type": "ENEMY",
        "state": {"trust": -0.3, "fear": 0.4, "affection": -0.4, "suspicion": 0.3},
        "label": "Resents IU for ending the professional relationship.",
        "met_before_game": true,
        "meeting_count": 50,
        "prior_relationship": false,
        "in_relationship": false
      }
    ]
  }
}
```

Notes:
- `"player"` is a valid `to` target without defining a player character in JSON — the engine creates the `USER` node automatically.
- Omit `character_type` for authored NPCs; the engine defaults to `CANONICAL` (or `MAIN` if `is_main: true`).
- `symmetric: true` on an edge automatically creates an explicit reverse edge with mirrored state at load time. Use explicit separate edges when asymmetric state matters (which is usually the case).
- `met_before_game: true` sets `met_at = 0` at load time — the convention for pre-existing relationships.
- `meeting_count` in story JSON pre-seeds the counter for authored relationships with prior history.
- `prior_relationship`, `prior_intimacy`, `in_relationship` can be pre-seeded in JSON or left as `false` for the extractor to discover during gameplay.

---

### Implementation Status

**All three phases are implemented.**

#### Files

| File | Role |
|---|---|
| `backend/app/engine/character_graph.py` | **Pure data layer.** `CharacterType`, `RelationshipType`, `RelationshipState`, `RelationshipEdge`, `CharacterGraph` (nodes + edges + queries only — no prose) |
| `backend/app/engine/state.py` | `Character` (with `character_type` field), `make_player_character()`, `GameState.character_graph`, `apply_state_tag()` |
| `backend/app/engine/story_loader.py` | Parses `relationships` into `CharacterGraph`; parses characters into `Character` objects |
| `backend/app/engine/prompt_builder.py` | **Prose-generation layer.** `_summarize_room_relationships(edges, chars)` — deterministic prose from raw edges. `_room_relationship_section(state, room_ids)` — calls graph query + summarizer. `_relationship_scene_section(state)` — per-speaker detail (existing). |
| `backend/app/api/prompt_engine.py` | Applies `rel_delta` post-turn; applies `relationship_state_updates` and `relationship_history_updates` from `TurnExtractor` |
| `backend/app/engine/extractors/turn_extractor.py` | `RelationshipStateUpdate` (player attitude deltas), `RelationshipHistoryUpdate` (history flags), `TurnExtraction` |
| `backend/app/integration_playback/scenarios/scenario_turn_extractor_relationships_llm.py` | Real-LLM integration scenario: 6 steps testing relationship extraction accuracy |

#### What is built
- `CharacterGraph` stores both character nodes and directed edges
- `CharacterType` enum classifies every participant structurally
- `make_player_character()` creates the USER node for game init
- O(1) edge lookup via canonical `"{from_id}->{to_id}"` key
- Full query API: `get_edge`, `get_edges_from`, `get_edges_to`, `get_all_relationships`, `get_room_relationships`
- `update_edge()` with full 5D delta (trust/fear/affection/suspicion/jealousy) + narrative
- `update_edge_history()` — applies LLM-extracted relationship history fields to an edge
- `process_first_meetings()` — detects first physical meetings, initializes prejudice on new edges, tracks `met_at`/`last_met_at`/`meeting_count`
- `summarize_relationships()` — deterministic prose paragraph for room-level LLM context
- `format_for_prompt()` — per-speaker detail with `[Context]`, `[Now]`, `[History]`, and `[Player's attitude]` labels
- `narrative` + `narrative_log` on each edge for runtime evolution tracking
- `symmetric=true` in story JSON expands to explicit reverse edge at load time
- Relationship history fields: `met_at`, `last_met_at`, `meeting_count` (engine-tracked); `prior_relationship`, `prior_intimacy`, `in_relationship` (LLM-extracted via `TurnExtractor`)
- **Player as character**: player→NPC edges created and tracked; player attitude deltas extracted each turn via `RelationshipStateUpdate`; NPC prompt surfaces `[Player's attitude]` tag
- Integration playback scenario: 6 LLM-backed steps cover distrust/suspicion, fear, warmth/trust, past relationship, current relationship, jealousy

#### What is pending (see plan)
- `rel_updates` array in STATE tag for LLM to drive multi-edge 4D updates (wired in `apply_state_tag()`)
- Prompt builder section for `summarize_relationships()` injected at room entry

---

## Epistemic Engine Design (North-Star Aligned, Minimal)

> **What this doc is for:** Design of the epistemic/knowledge system (canonical facts, beliefs, confidence). Edit this doc when knowledge retrieval, belief injection, or epistemic rules change.

### Purpose
Keep the engine simple, scalable across stories, and faithful to one rule: **world truth lives in engine state, not in model prose**.

### Non-Negotiables
1. One authoritative world state.
2. Time and movement mutate state deterministically.
3. Retrieval is recall/style only, never authority.
4. Player agency is preserved (no model-authored player actions).
5. Data is isolated by namespace `<user>-<story>-<instance>`.

### In-Memory Contract (Only 3 Categories)
Only these categories are allowed as long-lived runtime memory:

1. **Retrieval Index Cache**
   - BM25/FAISS indexes and lookup metadata.
   - Role: search acceleration only.

2. **Objects**
   - Characters, places, items, evidence objects, quest objects.
   - IDs are deterministic: `<user>-<story>-<instance>-<entity>`.

3. **Graphs**
   - Place graph (movement) and truth/claim relation graph.
   - Graphs store relationships/constraints between objects.

Everything else (full transcripts, audit history, long event logs) is durable storage and can be loaded as needed.

### Belief in This Design (What It Actually Means)
"Belief" is character-local epistemic state, not a fourth storage category.

- **Today (implemented):** `BeliefState` with claims + observations per character.
- **Target shape:** graph projection where:
  - nodes = entities/facts
  - edges = "character believes claim" with confidence + provenance

Belief may disagree with truth. Truth still wins.

### Authority Order
`validated truth > observed evidence > testimony/claim > rumor/inferred > retrieval prose`

Lower layers can inform dialogue, but cannot overwrite higher layers.

### Per-Turn Runtime (Simple)
1. Read input and detect movement/structured intents.
2. Mutate objects/graphs through validated rules.
3. Update epistemic beliefs (claims/observations with provenance).
4. Build prompt from current truth + allowed belief slice + retrieved recall.
5. Render reply.
6. Persist durable records asynchronously/synchronously per environment.

### Unknown Knowledge Resolution (Implemented)
When a chunk is not explicitly marked `known_by` and not explicitly marked `not_known_by` for the active speaker:

1. Prompt instructions require the LLM to make a best reasonable determination (with hedging if uncertain).
2. On the next turn's pre-render phase, a **single-call turn extractor** evaluates prior-turn dialogue + candidate chunks.
3. Extractor outputs deterministic updates per chunk in one JSON payload: `chunk_id`, `knows`, `confidence`, `reason`.
4. Engine writes these to the speaker's belief graph as `KnowledgeChunk` entries with `kind='claim'` (`source=knowledge_resolution_extractor`, `provenance=inferred_dialogue`).
5. Engine writes a mirrored knowledge object into transient buffer with TTL = 8 turns (`meta.source=knowledge_resolution`).

This means ambiguous retrieval memory is converted into explicit epistemic state over time using dialogue evidence, without running separate extractor calls in a single turn.

### Where Updates Are Stored
- Primary authority for these updates is character-local belief graph (`BeliefState`).
- Short-lived transport/debug copy is stored in transient buffer for 8 turns.
- No direct on-the-fly mutation of packaged FAISS/BM25 artifacts occurs at runtime.

### What Is Live vs Planned
- **Live now:** object state, place graph travel, retrieval namespaces, per-character belief logs (`BeliefState`), single-call extractor resolution, and transient scene buffering (including 8-turn knowledge objects).
- **Planned:** stronger invariant validator + full belief graph projection.

### Design Guardrails
- Do not let retrieval chunks mutate canonical truth.
- Do not keep unbounded transcript history in hot memory.
- Do not create a separate in-memory subsystem for "belief" beyond objects/graphs.
- Do not store scene flavor as permanent world truth unless gameplay requires it.

### Related
- See transient scene memory policy in `design/CHARACTER_MEMORY.md (transient buffer)`.

---

## Transient Buffer Design (Scene Memory, Non-Authoritative)

> **What this doc is for:** Design of scene memory / transient buffer (non-authoritative context). Edit this doc when the transient buffer eviction, injection, or scoring logic changes.

### Purpose
Allow vivid scene-level detail without polluting canonical world state.

Examples:
- "You put the coffee cup on the table."
- "Rainwater is pooling by the entrance."
- "A nurse just walked by."

These details improve immersion but should usually fade.

### Key Rule
Transient buffers are **scratch scene memory**, not truth authority.

Transient entries are **never rendered into the system prompt text**. They can influence runtime logic, but prompt assembly intentionally excludes a transient section.

If a detail must matter later for gameplay (evidence, objective, access, irreversible world change), it must be promoted into objects/graphs.

### Lifecycle
1. Create transient details during turn processing.
2. Use them for immediate narration and short-horizon continuity.
3. Reset/expire aggressively.

### Required Reset Behavior
- On session reset, clear all transient entries.
- Turn expiry is handled by countdown pruning, so transient memory naturally fades without being surfaced in prompt text.

### Data Shape (Current Runtime Model)
```text
TransientKnowledge:
- text
- turns_remaining

SceneKnowledge (FIFO scene queue):
- key
- location_id
- speakers: [character_key]
- people_present: [character_key]
- payload: { ... }
```

### Expiration Policy
- The default TTL is fixed to **8 turns**.
- This hardcoded value is centralized at `backend/app/config/settings.py` as `TRANSIENT_KNOWLEDGE_TURNS = 8`.
- `TransientBuffer.prune_expired()` decrements `turns_remaining` and removes entries once they hit `<= 0`.
- SceneKnowledge uses FIFO retention (max 8 entries) rather than per-object turn counters.
- Upsert semantics refresh an existing key by moving it to queue tail.

### Promotion Rules
If a detail becomes durable gameplay truth, write it explicitly to canonical structures (facts/graphs) rather than relying on transient retention.

### Safety Rules
- No direct transient section in prompt output.
- No direct truth overwrite from transient entries.
- No cross-session sharing.

### Implementation Notes
- Runtime state stores `List[TransientKnowledge]` on `GameState.transient_entries`.
- Runtime state also stores `List[SceneKnowledge]` on `GameState.scene_knowledge_entries`.
- New text entries are appended via `GameState.add_transient_entry(text, ...)` and use caller TTL or `TRANSIENT_KNOWLEDGE_TURNS`.
- Scene knowledge entries are upserted via `GameState.upsert_scene_knowledge(...)` and bounded to 8 FIFO items.
- Prompt builder excludes transient entries by design.

### Scene Presence Contract (Current)
- Per turn, engine tracks both:
	- `speakers` (who is currently talking / in turn-active cast)
	- `people_present` (who is physically present at player location)
- These scene fields are produced by the single-call turn extractor contract (one extractor LLM call per turn).
- `people_present` is derived by combining current world location query + character location index.
- If location did not change from previous scene knowledge item, previous turn speakers are carried into the current active character list.
- Phone-call/off-scene edge cases are intentionally deferred.

---

## Data Model Inventory

> **What this doc is for:** Complete inventory of all data models and their fields. Edit this doc when any data model, schema, or field is added or changed.

Complete list of every data model / class in the engine. Reference this when deciding where new data belongs or whether a new class is needed.

Last updated: 2026-09-26

---

### Durable session transaction

`game_sessions` in `backend/app/db/database.py` now has an additive `revision INTEGER NOT NULL DEFAULT 0` column. `SessionRepo._upsert` checks an optional `expected_revision` inside `BEGIN IMMEDIATE`, then increments the revision in the same transaction that writes `state_json`, `flags_json`, `last_request_id`, and `last_reply_json`. A stale writer raises `SessionRevisionConflict` without changing the stored state or reply. The chat handler refreshes stale cached sessions before planning a turn and returns a retryable 409 if another worker commits first. Existing rows are migrated without discarding saved state.

---

### Story / Authoring (static, from JSON)

The optional world atlas adds `MapPoint`, `PlaceResearch`, `MapArea`, and `WorldMap`
in `backend/app/engine/world/map_model.py`. `WorldGraph.world_map` owns the atlas;
`Location` adds `area_id`, `map_position`, and `research`; `PathEdge` adds `mode`
and `estimated`. Both world loaders preserve these fields. See
[design/WORLD_MODEL.md (atlas)](WORLD_MODEL.md) for validation, coordinates and API shape.

| Class | File | What it is |
|---|---|---|
| `StoryDefinition` | `backend/app/engine/story_loader.py` | Top-level container parsed from the story JSON. Holds characters, relationships, raw config. |

**Note:** `StoryCharacter` was deleted — it is now an alias for `Character` (see Runtime State below). Authoring-time character data is parsed directly into `Character` objects.

---

### Runtime State

| Class | File | What it is |
|---|---|---|
| `GameState` | `backend/app/engine/state.py` | The entire session container. Holds all sub-objects below. |
| `Character` | `backend/app/engine/state.py` | Unified character object — authoring identity fields (key, name, role, character_type, is_main, is_suspect, knowledge_character_id, uuid, tags, meta, self_knowledge, voice) merged with runtime state (emotion, relationship). Replaces the former StoryCharacter + CharacterState split. |
| `UserState` | `backend/app/engine/state.py` | The human player as seen in-story: display name, formal name, gender. |

`GameState` is the single object passed through the entire engine. Everything else hangs off it.

**Backward-compat aliases (do not use in new code):**
- `CharacterState = Character` (in `state.py`)
- `StoryCharacter = Character` (in `story_loader.py`)

**`self_knowledge` (BL-07):** each `characters[]` entry in story JSON may declare its own `self_knowledge: [<first-person identity facts>]` array, parsed by `Character.from_dict()` and preserved by `Character.to_dict()` (so it survives `StoryDefinition.from_dict()`'s normalization round-trip). In `prompt_engine.py`, a character's own `self_knowledge` always wins when present; the legacy top-level story JSON `character_self_knowledge` array remains a fallback used only for whichever character is `is_main` and has no per-character `self_knowledge` of its own. See `design/SOCIAL_ENGINE.md (social mode)` §5 for the full injection/gating rule.

**`gender` / `opening_cast` (opening welcome party):** a `characters[]` entry may declare `gender: "M" | "F"` (kept in `Character.meta`, read via `opening_scene.character_gender()`). `GameState.opening_cast: list[str]` holds the NPC keys staged by `opening_scene.stage_opening_scene()` from the story's `opening.welcome_party`; it and `main_character_id` are persisted by `_serialize_state`. See `design/SOCIAL_ENGINE.md (social mode)` §10.

**`mode.romance_goal` (optional story rule):** `enabled`, `partner_gender`, `rival_gender`, `outcome` are author-time fields retained in `story_cfg.mode`, without a new persisted state field. `_canonicalize_story_cfg` now also retains `characters[].gender` so `prompt_builder._mode_context_section` and the world-model `rivalry_context` can filter the active cast by player gender. Current supported Terrace values are `opposite_player` and `same_as_player`; other stories remain unaffected. This is an objective/context and offscreen-weight rule, not yet a validated win condition (BL-33).

**`voice` (personality/speech-style mechanism):** each `characters[]` entry may also declare a `voice: [<speech-style cues>]` array — diction, sentence rhythm, verbal tics, catchphrases, and other HOW-they-talk cues, kept deliberately separate from `self_knowledge` (WHAT they know/believe). Parsed by `Character.from_dict()`/serialized by `Character.to_dict()` the same way as `self_knowledge`. `prompt_builder._identity_block()` renders a character's `voice` cues in their `### CHARACTER IDENTITY` block under a "speech style" subsection, instructing the model to keep every line of that character's dialogue distinct from other characters in the scene. Empty/absent `voice` renders no extra section — additive, no effect on stories that don't author it. All 17 authored members of `7_six_strangers/six_strangers_story.json` have a `voice` profile.

---

### Character Relationships

| Class | File | What it is |
|---|---|---|
| `CharacterType` | `backend/app/engine/character_graph.py` | Engine-level character classification: `USER` (human player, key="player"), `MAIN` (focal NPC, is_main=True), `CANONICAL` (authored NPC with knowledge bundle), `NPC` (incidental/hallucinated). Distinct from the free-form `role` string. |
| `CharacterGraph` | `backend/app/engine/character_graph.py` | **Pure data layer.** Directed graph storing character nodes (`characters: Dict[str, Character]`) and edges (`edges` keyed `"{from_id}->{to_id}"`). One edge per ordered pair, enforced. Query methods: `get_edge`, `get_edges_from`, `get_edges_to`, `get_all_relationships`, `get_room_relationships`. Returns raw edges only — all prose generation is in `prompt_builder.py`. |
| `RelationshipEdge` | `backend/app/engine/character_graph.py` | One directed edge (from_id → to_id): type, state (4D numeric), `label` (static authored context), `narrative` (dynamic runtime note, replaced each update), `narrative_log` (append-only session history). |
| `RelationshipState` | `backend/app/engine/character_graph.py` | Four float dimensions: trust (-1..1), fear (0..1), affection (-1..1), suspicion (0..1). |
| `RelationshipType` | `backend/app/engine/character_graph.py` | Enum: FRIEND, ENEMY, FAMILY, LOVER, EMPLOYER, EMPLOYEE, SUSPECT, VICTIM, WITNESS, OTHER. |

**Factory**: `make_player_character(display_name)` in `state.py` creates the `USER` node (`key="player"`) at game init. Not defined in story JSON.

---

### Epistemic / Knowledge (truth and belief)

| Class | File | What it is |
|---|---|---|
| `KnowledgeChunk` | `backend/app/engine/knowledge_chunks.py` | **Universal knowledge unit.** Replaces EpistemicEntry / EpistemicFact / EpistemicClaim / Observation. Fields: id, text, content (alias for text), tier, source, certainty, known_by, not_known_by, maybe_known_by, kind ("fact"/"claim"/"observation"), subject, object, timestamp_minute, location_ref, confidence, provenance, status, resolution. Used by canonical truth, belief layer, and FAISS/BM25 retrieval. |
| `BeliefState` | `backend/app/engine/epistemic_state.py` | All claims + observations for one character. Both fields are `List[KnowledgeChunk]`. |
| `EpistemicStatus` | `backend/app/engine/epistemic_state.py` | Enum: ASSERTED, CONTESTED, RESOLVED. Still used for comparison; KnowledgeChunk.status stores matching string values. |
| `CharacterIndexBundle` | `backend/app/knowledge/contracts/index_bundle.py` | Runtime FAISS + BM25 index for one character's knowledge chunks. `chunks` is still `List[dict]` (raw JSONL dicts); conversion to KnowledgeChunk objects is a future cleanup. |

**Backward-compat aliases in `epistemic_state.py` (do not use in new code):**
- `EpistemicEntry = KnowledgeChunk`
- `EpistemicFact = KnowledgeChunk`
- `EpistemicClaim = KnowledgeChunk`
- `Observation = KnowledgeChunk`

Use `kind="fact"`, `kind="claim"`, `kind="observation"` on `KnowledgeChunk` to distinguish.

---

### World / Location

| Class | File | What it is |
|---|---|---|
| `Location` | `backend/app/engine/world/location.py` | One atomic place: id, name, description, tags, allows_phone, is_transit, uuid. |
| `LocationId` | `backend/app/engine/world/ids.py` | Type-safe string wrapper for location IDs. |
| `WorldGraph` | `backend/app/engine/world/graph.py` | All locations + edges. The authoritative map. |
| `PathEdge` | `backend/app/engine/world/edge.py` | Directed connection between two locations: from_id, to_id, minutes, blocked. |
| `WorldDefinition` | `backend/app/engine/world/world_json.py` | Parsed world JSON: graph + exposure config + travel timing. Frozen. |
| `WorldClock` | `backend/app/engine/world/clock.py` | Single source of truth for game time (minutes since world start). |


### Character & World Model (`backend/app/engine/world_model/`, saved as `GameState.world_model`)

| Class | File | What it is |
|---|---|---|
| `WorldModel` | `world_model/model.py` | Aggregate saved with a game: world, characters, memories, threads, contact queue, traces, seed, turn. `view` (TurnView) is per-turn and not saved. |
| `World` | `world_model/world.py` | Location index `where` (entity -> place, the single source; `contents` derived), clock helpers, immutable `events`. `move()` is the only location writer. |
| `Entity` | `world_model/entities.py` | Anything that can be somewhere: character, player, object, evidence (aliases, props/surfaces). |
| `Event` | `world_model/events.py` | World truth: minute, place, participants, truth text (`@id` refs), kind, visibility. Never changes. |
| `CharacterState` | `world_model/character.py` | Per-character body/mind: availability, activity, mood, routine, speaking recency, descriptor, slot group. `get_location()` reads the world index. |
| `Memory` / `Ref` / `MemoryStore` | `world_model/memory.py` | One owner's perspective with a source channel (witnessed / told_by:x / overheard / authored / promised), confidence, event link, `@id` refs; `Ref.actual` is engine-only. |
| `Routine` / `RoutineBlock` | `world_model/routine.py` | Time blocks (may wrap midnight, weekday filters, seeded jitter, `hard`), home and free place. |
| `Thread` / `Milestone` | `world_model/threads.py` | Personal arcs with milestones on the clock; public milestones leave traces. |
| `Trace` / `ContactMessage` / `SpeakerPlan` / `TurnView` | `world_model/model.py` | Noticeable consequences; queued texts/calls; engine-chosen speakers; the per-turn projection rendered into the prompt. |

---

### Travel

| Class | File | What it is |
|---|---|---|
| `TravelRoute` | `backend/app/engine/world/travel_rules.py` | A resolved path from A to B as a sequence of hops. |
| `TravelSegment` | `backend/app/engine/world/travel_rules.py` | One hop in a route (wraps a PathEdge). |
| `TravelRules` | `backend/app/engine/world/travel_rules.py` | Seeded, deterministic route selection logic. |
| `TravelRequest` | `backend/app/engine/world/travel_resolver.py` | A travel intent: from_id + to_id. |
| `TravelResult` | `backend/app/engine/world/travel_resolver.py` | Result of executing travel: route, exposure (TravelExposure), start/end minutes. |
| `TravelTiming` | `backend/app/engine/world/travel_resolver.py` | Timing parameters (e.g., exit_minutes). |
| `TravelResolver` | `backend/app/engine/world/travel_resolver.py` | Executes travel, advances world clock. |
| `TravelExposure` | `backend/app/engine/world/exposure.py` | What the AI is allowed to know about a travel event: exit_event, pass_intermediate, event_at_intermediate, enter_event, describe_destination, intermediate_id. Single exposure class (ExposurePacket was deleted). |
| `ExposureConfig` | `backend/app/engine/world/exposure.py` | Probability slots for travel exposure events. |
| `ExposureResolver` | `backend/app/engine/world/exposure.py` | Rolls exposure events according to probability config. Returns TravelExposure directly. |

---

### Extractors (LLM-backed structured parsing)

| Class | File | What it is |
|---|---|---|
| `TurnExtraction` | `backend/app/engine/extractors/turn_extractor.py` | Output of the single-call extractor: movement intent + knowledge updates. |
| `TurnKnowledgeResolution` | `backend/app/engine/extractors/turn_extractor.py` | Per-chunk knowledge resolution from turn extraction. |
| `TurnExtractor` | `backend/app/engine/extractors/turn_extractor.py` | Single-call LLM extractor for movement + scene signals + knowledge updates. |
| `LocationExtraction` | `backend/app/engine/extractors/location_extractor.py` | Movement intent from a player message: NONE or MOVE + destination_id. |
| `LocationIntent` | `backend/app/engine/extractors/location_extractor.py` | Enum: NONE, MOVE. |
| `LocationExtractor` | `backend/app/engine/extractors/location_extractor.py` | Lightweight location intent extractor. |
| `KnowledgeResolution` | `backend/app/engine/extractors/knowledge_resolution_extractor.py` | Whether an NPC knows an ambiguously-labeled chunk (knows, confidence, reason). |
| `KnowledgeResolutionExtractor` | `backend/app/engine/extractors/knowledge_resolution_extractor.py` | LLM extractor for knowledge chunk resolution. |

---

### Invariant Checking (post-generation validation)

| Class | File | What it is |
|---|---|---|
| `AnchorFact` | `backend/app/engine/invariant_validator.py` | Identity/fact anchor used for post-generation checks. |
| `InvariantCheck` | `backend/app/engine/invariant_validator.py` | Specifies what to validate (ANCHOR_CONTRADICTION, SPEAKER_IDENTITY_DRIFT). |
| `InvariantContract` | `backend/app/engine/invariant_validator.py` | Full validation contract for a speaker: anchors + checks. |
| `Violation` | `backend/app/engine/invariant_validator.py` | A detected invariant violation: type, description, matched text. |

---

### Transient / Scene Memory

| Class | File | What it is |
|---|---|---|
| `TransientKnowledge` | `backend/app/engine/transient_buffer.py` | Short-lived knowledge that decays over turns (TTL-based). Feeds FAISS retrieval. |
| `SceneKnowledge` | `backend/app/engine/transient_buffer.py` | Per-turn scene snapshot: location, speakers, people present, payload. |

---

### Evaluation Arena (beta vs prod) - local-only skill tooling, not part of the deployed app

Design: `design/JEV_GAME_ARENA.md`. All plain data, JSON round-trippable, persisted under `data/eval_arena/<experiment_id>/`.

| Class | File | What it is |
|---|---|---|
| `ExperimentManifest` | `.claude/skills/promote-to-prod/arena/contracts.py` | Immutable experiment identity (targets, judge model, rubric hash, player model/prompt, bundle hashes, pairs, seed, budget, capabilities). `manifest_hash` = sha256 of canonical JSON. |
| `TargetIdentity` | `.claude/skills/promote-to-prod/arena/contracts.py` | A release as reported by `/api/health`; `pin_key` = (commit, deployment_id, content_schema_version). |
| `PairSpec` / `ScenarioSpec` / `PersonaSpec` | `.claude/skills/promote-to-prod/arena/contracts.py` | One paired scenario replicate (the statistical unit), its starting condition and player persona. |
| `TurnRecord` / `ObservedState` / `ArmTranscript` | `.claude/skills/promote-to-prod/arena/contracts.py` | One player action + public reply + `[D]` observation; one side's full game with `ArmStatus`. |
| `Rubric` / `Dimension` / `CriticalProbe` | `.claude/skills/promote-to-prod/arena/rubric.py` | Judged dimensions, weights, criteria and per-side critical yes/no probes. |
| `GameKnowledgeBundle` / `CanonFact` / `LocationNode` | `.claude/skills/promote-to-prod/arena/knowledge.py` | Judge-side oracle built from authored story/world JSON; protected facts; directed world graph. |
| `EvidencePacket` | `.claude/skills/promote-to-prod/arena/evidence.py` | One blinded, fenced, token-bounded Jev `state` for one window in one A/B order. |
| `JudgeCall` / `ValidatedAnswer` | `.claude/skills/promote-to-prod/arena/judge.py` | One judge request record and its fail-closed per-question answers. |
| `Vote` / `EpisodeDecision` / `EpisodeOutcome` / `RatingSummary` | `.claude/skills/promote-to-prod/arena/aggregate.py` | Rating math units: dimension vote, episode decision, stratified outcome, headline summary. |
| `CheckFinding` | `.claude/skills/promote-to-prod/arena/checks.py` | Deterministic correctness finding (check id, severity, turn). |

---

### Prompt Assembly

| Class / Function | File | What it is |
|---|---|---|
| `PromptInput` | `backend/app/engine/prompt_builder.py` | Single source of truth for all model-bound inputs: state, log, user_msg, knowledge_chunks, truth_mode. |
| `_summarize_room_relationships(edges, chars)` | `backend/app/engine/prompt_builder.py` | Deterministic prose generator from raw `List[RelationshipEdge]`. Detects warmth, hostility, fear, suspicion, attraction, jealousy triangles. No LLM. |
| `_room_relationship_section(state, room_ids)` | `backend/app/engine/prompt_builder.py` | Calls `graph.get_room_relationships(room_ids)` → raw edges → `_summarize_room_relationships` → `[ROOM DYNAMICS]` prompt section. Called on location entry. |
| `_relationship_scene_section(state)` | `backend/app/engine/prompt_builder.py` | Per-speaker relationship detail (outgoing edges from main NPC, with word-mapped dimensions + `[Context]` + `[Now]` narrative). Always injected. |

---

### Time Utilities

| Class | File | What it is |
|---|---|---|
| `WorldTimestamp` | `backend/app/engine/time_utils.py` | A formatted world time: iso string + human display string. |
| `WorldTimeFormatter` | `backend/app/engine/time_utils.py` | Converts game minutes to a WorldTimestamp. |

---

### Configuration

| Class | File | What it is |
|---|---|---|
| `EpistemicSwitches` | `backend/app/config/epistemic_flags.py` | Feature toggles for epistemic layers: master, truth, belief, narrative, retrieval. |

---

### Integration Tests

| Class | File | What it is |
|---|---|---|
| `IntegrationScenario` | `backend/app/integration_playback/scenario.py` | Base class for integration test scenarios (setup, steps, run_as_test). |
| `Scenario` | `backend/app/integration_playback/scenario.py` | Legacy dataclass wrapper (backward compat). |
| `Step` | `backend/app/integration_playback/scenario.py` | One test step: kind (action/assert/note), function, uses_llm. |
| `StepDescriptor` | `backend/app/integration_playback/scenario.py` | Lightweight description of a class-based step (for introspection). |

---

### Known Structural Gaps / Consolidation Candidates

| Issue | Current state | Better state |
|---|---|---|
| `CharacterIndexBundle.chunks` | `List[dict]` — raw JSONL dicts loaded from disk | Convert to `List[KnowledgeChunk]` at load time; update all retrieval callers |
| `EpistemicStatus` enum vs string `status` field | `KnowledgeChunk.status` is a plain string; `EpistemicStatus` enum is still used for comparison | Eventually make `KnowledgeChunk.status` typed as `EpistemicStatus` or remove the enum |
