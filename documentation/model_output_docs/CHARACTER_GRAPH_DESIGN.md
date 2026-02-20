# Character Graph Design (Implemented)

## What Is the Character Graph?

The character graph is a directed graph that models every character in a story and how they relate to each other. Each character is a node. Each relationship between two characters is a directed edge carrying structured state (trust, fear, affection, suspicion). "Directed" means Steve's feelings toward Bob can differ from Bob's feelings toward Steve.

The graph serves three purposes:
1. **Prompt construction** — tell the AI how a character feels about the people in the scene so it can calibrate tone, hostility, willingness to cooperate.
2. **Game mechanics** — relationship thresholds can gate behaviors (e.g., a suspect only confesses when trust > 0.5 and fear > 0.7).
3. **Debug visibility** — the developer can inspect the full relationship state at any point to verify the AI's behavior makes sense.

## Current State (what exists today)

Today the engine has a single integer `relationship` field on `MurderGameState` (range -5 to +5). Every turn, the AI outputs a `rel_delta` of -1, 0, or +1, and the engine adds it. This score is global — it represents the player's relationship with "the character" as a whole, not between specific character pairs.

Problems:
- **One dimension collapses everything.** A suspect can fear the detective AND trust them simultaneously (classic interrogation dynamic). A single score can't represent this.
- **No character-to-character relationships.** Steve's opinion of Bob matters for interrogation strategy (can you play them against each other?) but isn't modeled.
- **No typed edges.** The system doesn't know if two characters are friends, enemies, family, or co-conspirators. The prompt builder can't use this information because it doesn't exist structurally.

## Proposed Design

### Nodes: CharacterModel

Each character in the story becomes a `CharacterModel` node in the graph. A character has:

- **Identity**: display name, archetype (e.g., "nervous suspect"), tags (e.g., `["suspect", "ex-boyfriend"]`).
- **Traits**: tone of voice, speech style, behavioral quirks. Used by the prompt builder to differentiate how characters talk.
- **Motivation**: primary goal, secondary goals, fears, needs. Drives the AI's decision-making about what the character reveals or conceals.
- **Epistemic profile**: what this character knows (chunk IDs), believes, and has forgotten. Determines what information they can share.
- **Anchors**: identity anchors that must never be contradicted (e.g., "You are IU. You are a ghost."). These are injected into the prompt every turn.
- **Location binding**: which locations this character appears at (if any). A character in Interview Room A is not available in Interview Room B.

### Edges: RelationshipEdge

An edge connects two characters with:

```
RelationshipEdge:
  id: str                    # unique edge identifier
  from_character_id: str     # who holds this opinion
  to_character_id: str       # about whom
  type: RelationshipType     # FRIEND, ENEMY, FAMILY, LOVER, SUSPECT, VICTIM, etc.
  state: RelationshipState   # multi-dimensional emotional state
  supporting_chunk_ids: []   # evidence/events that shaped this relationship
  symmetric: bool            # if true, the reverse edge mirrors this one
```

### RelationshipState (multi-dimensional)

Instead of one integer, each edge carries:

| Dimension  | Range  | What it means |
|------------|--------|---------------|
| `trust`    | -1..1  | How much A trusts B. Negative = active distrust. |
| `fear`     | 0..1   | How afraid A is of B. High fear + low trust = defensive/hostile. |
| `affection`| -1..1  | Emotional warmth. Negative = resentment/hatred. |
| `suspicion`| 0..1   | How much A suspects B of wrongdoing. |
| `custom`   | dict   | Story-specific dimensions (e.g., `"guilt": 0.8`). |

These dimensions are independent. A suspect can have high fear (0.9) AND moderate trust (0.3) toward the detective — they're scared but believe the detective will honor the cooperation deal. This nuance is impossible with a single score.

### RelationshipType enum

```
FRIEND, ENEMY, FAMILY, LOVER, EMPLOYER, EMPLOYEE, SUSPECT, VICTIM, WITNESS, OTHER
```

The type is the "label" on the edge. It's set at story creation time and can change during gameplay (e.g., FRIEND becomes ENEMY after a betrayal). The type informs prompt construction — knowing Steve and Bob are CO_CONSPIRATORS tells the AI they'll protect each other until pressure breaks them.

## How the Graph Gets Used

### 1. Prompt injection

When building the prompt for a turn, the engine:
1. Identifies the current speaker (from location → speaker mapping).
2. Looks up all edges FROM that speaker.
3. Injects a relationship summary into the prompt:
   ```
   Your feelings about the people you know:
   - Bob: co-conspirator. Trust: 0.4, Fear: 0.2, Suspicion: 0.1.
     You've been friends for years but you're starting to wonder if he'll crack first.
   - Detective (player): adversary. Trust: -0.3, Fear: 0.7, Suspicion: 0.0.
     You're terrified but trying not to show it.
   ```
4. The `supporting_chunk_ids` can optionally pull in the specific events that shaped the relationship, giving the AI concrete memories to reference.

### 2. Behavior gating

Relationship thresholds can trigger game events:
- Steve confesses only when `fear > 0.8` AND `trust > 0.3` (scared enough to talk, trusts the deal enough to take it).
- Bob turns on Steve only when `suspicion(Bob→Steve) > 0.6` (believes Steve will betray him).
- A character becomes hostile when `affection < -0.5`.

### 3. Delta application

Each turn, the AI outputs relationship deltas (currently `rel_delta: -1|0|1`). In the new system, the extractor would output per-dimension deltas:

```json
{
  "rel_updates": [
    {"target": "steve", "trust_delta": 0.1, "fear_delta": -0.05}
  ]
}
```

The engine applies these deltas and clamps values to their valid ranges.

### 4. Debug panel

The debug box can show the full relationship state:
```
Relationships (Steve's perspective):
  → Bob: trust=0.4, fear=0.2, affection=0.3, suspicion=0.1
  → Player: trust=-0.3, fear=0.7, affection=-0.1, suspicion=0.0
```

This lets the developer verify the AI's behavior aligns with the underlying state.

## Migration from Current System

The current single `relationship` integer maps most closely to `affection` in the new system. Migration path:

1. **Phase 1 (backward compatible):** Keep the existing `rel_delta` output format. The engine maps it to `affection` on the player→character edge. Other dimensions default to neutral.
2. **Phase 2 (multi-dimensional extraction):** Update the extractor to output per-dimension deltas. Update the prompt builder to inject the full relationship summary.
3. **Phase 3 (character-to-character):** Add edges between NPCs (e.g., Steve↔Bob). These start from story JSON and evolve based on gameplay events.

## Story JSON Format

Characters and relationships are defined in the story JSON:

```json
{
  "characters": [
    {
      "key": "steve",
      "name": "Steve",
      "role": "Fictional ex-boyfriend",
      "is_suspect": true,
      "tags": ["suspect"],
      "motivation": {
        "primary": "Avoid prison",
        "fears": ["being betrayed by Bob", "life sentence"],
        "needs": ["the cooperation deal"]
      }
    }
  ],
  "relationships": {
    "edges": [
      {
        "id": "steve_to_bob",
        "from": "steve",
        "to": "bob",
        "type": "FRIEND",
        "state": {"trust": 0.5, "fear": 0.1, "affection": 0.4, "suspicion": 0.2},
        "symmetric": false
      },
      {
        "id": "bob_to_steve",
        "from": "bob",
        "to": "steve",
        "type": "FRIEND",
        "state": {"trust": 0.3, "fear": 0.3, "affection": 0.3, "suspicion": 0.5}
      }
    ]
  }
}
```

Note that Steve→Bob and Bob→Steve have different states. Bob is more suspicious of Steve than Steve is of Bob. This asymmetry drives gameplay: Bob might crack first if the detective plays on his suspicion.

## Relationship to Location Binding

Characters exist at specific locations. The `location_speakers` map in the world config determines who speaks where. The character graph complements this: it tells you not just WHO is at a location, but how they FEEL about the other characters. When the player is in Interview Room A with Steve, the prompt needs both:
- Steve is the speaker here (from location binding)
- Steve's relationship state toward the player and toward Bob (from the character graph)

## Open Questions

1. **Should relationship edges be mutable or append-only?** Mutable is simpler. Append-only (with snapshots) enables time-travel debugging ("what was Steve's trust in Bob at turn 5?").
2. **How granular should extractor deltas be?** Per-dimension floats give precision but demand more from the extractor LLM. Coarser options: the extractor outputs a sentiment label (e.g., "more trusting") and the engine maps it to a fixed delta.
3. **Should the player node exist in the graph?** Currently the player is not a character node — they're the void that characters react to. Adding a player node would let NPCs have structured opinions about the player, but it adds complexity.

## Implementation Status

**Phase 1 (backward compatible) is implemented.** The following modules make this work:

- **`backend/app/engine/character_graph.py`** — Production module with `RelationshipType`, `RelationshipState`, `RelationshipEdge`, and `CharacterGraph` classes.
- **Story JSONs** — Both `iu_murder_mystery_story.json` and `jennie_murder_mini_story.json` have `"relationships": { "edges": [...] }` sections with initial character-to-character edges.
- **`backend/app/engine/story_loader.py`** — Parses `relationships` into `CharacterGraph` as part of `StoryDefinition`.
- **`backend/app/engine/state.py`** — `MurderGameState.character_graph` field; `apply_state_tag()` routes `rel_delta` through `CharacterGraph.apply_rel_delta()` (maps to affection delta).
- **`backend/app/engine/prompt_builder.py`** — Injects "YOUR FEELINGS ABOUT THE PEOPLE YOU KNOW" section into the system prompt from the character graph.
- **`scripts/scorer/story_agent_ui.py`** — Scorer context modal shows relationship layer with color-coded tag.

The legacy `rel_delta` (-1/0/+1) output format is preserved. The integer `state.relationship` continues to work in parallel.

**Phase 2 (multi-dimensional extraction) and Phase 3 (NPC-to-NPC runtime updates)** are future work.
