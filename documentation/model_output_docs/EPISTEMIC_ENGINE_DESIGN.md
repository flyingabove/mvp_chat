# Epistemic Engine Design (Plain-English Spec)

## Purpose
Build a layered epistemic system that keeps one canonical truth, separates beliefs/observations, preserves a full narrative log, and uses retrieval only for style and recall. The goal is to let the extractor update state safely, keep contradictions survivable, and give the renderer clear guidance on what can be asserted vs what must be hedged.

## Data Types and Truth Levels (authorities and risk)
- **Ground truth (validated fact):** observable/validated events, physical state, irreversible flags; authority: highest; hedging: none.
- **Observed evidence:** player/NPC directly sees/hears something (camera, bruise, shouting); authority: high but time/locale bound; hedging: minimal if timestamped.
- **Testimony/claim:** spoken statements by a speaker; authority: medium; hedging: "X claims…"; may conflict.
- **Rumor/inferred:** second-hand or model inference; authority: low; hedging: strong.
- **Narrative style memory:** phrasing/recall for fluency; authority: lowest; never overwrites higher tiers.

Authority ladder: Ground truth > Observed evidence > Testimony > Rumor/Inferred > Narrative style. Each layer below must never overwrite a higher layer; higher layers may explain or reconcile lower ones.
Promotion rule: Observed evidence can be promoted to ground truth only after deterministic validation (e.g., evidence registry + chain-of-custody). Inference from model reasoning stays quarantined at low confidence unless independently validated.

## Epistemic Layers (jobs, storage, allowed data)
1) **Canonical World State (Truth Layer)**
- Holds: ground truth facts, irreversible flags, validated evidence state (exists/destroyed/possessed), authoritative timeline/location relations.
- Storage: structured state on `MurderGameState` plus per-story truth graph.
- Allowed data types: Ground truth only (validated facts/irreversible flags). No rumor/testimony here. Observed evidence may be promoted once validated.
- Updates: only via validated extractor outputs + deterministic rules; never from retrieval or raw testimony.

2) **Epistemic State (Belief/Observation Layer)**
- Holds: per-character belief graphs, claims/testimony with provenance, player/NPC observations, confidence scores, contradictions.
- Storage: belief graph per character + shared observation log on `MurderGameState`.
- Allowed data types: Testimony/claims, observed evidence (time/location bound), inferred/rumor entries with explicit provenance/confidence. Not authoritative truth.
- Validation/promotion: Observed evidence can be promoted to truth only after deterministic checks (e.g., evidence registry + chain-of-custody). Model-only inference remains low-confidence and does not promote without external validation.
- Updates: extractor records exposures; contradictions set contested status; can diverge from truth layer.

3) **Narrative Log (Transcript Layer)**
- Holds: exact turns as spoken/rendered (user + assistant), including stylistic prose.
- Storage: message log in `MurderGameState`.
- Allowed data types: Narrative style memory only; no authority. References higher layers but never asserts them implicitly.
- Purpose: audit trail, forensics, source for retrieval snippets; never a source of truth.

4) **Retrieval Index (Style/Recall Layer)**
- Holds: labeled snippets of what the player experienced (OBSERVED/TESTIMONY/RUMOR/INFERRED/NARRATION), scene summaries, lore.
- Storage: retrieval index (BM25/FAISS) keyed by session/story.
- Allowed data types: Narrative style memory and hedged testimony/rumor labels; must never store or assert ground truth unless marked as validated fact.
- Purpose: improve phrasing/recall; lowest authority; cannot mutate any other layer.

## Why all four layers
- Truth layer guards canonical state and prevents narrative/retrieval drift.
- Belief/observation layer models disagreement, confidence, and provenance without polluting truth.
- Transcript layer preserves what was said for accountability and for building retrieval snippets.
- Retrieval layer offers style/recall without authority, keeping prompts lean and hedged.

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
