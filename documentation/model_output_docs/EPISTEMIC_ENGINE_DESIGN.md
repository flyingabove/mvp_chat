# Epistemic Engine Design (Current Design + Lessons Learned)

## Purpose
Keep one authoritative truth, separate beliefs and observations, preserve a full narrative log, and use retrieval strictly for style/recall. Support many users/sessions by namespacing every entity and index entry so data cannot bleed across `<user>-<story>-<instance>-<entity>`.

## Authority Levels (what they mean)
- **Ground truth (validated fact):** observed/validated physical state and irreversible flags; no hedging.
- **Observed evidence:** directly seen/heard; high authority but time/locale bound; light hedging with timestamp/location.
- **Testimony/claim:** spoken statements; medium authority; hedge as "X claims…".
- **Rumor/inferred:** second-hand or model inference; low authority; strong hedging.
- **Narrative style memory:** phrasing/recall only; lowest authority; never overwrites higher tiers.

Authority ordering: Ground truth > Observed evidence > Testimony > Rumor/Inferred > Narrative style. Lower tiers cannot overwrite higher tiers. Promotion: Observed evidence can become truth only after deterministic validation (e.g., evidence registry + chain-of-custody).

## Storage and Technology Map
- **Canonical Truth (structured)**
  - Stored in memory on `MurderGameState` plus per-story truth graph objects; persisted via backing store (DB or file) keyed by `<user>-<story>-<instance>`.
  - Not indexed in BM25/FAISS; read via structured APIs.
- **Beliefs/Observations (structured)**
  - Belief graphs per character + observation log on `MurderGameState`.
  - Structured storage only; no BM25/FAISS indexing of raw graphs. Narrative views of claims may be indexed (see retrieval layer).
- **Narrative Log (text)**
  - Turn-by-turn transcript stored on `MurderGameState`.
  - Source for retrieval snippets; also kept in structured history for audit.
- **Retrieval (BM25 + FAISS)**
  - Text chunks only (narrative/claims/observations) with provenance labels. Each chunk carries metadata `{user, story, instance, entity_ids, timestamp, type}`.
  - BM25: per-namespace index (e.g., index name/prefix = `<user>-<story>-<instance>`). Query filters on that namespace.
  - FAISS: vectors stored with external ids prefixed by `<user>-<story>-<instance>` plus a metadata sidecar to filter before similarity search.
- **Evidence Registry (structured)**
  - Structured catalog keyed by deterministic IDs; not put in retrieval.
- **Quest/Trigger State (structured)**
  - Structured status flags and conditions; not put in retrieval.

## Identifier and Namespacing Rules
- Deterministic IDs use `<user>-<story>-<instance>-<entity>`; defaults: `default_user`, story slug, instance `1`.
- Entities include characters, locations, items, flags, evidence objects.
- Retrieval docs carry a namespace key `<user>-<story>-<instance>` to isolate users and sessions and to speed filtering. BM25 indexes can be sharded or keyed by this string; FAISS uses the same prefix in vector ids plus metadata filters.

## Layers (jobs, data, storage)
1) **Canonical World State (Truth Layer)**
- Holds: validated facts, irreversible flags, validated evidence state, authoritative timeline/location relations.
- Storage: `MurderGameState` fields + truth graph objects; persisted in structured store keyed by namespace.
- Updates: only via validated extractor outputs and deterministic rules; retrieval never writes here.

2) **Epistemic State (Belief/Observation Layer)**
- Holds: per-character belief graphs, claims with provenance, observation log, confidence/contradiction status.
- Storage: structured on `MurderGameState`; per-character structures keyed by deterministic ids.
- Updates: extractor records exposures; contradictions set contested status; may diverge from truth.

3) **Narrative Log (Transcript Layer)**
- Holds: exact turns (user + assistant) with prose.
- Storage: structured list on `MurderGameState`.
- Purpose: audit trail, source of retrieval snippets; no authority.

4) **Retrieval Index (Style/Recall Layer)**
- Holds: labeled text snippets (OBSERVED/TESTIMONY/RUMOR/INFERRED/NARRATION), short scene summaries, safe lore.
- Storage: BM25 corpus + FAISS vectors, both partitioned by namespace `<user>-<story>-<instance>`.
- Allowed: hedged narrative text only; no raw truth state or registries. Ground truth may be echoed only if explicitly marked validated and still hedged in retrieval prompts.

## Core Objects (plain English to code)
- `MurderGameState` ([backend/app/engine/state.py](../../backend/app/engine/state.py)): session container; holds truth graph reference, beliefs, observation log, epistemic log, quest/evidence state, time/location, user/story/instance ids, deterministic UUIDs for characters/locations.
- `TruthGraph`: authoritative nodes/edges with validation (locations/items/events/flags/relations); confidence defaults to 1.0; provenance "validated".
- `BeliefGraph`: per-character view mirroring truth shape; holds believed relations + provenance/confidence; can diverge.
- `ObservationLog`: chronological observations with minute/location/provenance.
- `EpistemicLog`: normalized claims/observations with pointers into truth/belief graphs for reconciliation.
- `EvidenceRegistry`: evidence catalog with existence/possession/chain-of-custody.
- `QuestState`: quest trigger/progress/completion flags tied to truth/belief/observation conditions.
- `Knowledge/Story config`: story JSON seeds world graph, quests, triggers, and deterministic ids.

## Extractor Output (structured input contract)
- `ExtractorResult`
  - `moves`: `{destination_id, via: [ids], raw_text}`
  - `claims`: `{speaker, content, subject, object, time_ref, location_ref, confidence, provenance: observed|testimony|inferred|rumor}`
  - `quests`: `{id, status: triggered|progress|completed}`
  - `rel_emotion`: `{rel_delta: -1|0|1, emotion}`
  - `evidence`: `{id, action: add|remove, note, confidence, provenance}`
  - `world_mutations` (optional): `{type: add|update|delete, target: location|item|flag, id, fields}`
- Validation: ids must exist or be flagged (e.g., `unknown_npc_X`); mutations must pass graph rules; provenance required for hedging.

## Per-Turn Flow (apply and render)
1) Run location extraction (LLM classifier + heuristic fallback) to canonicalize movement intent.
2) Advance time (state minute) and sync world clock — using the canonicalized message so movement regex matches.
3) Call extractor (structured JSON only) to get `ExtractorResult`.
4) Validate ids/rules/quests; drop or flag invalid entries.
5) Apply to layers:
- Truth: apply validated world_mutations, movements, evidence state, irreversible flags.
- Beliefs: add claims/beliefs per speaker with provenance/confidence.
- Observation log: append observations and player-visible events.
- Epistemic log: append normalized claims/observations with time/location.
- Quest state: update from quest results.
- Relationship/emotion: apply rel_delta/emotion updates.
6) Build prompt: concise "What the world knows" from truth (player-visible slice) + contested/claimed items with provenance labels.
7) Narrative call: renderer produces prose; hedges based on provenance; does not invent state.
8) Log: append to narrative log; produce retrieval chunks (labeled) for BM25/FAISS with namespace metadata.

## Speaker Resolution (location-aware)
The debug panel and prompt builder need to know who is speaking at the current location. Resolution order:
1. **`location_speakers` map** (story JSON `world.location_speakers`): explicit mapping from `location_id` to speaker name(s). Preferred source.
2. **Fallback: `state.characters`**: iterate all characters, but **exclude** any character tagged `"victim"` (dead characters never speak).
3. The player is never listed as a speaker — only NPCs.

This prevents dead characters (e.g., Jennie in the murder mystery) from appearing as active speakers in debug output.

## Location Movement (ordering constraint)
Location extraction (LLM + heuristic) MUST run before `advance_time()`. The user's natural language (e.g., "one sec, let me get water then I go to room B") does not match the strict movement regex in `advance_time`. The extraction pipeline canonicalizes this to `"go to interview_room_bob"` which the regex can parse. If `advance_time` runs first with the raw message, the movement is missed and the location never updates.

## Retrieval Rules (BM25/FAISS)
- Index only player-visible, hedged text (observations, claims, narration, summaries). Each chunk carries `{namespace, type, time, location_id, character_ids, confidence, provenance}`.
- Namespace key = `<user>-<story>-<instance>`; use it to shard BM25 indexes or as a filter prefix before FAISS similarity search.
- Do not index raw truth graph or registries; keep them structured-only.
- Retrieval is read-only; it never mutates truth/belief/observation state.

## Isolation and Scale
- Deterministic UUIDs ensure stable joins across layers: `<user>-<story>-<instance>-<entity>`.
- Default namespace is `default_user-<story>-1` for single-user scenarios; multi-user uses real user id.
- BM25: separate corpus per namespace (fast filtering) or a shared corpus with namespace field filter.
- FAISS: store vector ids with namespace prefix and maintain a sidecar mapping for filtering before distance computation.

## Edge Handling
- Unknown NPCs: create `unknown_npc_X` with low confidence; keep separate from validated characters.
- Contradictions: mark contested in beliefs/epistemic log; do not auto-resolve without evidence.
- Missing locations: drop move mutations but keep intent noted.
- Translation/debug/map modes: preserve [[STATE]] tags and remain language-agnostic.

## Known Gaps (identified during v2 redesign review)
1. **Identity anchors are not modeled.** Canon facts like "You are IU" are embedded as prompt text, not as structural invariants. This causes identity drift (IU referring to herself in third person). The v2 redesign addresses this with ANCHOR-tier KnowledgeChunks injected every turn.
2. **Prompt rules are global and mode-conflicting.** Rules like "cinematic narration" and "no player speech" apply to all stories regardless of mode (ghost story vs interrogation). Truth mode must explicitly override output style rules, not just add to them.
3. **Retrieval returns text, not canonical objects.** Retrieved chunks lack canon tier, access policy, or invariant metadata. This means retrieval can surface text that conflicts with canon because nothing structurally prevents it.
4. **Single-dimension relationship score.** The current `relationship` integer (-5..+5) collapses trust, fear, affection, and suspicion into one number. The v2 `RelationshipGraph` with multi-dimensional `RelationshipState` is the planned fix, but the prompt builder must be updated to consume all dimensions.
5. **No post-generation validation.** The engine does not check model output for canon violations before sending it to the player. The v2 `invariant_validator` is the planned fix.

## Success Criteria
- Canonical truth never overwritten by retrieval or narrative.
- Extractor outputs stay structured, validated, and deterministic.
- Renderer receives labeled facts vs claims vs rumors and hedges correctly.
- Retrieval stays namespaced, read-only, and free of authority bleed across users/sessions.
- Identity anchors are never contradicted in model output.
- Dead/victim characters never appear as active speakers.
- Location updates are applied before prompt construction and debug rendering.
