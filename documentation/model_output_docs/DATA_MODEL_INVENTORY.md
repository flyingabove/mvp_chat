# Data Model Inventory

> **What this doc is for:** Complete inventory of all data models and their fields. Edit this doc when any data model, schema, or field is added or changed.

Complete list of every data model / class in the engine. Reference this when deciding where new data belongs or whether a new class is needed.

Last updated: 2026-02-26

---

## Story / Authoring (static, from JSON)

The optional world atlas adds `MapPoint`, `PlaceResearch`, `MapArea`, and `WorldMap`
in `backend/app/engine/world/map_model.py`. `WorldGraph.world_map` owns the atlas;
`Location` adds `area_id`, `map_position`, and `research`; `PathEdge` adds `mode`
and `estimated`. Both world loaders preserve these fields. See
[WORLD_ATLAS_DESIGN.md](WORLD_ATLAS_DESIGN.md) for validation, coordinates and API shape.

| Class | File | What it is |
|---|---|---|
| `StoryDefinition` | `backend/app/engine/story_loader.py` | Top-level container parsed from the story JSON. Holds characters, relationships, raw config. |

**Note:** `StoryCharacter` was deleted — it is now an alias for `Character` (see Runtime State below). Authoring-time character data is parsed directly into `Character` objects.

---

## Runtime State

| Class | File | What it is |
|---|---|---|
| `GameState` | `backend/app/engine/state.py` | The entire session container. Holds all sub-objects below. |
| `Character` | `backend/app/engine/state.py` | Unified character object — authoring identity fields (key, name, role, character_type, is_main, is_suspect, knowledge_character_id, uuid, tags, meta, self_knowledge, voice) merged with runtime state (emotion, relationship). Replaces the former StoryCharacter + CharacterState split. |
| `UserState` | `backend/app/engine/state.py` | The human player as seen in-story: display name, formal name, gender. |

`GameState` is the single object passed through the entire engine. Everything else hangs off it.

**Backward-compat aliases (do not use in new code):**
- `CharacterState = Character` (in `state.py`)
- `StoryCharacter = Character` (in `story_loader.py`)

**`self_knowledge` (BL-07):** each `characters[]` entry in story JSON may declare its own `self_knowledge: [<first-person identity facts>]` array, parsed by `Character.from_dict()` and preserved by `Character.to_dict()` (so it survives `StoryDefinition.from_dict()`'s normalization round-trip). In `prompt_engine.py`, a character's own `self_knowledge` always wins when present; the legacy top-level story JSON `character_self_knowledge` array remains a fallback used only for whichever character is `is_main` and has no per-character `self_knowledge` of its own. See `SOCIAL_MODE_DESIGN.md` §5 for the full injection/gating rule.

**`voice` (personality/speech-style mechanism):** each `characters[]` entry may also declare a `voice: [<speech-style cues>]` array — diction, sentence rhythm, verbal tics, catchphrases, and other HOW-they-talk cues, kept deliberately separate from `self_knowledge` (WHAT they know/believe). Parsed by `Character.from_dict()`/serialized by `Character.to_dict()` the same way as `self_knowledge`. `prompt_builder._identity_block()` renders a character's `voice` cues in their `### CHARACTER IDENTITY` block under a "speech style" subsection, instructing the model to keep every line of that character's dialogue distinct from other characters in the scene. Empty/absent `voice` renders no extra section — additive, no effect on stories that don't author it. All 17 authored members of `7_six_strangers/six_strangers_story.json` have a `voice` profile.

---

## Character Relationships

| Class | File | What it is |
|---|---|---|
| `CharacterType` | `backend/app/engine/character_graph.py` | Engine-level character classification: `USER` (human player, key="player"), `MAIN` (focal NPC, is_main=True), `CANONICAL` (authored NPC with knowledge bundle), `NPC` (incidental/hallucinated). Distinct from the free-form `role` string. |
| `CharacterGraph` | `backend/app/engine/character_graph.py` | **Pure data layer.** Directed graph storing character nodes (`characters: Dict[str, Character]`) and edges (`edges` keyed `"{from_id}->{to_id}"`). One edge per ordered pair, enforced. Query methods: `get_edge`, `get_edges_from`, `get_edges_to`, `get_all_relationships`, `get_room_relationships`. Returns raw edges only — all prose generation is in `prompt_builder.py`. |
| `RelationshipEdge` | `backend/app/engine/character_graph.py` | One directed edge (from_id → to_id): type, state (4D numeric), `label` (static authored context), `narrative` (dynamic runtime note, replaced each update), `narrative_log` (append-only session history). |
| `RelationshipState` | `backend/app/engine/character_graph.py` | Four float dimensions: trust (-1..1), fear (0..1), affection (-1..1), suspicion (0..1). |
| `RelationshipType` | `backend/app/engine/character_graph.py` | Enum: FRIEND, ENEMY, FAMILY, LOVER, EMPLOYER, EMPLOYEE, SUSPECT, VICTIM, WITNESS, OTHER. |

**Factory**: `make_player_character(display_name)` in `state.py` creates the `USER` node (`key="player"`) at game init. Not defined in story JSON.

---

## Epistemic / Knowledge (truth and belief)

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
| `TravelResult` | `backend/app/engine/world/travel_resolver.py` | Result of executing travel: route, exposure (TravelExposure), start/end minutes. |
| `TravelTiming` | `backend/app/engine/world/travel_resolver.py` | Timing parameters (e.g., exit_minutes). |
| `TravelResolver` | `backend/app/engine/world/travel_resolver.py` | Executes travel, advances world clock. |
| `TravelExposure` | `backend/app/engine/world/exposure.py` | What the AI is allowed to know about a travel event: exit_event, pass_intermediate, event_at_intermediate, enter_event, describe_destination, intermediate_id. Single exposure class (ExposurePacket was deleted). |
| `ExposureConfig` | `backend/app/engine/world/exposure.py` | Probability slots for travel exposure events. |
| `ExposureResolver` | `backend/app/engine/world/exposure.py` | Rolls exposure events according to probability config. Returns TravelExposure directly. |

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

## Evaluation Arena (beta vs prod) - local-only skill tooling, not part of the deployed app

Design: `JEV_GAME_ARENA_DESIGN.md`. All plain data, JSON round-trippable, persisted under `data/eval_arena/<experiment_id>/`.

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

## Prompt Assembly

| Class / Function | File | What it is |
|---|---|---|
| `PromptInput` | `backend/app/engine/prompt_builder.py` | Single source of truth for all model-bound inputs: state, log, user_msg, knowledge_chunks, truth_mode. |
| `_summarize_room_relationships(edges, chars)` | `backend/app/engine/prompt_builder.py` | Deterministic prose generator from raw `List[RelationshipEdge]`. Detects warmth, hostility, fear, suspicion, attraction, jealousy triangles. No LLM. |
| `_room_relationship_section(state, room_ids)` | `backend/app/engine/prompt_builder.py` | Calls `graph.get_room_relationships(room_ids)` → raw edges → `_summarize_room_relationships` → `[ROOM DYNAMICS]` prompt section. Called on location entry. |
| `_relationship_scene_section(state)` | `backend/app/engine/prompt_builder.py` | Per-speaker relationship detail (outgoing edges from main NPC, with word-mapped dimensions + `[Context]` + `[Now]` narrative). Always injected. |

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
| `CharacterIndexBundle.chunks` | `List[dict]` — raw JSONL dicts loaded from disk | Convert to `List[KnowledgeChunk]` at load time; update all retrieval callers |
| `EpistemicStatus` enum vs string `status` field | `KnowledgeChunk.status` is a plain string; `EpistemicStatus` enum is still used for comparison | Eventually make `KnowledgeChunk.status` typed as `EpistemicStatus` or remove the enum |
