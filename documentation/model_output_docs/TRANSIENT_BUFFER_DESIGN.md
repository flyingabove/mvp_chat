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

Transient entries are **never rendered into the system prompt text**. They can influence runtime logic, but prompt assembly intentionally excludes a transient section.

If a detail must matter later for gameplay (evidence, objective, access, irreversible world change), it must be promoted into objects/graphs.

## Lifecycle
1. Create transient details during turn processing.
2. Use them for immediate narration and short-horizon continuity.
3. Reset/expire aggressively.

## Required Reset Behavior
- On session reset, clear all transient entries.
- Turn expiry is handled by countdown pruning, so transient memory naturally fades without being surfaced in prompt text.

## Data Shape (Current Minimal Runtime Model)
```text
TransientKnowledge:
- text
- turns_remaining
```

## Expiration Policy
- The default TTL is fixed to **8 turns**.
- This hardcoded value is centralized at `backend/app/config/settings.py` as `TRANSIENT_KNOWLEDGE_TURNS = 8`.
- `TransientBuffer.prune_expired()` decrements `turns_remaining` and removes entries once they hit `<= 0`.

## Promotion Rules
If a detail becomes durable gameplay truth, write it explicitly to canonical structures (facts/graphs) rather than relying on transient retention.

## Safety Rules
- No direct transient section in prompt output.
- No direct truth overwrite from transient entries.
- No cross-session sharing.

## Implementation Notes
- Runtime state stores `List[TransientKnowledge]` on `GameState.transient_entries`.
- New entries are appended via `GameState.add_transient_entry(text, ...)` and always use `TRANSIENT_KNOWLEDGE_TURNS`.
- Prompt builder excludes transient entries by design.
