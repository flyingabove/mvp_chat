# Epistemic Engine Design (Plain-English Spec)

## Purpose
Build a layered epistemic system that keeps one canonical truth, separates beliefs/observations, preserves a full narrative log, and uses retrieval only for style and recall. The goal is to let the extractor update state safely, keep contradictions survivable, and give the renderer clear guidance on what can be asserted vs what must be hedged.

## The Four Layers (Jobs, Storage, Updates)
1) **Canonical World State (Truth)**
- What it holds: hard facts about the world — locations, time, who has what, who did what; evidence objects and their properties (exists, destroyed, overwritten); irreversible flags (e.g., "mastermind confessed", "door locked").
- Storage: structured state on `MurderGameState` plus a story knowledge graph (truth graph) loaded per story.
- Updates: only through validated extractor outputs and deterministic game rules; never from retrieval.

2) **Epistemic State (Who knows/believes what)**
- What it holds: per-character beliefs (can be wrong), player-observed information, rumor/fact confidence, provenance of claims.
- Storage: per-character belief graph + player observation log stored on `MurderGameState`.
- Updates: extractor notes exposures (saw CCTV, heard claim, inferred); NPCs can lie so belief graphs may diverge from truth graph.

3) **Narrative Log (What was said)**
- What it holds: full transcript of user and assistant turns, exactly as spoken/rendered.
- Storage: existing message log in `MurderGameState`.
- Purpose: audit trail, forensics/debug, material for retrieval.

4) **Retrieval Index (Search memory)**
- What it holds: snippets of past dialogue, lore paragraphs, scene summaries, "what the player experienced" phrased for style.
- Scope: only player-observable experience, not hidden truth.
- Purpose: help the model talk well; lowest authority. Labeled snippets (OBSERVED / TESTIMONY / RUMOR / INFERRED / NARRATION) to prevent hallucinated authority.

## Core Data Structures (Plain English)
- **TruthGraph** (per story): nodes for characters, locations, items/evidence, events, flags; edges for relations (e.g., saw_at, owns, occurred_at, ordered); attributes for time bounds, confidence (truth defaults to 1.0), provenance (usually "validated").
- **BeliefGraph** (per character): mirrors truth graph shape but can diverge; stores that character's believed relations, confidence, and provenance (testimony, rumor, inferred).
- **ObservationLog** (player-facing): chronological list of what the player/NPCs directly observed (e.g., "saw CCTV blinking", "heard Bob claim an alibi"); includes minute, location, provenance.
- **EpistemicLog**: append-only record of claims/observations with normalized subject/object, confidence, provenance, and pointers into truth/belief graphs for reconciliation.
- **EvidenceRegistry**: catalog of evidence objects (ids, state: exists/destroyed/hidden, possession, chain-of-custody notes).
- **QuestState**: trigger status per quest (triggered/progress/completed), with references to conditions in the truth/belief/observation layers.
- **SessionState (MurderGameState additions)**: references to truth graph, per-character belief graphs, observation log, epistemic log, evidence registry, quest state, plus existing time/location/user/character fields.

## Extractor Outputs (Single Call, Structured)
- Output object: `ExtractorResult`
  - `moves`: list of `{destination_id, via: [ids], raw_text}`
  - `claims`: list of `{speaker: player|npc, content, subject, object, time_ref, location_ref, confidence, provenance: observed|testimony|inferred|rumor}`
  - `quests`: list of `{id, status: triggered|progress|completed}`
  - `rel_emotion`: `{rel_delta: -1|0|1, emotion}`
  - `evidence`: list of `{id, action: add|remove, note, confidence, provenance}`
  - `world_mutations` (optional): list of `{type: add|update|delete, target: location|item|flag, id, fields}` for non-movement state changes
- Validation expectations:
  - Location ids must exist in the world graph; unknowns must be flagged (e.g., `unknown_npc_X`).
  - World mutations must pass graph/state validation and deterministic rules.
  - Provenance must be present so the renderer can hedge appropriately.

## Update Flow (Per Turn)
1) **Advance time**: apply time cost; sync world clock if graph active.
2) **Extractor call** (structured only): returns `ExtractorResult`.
3) **Validate**: check ids, world rules, quest conditions; drop/flag invalid items.
4) **Apply to layers**:
   - Truth graph/state: apply validated world_mutations, movements, evidence state changes, irreversible flags.
   - Belief graphs: add claims/beliefs per speaker with provenance and confidence.
   - Observation log: add observations and any player-visible events.
   - Epistemic log: append normalized claims/observations with time/location.
   - Quest state: update from quest results.
   - Relationship/emotion: apply rel_delta/emotion updates.
5) **Prompt build**: construct narrative prompt with a concise "What the world knows" block drawn from truth (player-visible slice) + contested/claimed items with provenance labels.
6) **Narrative call**: renderer produces prose; may hedge based on provenance; must not invent state.
7) **Log**: append to narrative log; do not feed back into truth without extractor validation.

## Class Descriptions (Plain English)
- `TruthGraph`: authoritative map of world entities and facts; APIs to get/set nodes/edges with validation; backs canonical world state.
- `BeliefGraph`: per-character view; APIs to record a belief/claim with provenance and confidence; can diverge from `TruthGraph`.
- `ObservationLog`: ordered records of what was seen/heard; each entry has minute, location, description, provenance.
- `EpistemicLog`: normalized stream of claims/observations for auditing and prompt inclusion; links to truth/belief entries when reconciled.
- `EvidenceRegistry`: tracks evidence objects, state (exists/destroyed/hidden), possession, and notes; used by both truth and belief layers for consistency checks.
- `QuestState`: holds quest trigger/completion statuses and links to conditions; updates from extractor `quests` outputs.
- `ExtractorResult`: structured container for extractor outputs (as above); produced by `EpistemicExtractor`.
- `EpistemicExtractor`: orchestrates the single pre-narrative LLM call; builds prompts with world graph ids, knowledge snippets, and recent context; enforces JSON schema.
- `StateUpdater`: deterministic applier that consumes `ExtractorResult` and updates truth/belief/observation/evidence/quest state safely.
- `PromptBuilder` (extended): pulls from truth (player-visible slice), belief/claims with provenance, and observation log to produce a "What the world knows" section; tags retrieved snippets by type.

## Precedence & Rendering Rules
- Precedence: Truth > Belief/Observation > Narrative Log > Retrieval.
- Retrieval must be labeled; it never overwrites truth. If it conflicts, treat it as testimony/rumor in the prompt.
- Renderer assertion rule: assert hard facts only if they are in player-visible truth or direct observations; otherwise hedge ("Bob claimed…", "You heard…").

## Story JSON Extensions (for triggers)
- Add optional sections for `quests` (id, conditions, rewards), `triggers` (natural-language or structured conditions tied to world/epistemic facts), and `knowledge_graph` seeds (nodes/edges/flags).
- IU mini-game path: first encode triggers and graph for the IU integration test story; once stable, port patterns into main stories.

## Edge Handling (kept concise)
- Unknown NPCs: create `unknown_npc_X` with low confidence; do not merge into canonical characters without confirmation.
- Contradictions: mark conflicts in belief/epistemic logs; do not auto-resolve unless deterministic evidence exists.
- Missing locations: drop move mutations but keep the claim as intent with a note.
- Translation/debug/map modes: extractor/narrative must preserve [[STATE]] and remain language-agnostic.

## Success Criteria
- Canonical truth never overwritten by retrieval or narrative.
- Extractor outputs are validated, typed, and applied deterministically.
- Renderer sees a clear, labeled summary of facts vs claims vs rumors and hedges appropriately.
- IU mini-game triggers and epistemic flows pass the integration test (5-turn scenario) with correct logs and conflicts recorded.
