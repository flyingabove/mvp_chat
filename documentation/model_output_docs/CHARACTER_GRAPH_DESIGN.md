# Character Graph Design

Last updated: 2026-02-26

## What Is the Character Graph?

The character graph is a directed graph that models every participant in the story — including the human player — and how they relate to each other. Every participant is a **node** (a `Character` object). Every relationship between two participants is a **directed edge** (`RelationshipEdge`) carrying structured numeric state plus human-readable prose.

The graph serves three purposes:
1. **Prompt construction** — tell the AI how a character feels about the people in the scene so it can calibrate tone, hostility, and willingness to cooperate.
2. **Game mechanics** — relationship thresholds can gate behaviors (e.g., a suspect only confesses when `trust > 0.5` and `fear > 0.7`).
3. **Debug visibility** — the developer can inspect the full relationship state at any point to verify the AI's behavior makes sense.

---

## Character Types

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

## Graph Structure

`CharacterGraph` stores both nodes and edges:

```
CharacterGraph
├── characters: Dict[str, Character]         # key → Character node
└── edges: Dict[str, RelationshipEdge]       # "{from_id}->{to_id}" → edge
```

**Edge uniqueness**: exactly one directed edge per `(from_id, to_id)` pair. Internally keyed as `"{from_id}->{to_id}"` for O(1) lookup. Uniqueness is enforced on write — no duplicate edges can exist.

**Directed means asymmetric**: IU's feelings toward the player are a separate edge from the player's feelings toward IU. They can differ.

---

## Node: Character

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

## Edge: RelationshipEdge

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

### Relationship History Fields

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

## Player as a Character

The player is a full first-class character in the graph (`character_type = USER`, key = `"player"`). Player→NPC edges are created by `process_first_meetings()` just like NPC→NPC edges. The player's relationship state toward each NPC is tracked independently and updated by three mechanisms:

| Update source | What it updates | When |
|---|---|---|
| `process_first_meetings()` | `met_at`, `last_met_at`, `meeting_count` on player→NPC edge | Each room entry |
| `TurnExtractor` `relationship_state_updates` | Trust/fear/affection/suspicion/jealousy deltas on player→NPC edge | Each turn — inferred from player's message |
| `TurnExtractor` `relationship_history_updates` | `prior_relationship`, `prior_intimacy`, `in_relationship` on player→NPC edge | When player's dialogue explicitly confirms |

### Player Attitude Deltas (RelationshipStateUpdate)

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

### Player Attitude in the NPC's Prompt

The NPC's relationship context section (`[RELATIONSHIP CONTEXT IN THIS SCENE]`) shows the NPC→player edge as normal. Additionally, when the player→NPC reverse edge has been updated, a `[Player's attitude toward {NPC}: ...]` tag is appended to show the NPC how the player is currently treating them. This lets the NPC calibrate their response to the player's revealed attitude.

---

### RelationshipState (multi-dimensional)

| Dimension   | Range  | Levels | What it means |
|-------------|--------|--------|---------------|
| `trust`     | -1..1  | 21 (0.1 step) | How much A trusts B. Negative = active distrust. |
| `fear`      | 0..1   | 21 (0.1 step) | How afraid A is of B. High fear + low trust = defensive/hostile. |
| `affection` | -1..1  | 21 (0.1 step) | Emotional warmth. Negative = resentment/hatred. |
| `suspicion` | 0..1   | 21 (0.1 step) | How much A suspects B of wrongdoing. |
| `jealousy`  | 0..1   | 5 (0.25 step) | How jealous A is toward B. Five named levels (see below). |

These dimensions are independent. A suspect can have high fear (0.9) AND moderate trust (0.3) toward the detective simultaneously — they're scared but believe the detective will honor a deal. This nuance is impossible with a single integer score.

### Jealousy Levels (5 discrete word levels)

| Value | Word | Meaning |
|-------|------|---------|
| 0.00 | `secure` | No jealousy — relationship feels unthreatened |
| 0.25 | `mild` | Low-level envy or mild possessiveness |
| 0.50 | `moderate` | Noticeable jealousy influencing behavior |
| 0.75 | `strong` | Openly jealous, likely to act on it |
| 1.00 | `consuming` | Obsessive jealousy dominating all interactions |

### Per-Interaction Increment Bounds

All five dimensions are bounded per turn. Constants stored in `backend/app/config/settings.py`:

| Constant | Value | Meaning |
|----------|-------|---------|
| `REL_TRAIT_DELTA_MIN` | 0.05 | Smallest non-zero change per interaction |
| `REL_TRAIT_DELTA_MAX` | 0.20 | Largest change per interaction |

A delta of 0 is also valid (nothing changed this turn). These are tunable without touching game logic.

### RelationshipType

```
FRIEND, ENEMY, FAMILY, LOVER, EMPLOYER, EMPLOYEE, SUSPECT, VICTIM, WITNESS, OTHER
```

Set at story creation time. Can change during gameplay (e.g., FRIEND becomes ENEMY after a betrayal).

---

## Query Interface

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

## Layered Architecture: Data vs. Prose

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

## Room Scenario: Location Entry Pipeline

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

## Relationship Summarizer (in prompt_builder.py)

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

## Per-Speaker Detail (format_for_prompt)

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

## Deterministic Language Layer

Numeric dimension values are converted to human-readable words deterministically (no LLM, no randomness):

- `trust` and `affection`: already on -1..1 scale.
- `fear` and `suspicion`: stored as 0..1, normalized to -1..1 via `(value * 2) - 1`.
- Each normalized value is clamped to [-1, 1], rounded to nearest 0.1, then mapped to a fixed vocabulary word.
- Runtime helper: `describe_relationship_state()` in `character_graph.py`.

---

## Edge Mutation

### Legacy backward-compat (still works)
```python
graph.apply_rel_delta(from_id="iu", to_id="player", rel_delta=-1)
# Maps ±1 integer to ±0.1 affection delta. Preserved for existing story JSONs.
```

### Full 4D update
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

### STATE tag format (applied each turn by apply_state_tag())

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

## Story JSON Format

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

## Implementation Status

**All three phases are implemented.**

### Files

| File | Role |
|---|---|
| `backend/app/engine/character_graph.py` | **Pure data layer.** `CharacterType`, `RelationshipType`, `RelationshipState`, `RelationshipEdge`, `CharacterGraph` (nodes + edges + queries only — no prose) |
| `backend/app/engine/state.py` | `Character` (with `character_type` field), `make_player_character()`, `GameState.character_graph`, `apply_state_tag()` |
| `backend/app/engine/story_loader.py` | Parses `relationships` into `CharacterGraph`; parses characters into `Character` objects |
| `backend/app/engine/prompt_builder.py` | **Prose-generation layer.** `_summarize_room_relationships(edges, chars)` — deterministic prose from raw edges. `_room_relationship_section(state, room_ids)` — calls graph query + summarizer. `_relationship_scene_section(state)` — per-speaker detail (existing). |
| `backend/app/api/prompt_engine.py` | Applies `rel_delta` post-turn; applies `relationship_state_updates` and `relationship_history_updates` from `TurnExtractor` |
| `backend/app/engine/extractors/turn_extractor.py` | `RelationshipStateUpdate` (player attitude deltas), `RelationshipHistoryUpdate` (history flags), `TurnExtraction` |
| `backend/app/integration_playback/scenarios/scenario_turn_extractor_relationships_llm.py` | Real-LLM integration scenario: 6 steps testing relationship extraction accuracy |

### What is built
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

### What is pending (see plan)
- `rel_updates` array in STATE tag for LLM to drive multi-edge 4D updates (wired in `apply_state_tag()`)
- Prompt builder section for `summarize_relationships()` injected at room entry
