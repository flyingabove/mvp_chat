# Transient Buffer Design (Scene Memory, Non-Authoritative)

## Purpose
Allow vivid scene-level detail without polluting canonical world state.

Examples:
- "You put the coffee cup on the table."
- "Rainwater is pooling by the entrance."
- "A nurse just walked by."

These details improve immersion but should usually fade.

## Key Rule
Transient buffers are **scratch scene memory**, not truth authority.

If a detail must matter later for gameplay (evidence, objective, access, irreversible world change), it must be promoted into objects/graphs.

## Lifecycle
1. Create transient details during turn processing.
2. Use them for immediate narration and short-horizon continuity.
3. Reset/expire aggressively.

## Required Reset Behavior
- On location change, clear location-scoped transient entries.
- On session reset, clear all transient entries.

This matches expected behavior: Hospital scene details do not automatically follow the player to Work.

## Data Shape (Minimal)
```text
TransientEntry:
- id
- namespace: <user>-<story>-<instance>
- scope: scene | location | conversation
- location_id (optional)
- text
- created_minute
- expires_after_turns or expires_after_minutes
- promotable: bool
- promoted: bool
```

## Expiration Policy
Use one simple policy set:
- default turn TTL (short)
- optional minute TTL
- hard cap on max entries per namespace

Evict oldest first when cap is exceeded.

## Promotion Rules
Promote transient detail to canonical objects/graphs only when at least one is true:
1. The detail changes objective/evidence state.
2. The detail creates durable access constraints.
3. The detail is repeatedly confirmed and gameplay-relevant.

Promotion should be explicit and logged.

## Safety Rules
- No retrieval index writes from transient buffer by default.
- No direct truth overwrite from transient buffer.
- No cross-namespace sharing.

## Implementation Notes
- Keep transient buffer attached to runtime session state (namespace-scoped).
- Keep APIs tiny: add, get_active, clear_on_travel, clear_all, promote.
- Instrument with logs so debugging is easy.
