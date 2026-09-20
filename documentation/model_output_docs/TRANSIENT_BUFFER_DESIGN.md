# Transient Buffer Design (Scene Memory, Non-Authoritative)

> **What this doc is for:** Design of scene memory / transient buffer (non-authoritative context). Edit this doc when the transient buffer eviction, injection, or scoring logic changes.

## Purpose
Allow vivid scene-level detail without polluting canonical world state.

Examples:
- "You put the coffee cup on the table."
- "Rainwater is pooling by the entrance."
- "A nurse just walked by."

These details improve immersion but should usually fade.

## Key Rule
Transient buffers are **scratch scene memory**, not truth authority.

Transient entries are **never rendered into the system prompt text**. They can influence runtime logic, but prompt assembly intentionally excludes a transient section.

If a detail must matter later for gameplay (evidence, objective, access, irreversible world change), it must be promoted into objects/graphs.

## Lifecycle
1. Create transient details during turn processing.
2. Use them for immediate narration and short-horizon continuity.
3. Reset/expire aggressively.

## Required Reset Behavior
- On session reset, clear all transient entries.
- Turn expiry is handled by countdown pruning, so transient memory naturally fades without being surfaced in prompt text.

## Data Shape (Current Runtime Model)
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

## Expiration Policy
- The default TTL is fixed to **8 turns**.
- This hardcoded value is centralized at `backend/app/config/settings.py` as `TRANSIENT_KNOWLEDGE_TURNS = 8`.
- `TransientBuffer.prune_expired()` decrements `turns_remaining` and removes entries once they hit `<= 0`.
- SceneKnowledge uses FIFO retention (max 8 entries) rather than per-object turn counters.
- Upsert semantics refresh an existing key by moving it to queue tail.

## Promotion Rules
If a detail becomes durable gameplay truth, write it explicitly to canonical structures (facts/graphs) rather than relying on transient retention.

## Safety Rules
- No direct transient section in prompt output.
- No direct truth overwrite from transient entries.
- No cross-session sharing.

## Implementation Notes
- Runtime state stores `List[TransientKnowledge]` on `GameState.transient_entries`.
- Runtime state also stores `List[SceneKnowledge]` on `GameState.scene_knowledge_entries`.
- New text entries are appended via `GameState.add_transient_entry(text, ...)` and use caller TTL or `TRANSIENT_KNOWLEDGE_TURNS`.
- Scene knowledge entries are upserted via `GameState.upsert_scene_knowledge(...)` and bounded to 8 FIFO items.
- Prompt builder excludes transient entries by design.

## Scene Presence Contract (Current)
- Per turn, engine tracks both:
	- `speakers` (who is currently talking / in turn-active cast)
	- `people_present` (who is physically present at player location)
- These scene fields are produced by the single-call turn extractor contract (one extractor LLM call per turn).
- `people_present` is derived by combining current world location query + character location index.
- If location did not change from previous scene knowledge item, previous turn speakers are carried into the current active character list.
- Phone-call/off-scene edge cases are intentionally deferred.
