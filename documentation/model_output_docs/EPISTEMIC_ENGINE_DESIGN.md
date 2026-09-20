# Epistemic Engine Design (North-Star Aligned, Minimal)

> **What this doc is for:** Design of the epistemic/knowledge system (canonical facts, beliefs, confidence). Edit this doc when knowledge retrieval, belief injection, or epistemic rules change.

## Purpose
Keep the engine simple, scalable across stories, and faithful to one rule: **world truth lives in engine state, not in model prose**.

## Non-Negotiables
1. One authoritative world state.
2. Time and movement mutate state deterministically.
3. Retrieval is recall/style only, never authority.
4. Player agency is preserved (no model-authored player actions).
5. Data is isolated by namespace `<user>-<story>-<instance>`.

## In-Memory Contract (Only 3 Categories)
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

## Belief in This Design (What It Actually Means)
"Belief" is character-local epistemic state, not a fourth storage category.

- **Today (implemented):** `BeliefState` with claims + observations per character.
- **Target shape:** graph projection where:
  - nodes = entities/facts
  - edges = "character believes claim" with confidence + provenance

Belief may disagree with truth. Truth still wins.

## Authority Order
`validated truth > observed evidence > testimony/claim > rumor/inferred > retrieval prose`

Lower layers can inform dialogue, but cannot overwrite higher layers.

## Per-Turn Runtime (Simple)
1. Read input and detect movement/structured intents.
2. Mutate objects/graphs through validated rules.
3. Update epistemic beliefs (claims/observations with provenance).
4. Build prompt from current truth + allowed belief slice + retrieved recall.
5. Render reply.
6. Persist durable records asynchronously/synchronously per environment.

## Unknown Knowledge Resolution (Implemented)
When a chunk is not explicitly marked `known_by` and not explicitly marked `not_known_by` for the active speaker:

1. Prompt instructions require the LLM to make a best reasonable determination (with hedging if uncertain).
2. On the next turn's pre-render phase, a **single-call turn extractor** evaluates prior-turn dialogue + candidate chunks.
3. Extractor outputs deterministic updates per chunk in one JSON payload: `chunk_id`, `knows`, `confidence`, `reason`.
4. Engine writes these to the speaker's belief graph as `KnowledgeChunk` entries with `kind='claim'` (`source=knowledge_resolution_extractor`, `provenance=inferred_dialogue`).
5. Engine writes a mirrored knowledge object into transient buffer with TTL = 8 turns (`meta.source=knowledge_resolution`).

This means ambiguous retrieval memory is converted into explicit epistemic state over time using dialogue evidence, without running separate extractor calls in a single turn.

## Where Updates Are Stored
- Primary authority for these updates is character-local belief graph (`BeliefState`).
- Short-lived transport/debug copy is stored in transient buffer for 8 turns.
- No direct on-the-fly mutation of packaged FAISS/BM25 artifacts occurs at runtime.

## What Is Live vs Planned
- **Live now:** object state, place graph travel, retrieval namespaces, per-character belief logs (`BeliefState`), single-call extractor resolution, and transient scene buffering (including 8-turn knowledge objects).
- **Planned:** stronger invariant validator + full belief graph projection.

## Design Guardrails
- Do not let retrieval chunks mutate canonical truth.
- Do not keep unbounded transcript history in hot memory.
- Do not create a separate in-memory subsystem for "belief" beyond objects/graphs.
- Do not store scene flavor as permanent world truth unless gameplay requires it.

## Related
- See transient scene memory policy in `TRANSIENT_BUFFER_DESIGN.md`.
