# Story JSON v2 Redesign (Engine‑First Canon + Epistemic Enforcement)

**Repository context:** `mvp_chat.zip` (this project)  
**Primary pain:** the model can drift on *core identity canon* (e.g., IU ghost speaking about “her” as if IU is a different entity), because canonical anchors are not represented or enforced as a first‑class concept.

This document specifies a **complete story package format** (JSON) and a **Python implementation plan** (dataclasses + loader + turn contract + invariant validation) that supports:

- Any story / any number of characters / arbitrary attributes
- Clean JSON → Python object translation (Java‑ish OOP style)
- Canon tiers (**ANCHOR** vs **CANON** vs **SECRET_CANON** vs **CLAIM** vs **RUMOR**)
- Character epistemics (known / believed / forgotten) with trigger‑based memory unlock
- A **universal KnowledgeChunk** class compatible with FAISS retrieval
- A first‑class **RelationshipGraph** (character graph)
- Win conditions / objectives
- A robust unit test suite

---

## 1) What’s wrong today (in this repo)

### 1.1 Canon anchors are not modeled
In `backend/app/stories/1_iu_murder_mystery/iu_murder_mystery_story.json`, characters are defined with fields like:

- `key`, `name`, `role`, `is_main`, `knowledge_character_id`, `uuid`, `tags`

There is **no representation** for:
- “identity anchors” that must never be contradicted (e.g., **You are IU**)
- “true but unknown” facts (e.g., killer identity) separate from character memory
- “known vs believed vs forgotten” structured epistemic state

### 1.2 Prompt rules are global and mode‑conflicting
In `backend/app/engine/prompt_builder.py`, you hardcode global style/behavior rules such as:

- mandatory “cinematic narration” (`Begin EVERY reply with *italicized, cinematic narration*.`)
- “Suspects exist but are NEVER referenced unless the user asks”
- an “ABSOLUTE BAN: NEVER SPEAK AS THE PLAYER” block

These global rules cause:
- **mode conflicts** across stories (ghost story vs interrogation vs freeform)
- canon enforcement treated as “memory text” rather than invariants
- identity drift because nothing constrains it structurally

### 1.3 Retrieval returns text, not canonical objects
Your knowledge stack under `backend/app/knowledge/build/*` builds indexes and retrieves text “chunks”.
But the engine does not tie retrieval to:
- canon tier
- access policy (who is allowed to know)
- invariants (what cannot be contradicted)

So retrieved text can eventually conflict with canon.

---

## 2) Design principles

### 2.1 Separate three layers
1) **World Truth (Canon):** global facts about the universe  
2) **Character Epistemic:** what each character knows/believes/has forgotten  
3) **Turn Contract:** runtime constraints for the current speaker on this turn

### 2.2 Everything is a KnowledgeChunk
Identity, memories, secrets, evidence, rules, rumors — unify into one object:

- enables consistent retrieval (FAISS returns `chunk_id`)
- enables enforcement by canon tier and access policy

### 2.3 Canon tiers are metadata
Core identity facts (e.g., “You are IU”) must be **ANCHOR** chunks that:
- are injected every turn for that speaker
- cannot be contradicted (validator enforces)

### 2.4 “IU forgot she is IU” is supported
A character can have **amnesia** without contradicting identity anchors:

- The character’s epistemic may not include the “true name” chunk as *known*
- But the ANCHOR still exists and prevents third‑person identity drift
- The character may say “I don’t remember my name,” but never “she was trapped”

---

## 3) StoryPackage v2 (root JSON object)

High‑level JSON shape:

```json
{
  "story_id": "iu_murder_mystery",
  "version": 2,
  "meta": { "...": "..." },
  "game": { "...": "..." },
  "world": { "...": "..." },
  "knowledge": { "chunks": { "...": "..." } },
  "characters": { "...": "..." },
  "relationships": { "edges": { "...": "..." } },
  "win_conditions": { "...": "..." }
}
```

---

## 4) Canon system

### 4.1 Enums

```python
from enum import Enum

class CanonTier(str, Enum):
    ANCHOR = "ANCHOR"
    CANON = "CANON"
    SECRET_CANON = "SECRET_CANON"
    CLAIM = "CLAIM"
    RUMOR = "RUMOR"

class Visibility(str, Enum):
    PUBLIC = "PUBLIC"
    RESTRICTED = "RESTRICTED"
    PRIVATE = "PRIVATE"
    ENGINE_ONLY = "ENGINE_ONLY"
```

---

## 5) Universal KnowledgeChunk

### 5.1 ChunkType

```python
class ChunkType(str, Enum):
    IDENTITY = "IDENTITY"
    FACT = "FACT"
    EVENT = "EVENT"
    MEMORY = "MEMORY"
    EVIDENCE = "EVIDENCE"
    RULE = "RULE"
    RUMOR = "RUMOR"
    NOTE = "NOTE"
```

### 5.2 Dataclasses (drop-in implementation skeleton)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class Content:
    # Human-readable text + optional structured payload for deterministic systems.
    text: str
    data: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class Provenance:
    # Source + confidence are critical for CLAIM/RUMOR.
    source: str = "author"
    confidence: float = 1.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass(frozen=True)
class UnlockRules:
    # Declarative unlock rules; interpreted by extractors/engine.
    required_objective_ids: List[str] = field(default_factory=list)
    required_chunk_ids: List[str] = field(default_factory=list)
    required_location_id: Optional[str] = None
    min_world_minute: Optional[int] = None
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class AccessPolicy:
    # inject_every_turn is used for ANCHORs; speaker_must_not_deny forbids contradiction.
    visibility: Visibility = Visibility.PUBLIC
    allowed_character_ids: List[str] = field(default_factory=list)
    unlock_rules: UnlockRules = field(default_factory=UnlockRules)
    inject_every_turn: bool = False
    speaker_must_not_deny: bool = False

@dataclass(frozen=True)
class KnowledgeChunk:
    # Universal unit of knowledge. Retrieval returns chunk IDs of these.
    id: str
    type: ChunkType
    canon_tier: CanonTier
    access: AccessPolicy
    content: Content
    provenance: Provenance = field(default_factory=Provenance)
    tags: List[str] = field(default_factory=list)
    fields: Dict[str, Any] = field(default_factory=dict)
```

### 5.3 Why KnowledgeChunk is required
- Your current prompt builder (`backend/app/engine/prompt_builder.py`) treats memory as text blocks.
- Canon enforcement requires structured metadata: canon tier + access + invariants.
- Retrieval should return `chunk_id` (not just text), so the engine can enforce policy and update objectives/epistemics.

---

## 6) KnowledgeBase

```python
@dataclass(frozen=True)
class RetrievalIndexSpec:
    embedder: str = "default"
    chunking: Dict[str, Any] = field(default_factory=dict)
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass
class KnowledgeBase:
    chunks: Dict[str, KnowledgeChunk] = field(default_factory=dict)
    retrieval: RetrievalIndexSpec = field(default_factory=RetrievalIndexSpec)
```

---

## 7) Character system (Identity + Traits + Motivation + Epistemic + Anchors)

```python
@dataclass(frozen=True)
class Identity:
    # Minimal stable identity.
    display_name: str
    archetype: str = ""
    tags: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class CharacterTraits:
    tone: str = ""
    speech_style: str = ""
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class MotivationModel:
    primary: str = ""
    secondary: List[str] = field(default_factory=list)
    fears: List[str] = field(default_factory=list)
    needs: List[str] = field(default_factory=list)
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class MemoryTrigger:
    id: str
    condition: str                 # e.g. "mentions:closet"
    unlock_chunk_ids: List[str] = field(default_factory=list)
    probability: float = 1.0
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class MemoryRules:
    triggers: List[MemoryTrigger] = field(default_factory=list)

@dataclass
class EpistemicProfile:
    # known: usable facts, believed: claims/rumors, forgotten: true but inaccessible for now.
    known_chunk_ids: List[str] = field(default_factory=list)
    believed_chunk_ids: List[str] = field(default_factory=list)
    forgotten_chunk_ids: List[str] = field(default_factory=list)
    memory_rules: MemoryRules = field(default_factory=MemoryRules)

@dataclass(frozen=True)
class CharacterAnchors:
    # These must reference KnowledgeChunks with canon_tier=ANCHOR.
    anchor_chunk_ids: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class CharacterHistory:
    experienced_chunk_ids: List[str] = field(default_factory=list)

@dataclass
class CharacterModel:
    id: str
    identity: Identity
    traits: CharacterTraits = field(default_factory=CharacterTraits)
    motivation: MotivationModel = field(default_factory=MotivationModel)
    epistemic: EpistemicProfile = field(default_factory=EpistemicProfile)
    anchors: CharacterAnchors = field(default_factory=CharacterAnchors)
    history: CharacterHistory = field(default_factory=CharacterHistory)
    stats: Dict[str, Any] = field(default_factory=dict)
```

### Why anchors must be separate
This is the direct fix for your IU screenshot issue:

- Epistemic can omit “true name” or “murder details” (amnesia allowed)
- Anchors ensure the character never implies a different identity (no third-person drift)

---

## 8) RelationshipGraph (character graph)

```python
class RelationshipType(str, Enum):
    FRIEND = "FRIEND"
    ENEMY = "ENEMY"
    FAMILY = "FAMILY"
    LOVER = "LOVER"
    EMPLOYER = "EMPLOYER"
    EMPLOYEE = "EMPLOYEE"
    SUSPECT = "SUSPECT"
    VICTIM = "VICTIM"
    WITNESS = "WITNESS"
    OTHER = "OTHER"

@dataclass
class RelationshipState:
    trust: float = 0.0       # -1..1
    fear: float = 0.0        # 0..1
    affection: float = 0.0   # -1..1
    suspicion: float = 0.0   # 0..1
    custom: Dict[str, float] = field(default_factory=dict)

@dataclass
class RelationshipEdge:
    id: str
    from_character_id: str
    to_character_id: str
    type: RelationshipType = RelationshipType.OTHER
    state: RelationshipState = field(default_factory=RelationshipState)
    supporting_chunk_ids: List[str] = field(default_factory=list)
    symmetric: bool = False
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RelationshipGraph:
    edges: Dict[str, RelationshipEdge] = field(default_factory=dict)
```

---

## 9) Objectives / WinConditions

```python
class ObjectiveType(str, Enum):
    DISCOVER_FACT = "DISCOVER_FACT"
    REACH_LOCATION = "REACH_LOCATION"
    CONVINCE_CHARACTER = "CONVINCE_CHARACTER"
    ESCAPE = "ESCAPE"
    SURVIVE = "SURVIVE"
    CUSTOM = "CUSTOM"

class ObjectiveState(str, Enum):
    LOCKED = "LOCKED"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"

class WinRule(str, Enum):
    ALL_OF = "ALL_OF"
    ANY_OF = "ANY_OF"
    SCORE_THRESHOLD = "SCORE_THRESHOLD"

@dataclass
class Objective:
    id: str
    title: str
    type: ObjectiveType = ObjectiveType.CUSTOM
    state: ObjectiveState = ObjectiveState.LOCKED
    required_chunk_ids: List[str] = field(default_factory=list)
    unlock_rules: UnlockRules = field(default_factory=UnlockRules)
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass
class WinConditions:
    objectives: List[Objective] = field(default_factory=list)
    win_rule: WinRule = WinRule.ALL_OF
    props: Dict[str, Any] = field(default_factory=dict)
```

---

## 10) WorldModel (general)

```python
@dataclass(frozen=True)
class TimeModel:
    start_minute: int = 0
    minute_label: str = "minutes_since_start"

@dataclass(frozen=True)
class CommunicationRules:
    allows_phone: bool = False
    allows_text: bool = False
    allows_broadcast: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class LocationModel:
    id: str
    name: str
    tags: List[str] = field(default_factory=list)
    description: str = ""
    comms: CommunicationRules = field(default_factory=CommunicationRules)
    props: Dict[str, Any] = field(default_factory=dict)
    default_present_character_ids: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class MovementEdge:
    id: str
    from_location_id: str
    to_location_id: str
    minutes_cost: int = 1
    probability: float = 1.0
    tags: List[str] = field(default_factory=list)
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MovementGraph:
    edges: Dict[str, MovementEdge] = field(default_factory=dict)

@dataclass
class WorldModel:
    time: TimeModel = field(default_factory=TimeModel)
    locations: Dict[str, LocationModel] = field(default_factory=dict)
    movement: MovementGraph = field(default_factory=MovementGraph)
    systems: Dict[str, Any] = field(default_factory=dict)
```

---

## 11) GameConfig (mode + policies)

```python
@dataclass(frozen=True)
class ExtractorSpec:
    id: str
    purpose: str
    output_keys: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    run_every_turn: bool = True

@dataclass(frozen=True)
class EnforcementPolicy:
    enable_invariant_validator: bool = True
    max_repair_attempts: int = 1
    invariant_types: List[str] = field(default_factory=lambda: [
        "ANCHOR_CONTRADICTION",
        "SPEAKER_IDENTITY_DRIFT",
    ])
    repair_strategy: str = "regen_with_constraints"

@dataclass(frozen=True)
class TurnPolicy:
    time_advances_on_reply: bool = True
    min_minutes_per_turn: int = 1
    max_minutes_per_turn: int = 10
    extractors: List[ExtractorSpec] = field(default_factory=list)
    enforcement: EnforcementPolicy = field(default_factory=EnforcementPolicy)

@dataclass(frozen=True)
class OutputPolicy:
    narration_style: str = "minimal"
    allow_second_person: bool = False
    allow_player_action_narration: bool = False
    required_sections: List[str] = field(default_factory=list)
    formatting: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class GameConfig:
    mode: str = "freeform"
    turn_policy: TurnPolicy = field(default_factory=TurnPolicy)
    output_policy: OutputPolicy = field(default_factory=OutputPolicy)
```

---

## 12) StoryPackage v2 (root)

```python
@dataclass(frozen=True)
class Metadata:
    title: str = ""
    theme: str = ""
    disclaimer: str = ""
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StoryPackageV2:
    story_id: str
    version: int
    meta: Metadata = field(default_factory=Metadata)
    game: GameConfig = field(default_factory=GameConfig)
    world: WorldModel = field(default_factory=WorldModel)
    characters: Dict[str, CharacterModel] = field(default_factory=dict)
    relationships: RelationshipGraph = field(default_factory=RelationshipGraph)
    knowledge: KnowledgeBase = field(default_factory=KnowledgeBase)
    win_conditions: WinConditions = field(default_factory=WinConditions)
```

---

## 13) Loader v2 (how it fits this repo)

### New files to add
- `backend/app/engine/story_schema_v2.py` (all enums + dataclasses + from_dict)
- `backend/app/engine/story_loader_v2.py` (load + validate + return StoryPackageV2)
- `backend/app/engine/turn_contract.py` (TurnContract builder)
- `backend/app/engine/invariant_validator.py` (detect canon violations)
- `backend/app/engine/prompt_builder_v2.py` (contract-driven prompt)

### Keep existing v1
- `backend/app/engine/story_loader.py`
- `backend/app/engine/prompt_builder.py`

Your app can support both by checking `version`.

---

## 14) TurnContract (runtime enforcement)

```python
@dataclass
class Invariant:
    type: str
    description: str
    props: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TurnContract:
    speaker_character_id: str
    injected_anchors: List[KnowledgeChunk]
    allowed_knowledge: List[KnowledgeChunk]
    forbidden_knowledge: List[KnowledgeChunk]
    output_policy: OutputPolicy
    invariants: List[Invariant]
```

### Contract builder rules (required)
- Inject all anchor chunks listed in `CharacterAnchors`
- Inject any chunk with `access.inject_every_turn` that allows the speaker
- Allowed knowledge = known ∪ believed, filtered by access policy
- Forbidden includes SECRET_CANON not unlocked
- Add invariants for each anchor: “must not contradict”
- Add identity drift invariant when identity anchors exist

---

## 15) Validator (fixes the IU screenshot drift)

Create `validate_response(contract, text) -> violations`.

Required checks:
- Direct denial of identity anchor (e.g., “I’m not IU”)
- Third-person self split (“she was trapped”) when anchor implies speaker is that person
- Contradictions of other anchors (closet, binding locus, etc.)

The initial implementation is **best-effort heuristic** — pronoun coreference
is inherently fuzzy and cannot be solved deterministically with regex alone.
The validator catches common patterns and is unit-testable, but may miss
subtle cases. A future LLM-based validation pass can be added as a fallback.

---

## 16) Prompt builder v2

Instead of global prompt rules, structure prompt like:

1) OutputPolicy block (mode-dependent)
2) V1 rules carried forward (no-player-speech, speaker labels)
3) IDENTITY ANCHORS (DO NOT CONTRADICT)
4) KNOWN FACTS YOU MAY USE
5) SECRETS YOU MUST NOT REVEAL
6) Character traits and motivation
7) Scene context (location/time/present)
8) Truth mode override (if active — strips all narrative)
9) Required tail ([[STATE]] tag)

This is what turns canon from "suggestion" into "contract".

---

## 18) Fixes applied to this redesign

The following issues were identified during review and have been addressed
in the implementation:

1. **Validator is heuristic, not deterministic.** Acknowledged in code and docs.
   Pronoun coreference cannot be solved with regex; the validator is best-effort.

2. **`allow_second_person` removed.** Redundant with `allow_player_action_narration`.
   Second-person indirect references ("your words") are always allowed.

3. **`CharacterHistory` is mutable.** `experienced_chunk_ids` grows at runtime;
   `frozen=True` was wrong. Fixed to regular dataclass.

4. **V1 prompt rules carried forward.** No-player-speech and speaker label rules
   are explicitly included in `prompt_builder_v2.py`. Truth mode override is
   ported from v1.

5. **`RelationshipState.collapse()`** maps multi-dimensional state to legacy
   integer score (-5..+5) for backward compatibility.

6. **`MemoryTrigger.condition` format specified.** Uses `"type:value"` syntax:
   `mentions:<keyword>`, `location:<id>`, `minute_gte:<N>`, `chunk_known:<id>`.
   Parsed by `evaluate_triggers()` in `turn_contract.py`.

7. **`LocationModel.speaker_character_ids`** added for location-aware speaker
   resolution. Maps directly to the `location_speakers` concept from v1.

---

## 19) Unit tests (robust list)

### Loader & schema
- minimal v2 loads
- missing required fields fail
- invalid enums fail
- duplicate IDs fail
- anchor chunk ref missing fails
- anchor refs non-ANCHOR fails
- relationship endpoints missing fail
- objective chunk refs missing fail

### TurnContract
- injects anchors every turn
- injectEveryTurn chunks included
- allowed = known ∪ believed
- forbidden includes locked SECRET_CANON
- retrieval included only when access allows

### Validator
- flags “she was trapped” drift
- flags “I’m not IU”
- allows “I don’t remember my name”
- flags closet contradiction
- allows ambiguous language about closet

### Epistemic updates
- triggers unlock chunks
- deterministic probability with seed

### Relationship graph
- apply deltas
- symmetric edge behavior
- evidence refs validated

### Objectives/win
- unlock rules activate
- completion when required chunks discovered
- win rule logic

### Prompt builder v2
- anchors in labeled block
- secrets excluded
- output policy included

### End-to-end mocked turn
- mock output violates anchor → validator triggers repair pass (if enabled)

---
