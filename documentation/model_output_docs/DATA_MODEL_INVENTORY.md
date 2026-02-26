# Data Model Inventory

Complete list of every data model / class in the engine. Reference this when deciding where new data belongs or whether a new class is needed.

Last updated: 2026-02-25

---

## Story / Authoring (static, from JSON)

| Class | File | What it is |
|---|---|---|
| `StoryDefinition` | `backend/app/engine/story_loader.py` | Top-level container parsed from the story JSON. Holds characters, relationships, raw config. |
| `StoryCharacter` | `backend/app/engine/story_loader.py` | One character entry from the story JSON. Static authoring data only (key, name, role, is_main, knowledge_character_id, tags). |

**Note:** `StoryCharacter` is authoring-time data. It gets transformed into `CharacterState` at game start. `self_knowledge` currently lives in `story_cfg["character_self_knowledge"]` (story level), not on the character — this is a known structural gap.

---

## Runtime State

| Class | File | What it is |
|---|---|---|
| `GameState` | `backend/app/engine/state.py` | The entire session container. Holds all sub-objects below. |
| `CharacterState` | `backend/app/engine/state.py` | Runtime per-character data: emotion, relationship score, role, uuid. |
| `UserState` | `backend/app/engine/state.py` | The human player as seen in-story: display name, formal name, gender. |

`GameState` is the single object passed through the entire engine. Everything else hangs off it.

---

## Character Relationships

| Class | File | What it is |
|---|---|---|
| `CharacterGraph` | `backend/app/engine/character_graph.py` | Directed graph of all character-to-character edges. |
| `RelationshipEdge` | `backend/app/engine/character_graph.py` | One directed edge: from_id → to_id, with type + multi-dimensional state. |
| `RelationshipState` | `backend/app/engine/character_graph.py` | Four float dimensions: trust, fear, affection, suspicion. |
| `RelationshipType` | `backend/app/engine/character_graph.py` | Enum: FRIEND, ENEMY, FAMILY, LOVER, EMPLOYER, EMPLOYEE, SUSPECT, VICTIM, WITNESS, OTHER. |

---

## Epistemic / Knowledge (truth and belief)

| Class | File | What it is |
|---|---|---|
| `EpistemicEntry` | `backend/app/engine/epistemic_state.py` | Base dataclass for all knowledge records (id, content, known_by, confidence, status). |
| `EpistemicFact` | `backend/app/engine/epistemic_state.py` | Canonical world truth. Confidence always 1.0. Directly injected into system prompt. |
| `EpistemicClaim` | `backend/app/engine/epistemic_state.py` | Subjective claim made by a character. Can have variable confidence. |
| `Observation` | `backend/app/engine/epistemic_state.py` | What a character saw or heard. Same fields as EpistemicEntry. |
| `BeliefState` | `backend/app/engine/epistemic_state.py` | All claims + observations for one character. |
| `EpistemicStatus` | `backend/app/engine/epistemic_state.py` | Enum: ASSERTED, CONTESTED, RESOLVED. |
| `KnowledgeChunk` | `backend/app/engine/knowledge_chunks.py` | Discrete knowledge unit with tier, source, certainty, and known_by visibility rules. Used in the prompt knowledge stack. |
| `CharacterIndexBundle` | `backend/app/knowledge/contracts/index_bundle.py` | Runtime FAISS + BM25 index for one character's knowledge chunks. |

**Overlap note:** `EpistemicFact`, `EpistemicClaim`, and `Observation` are three subclasses of `EpistemicEntry` with identical fields. They differ only by usage context, not structure.

---

## World / Location

| Class | File | What it is |
|---|---|---|
| `Location` | `backend/app/engine/world/location.py` | One atomic place: id, name, description, tags, allows_phone, is_transit, uuid. |
| `LocationId` | `backend/app/engine/world/ids.py` | Type-safe string wrapper for location IDs. |
| `WorldGraph` | `backend/app/engine/world/graph.py` | All locations + edges. The authoritative map. |
| `PathEdge` | `backend/app/engine/world/edge.py` | Directed connection between two locations: from_id, to_id, minutes, blocked. |
| `WorldDefinition` | `backend/app/engine/world/world_json.py` | Parsed world JSON: graph + exposure config + travel timing. Frozen. |
| `WorldClock` | `backend/app/engine/world/clock.py` | Single source of truth for game time (minutes since world start). |

---

## Travel

| Class | File | What it is |
|---|---|---|
| `TravelRoute` | `backend/app/engine/world/travel_rules.py` | A resolved path from A to B as a sequence of hops. |
| `TravelSegment` | `backend/app/engine/world/travel_rules.py` | One hop in a route (wraps a PathEdge). |
| `TravelRules` | `backend/app/engine/world/travel_rules.py` | Seeded, deterministic route selection logic. |
| `TravelRequest` | `backend/app/engine/world/travel_resolver.py` | A travel intent: from_id + to_id. |
| `TravelResult` | `backend/app/engine/world/travel_resolver.py` | Result of executing travel: route, exposure, start/end minutes. |
| `TravelTiming` | `backend/app/engine/world/travel_resolver.py` | Timing parameters (e.g., exit_minutes). |
| `TravelResolver` | `backend/app/engine/world/travel_resolver.py` | Executes travel, advances world clock. |
| `TravelExposure` | `backend/app/engine/world/exposure.py` | Backward-compat exposure shape (exit_event, pass_intermediate, enter_event, etc.). |
| `ExposurePacket` | `backend/app/engine/world/exposure.py` | Internal v2 exposure packet. `TravelExposure` wraps this. |
| `ExposureConfig` | `backend/app/engine/world/exposure.py` | Probability slots for travel exposure events. |
| `ExposureResolver` | `backend/app/engine/world/exposure.py` | Rolls exposure events according to probability config. |

**Overlap note:** `TravelExposure` exists only for backward compat with `ExposurePacket`. They represent the same data.

---

## Extractors (LLM-backed structured parsing)

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

## Invariant Checking (post-generation validation)

| Class | File | What it is |
|---|---|---|
| `AnchorFact` | `backend/app/engine/invariant_validator.py` | Identity/fact anchor used for post-generation checks. |
| `InvariantCheck` | `backend/app/engine/invariant_validator.py` | Specifies what to validate (ANCHOR_CONTRADICTION, SPEAKER_IDENTITY_DRIFT). |
| `InvariantContract` | `backend/app/engine/invariant_validator.py` | Full validation contract for a speaker: anchors + checks. |
| `Violation` | `backend/app/engine/invariant_validator.py` | A detected invariant violation: type, description, matched text. |

---

## Transient / Scene Memory

| Class | File | What it is |
|---|---|---|
| `TransientKnowledge` | `backend/app/engine/transient_buffer.py` | Short-lived knowledge that decays over turns (TTL-based). Feeds FAISS retrieval. |
| `SceneKnowledge` | `backend/app/engine/transient_buffer.py` | Per-turn scene snapshot: location, speakers, people present, payload. |

---

## Prompt Assembly

| Class | File | What it is |
|---|---|---|
| `PromptInput` | `backend/app/engine/prompt_builder.py` | Single source of truth for all model-bound inputs: state, log, user_msg, knowledge_chunks, truth_mode. |

---

## Time Utilities

| Class | File | What it is |
|---|---|---|
| `WorldTimestamp` | `backend/app/engine/time_utils.py` | A formatted world time: iso string + human display string. |
| `WorldTimeFormatter` | `backend/app/engine/time_utils.py` | Converts game minutes to a WorldTimestamp. |

---

## Configuration

| Class | File | What it is |
|---|---|---|
| `EpistemicSwitches` | `backend/app/config/epistemic_flags.py` | Feature toggles for epistemic layers: master, truth, belief, narrative, retrieval. |

---

## Integration Tests

| Class | File | What it is |
|---|---|---|
| `IntegrationScenario` | `backend/app/integration_playback/scenario.py` | Base class for integration test scenarios (setup, steps, run_as_test). |
| `Scenario` | `backend/app/integration_playback/scenario.py` | Legacy dataclass wrapper (backward compat). |
| `Step` | `backend/app/integration_playback/scenario.py` | One test step: kind (action/assert/note), function, uses_llm. |
| `StepDescriptor` | `backend/app/integration_playback/scenario.py` | Lightweight description of a class-based step (for introspection). |

---

## Known Structural Gaps / Consolidation Candidates

| Issue | Current state | Better state |
|---|---|---|
| `character_self_knowledge` at story level | `story_cfg["character_self_knowledge"]` — flat list on the story, not the character | Move to `StoryCharacter.self_knowledge` → `CharacterState.self_knowledge` |
| `EpistemicFact` / `EpistemicClaim` / `Observation` | Three subclasses with identical fields, differentiated only by usage | Could be one class with a `kind` enum |
| `TravelExposure` / `ExposurePacket` | Two classes for the same data shape | `TravelExposure` exists only for backward compat; can be deleted once callers are updated |
| `WorldLoadResult` | A bag of disparate objects returned by the loader | Not a real domain object; could just be a named tuple or eliminated |
| `StoryCharacter` vs `CharacterState` | Authoring-time vs runtime split is correct, but no explicit migration path | Add explicit `CharacterState.from_story_character()` factory |
