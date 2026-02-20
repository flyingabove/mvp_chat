# Epistemic Engine TODO (Simple + Strict)

## Scope Lock
Keep implementation inside the in-memory contract from `EPISTEMIC_ENGINE_DESIGN.md`:
1. Retrieval indexes
2. Objects
3. Graphs

No extra long-lived memory categories.

## Phase 1 — Stabilize Current Live Path
- [x] Keep `BeliefState` as the live epistemic container (claims + observations).
- [x] Ensure seeded epistemic writes include provenance/source fields.
- [x] Enforce reset hygiene: `__cmd_reset__` clears epistemic state and session-local transient scene data.
- [x] Add logging for seeded epistemic mutations (`kind=epistemic_event`).

## Phase 1.5 — Unknown Knowledge Resolution (Implemented)
- [x] Add extractor pass after each reply for unknown chunks (`KnowledgeResolutionExtractor`).
- [x] Resolve per chunk into explicit `knows`/`does_not_know` updates with confidence.
- [x] Upsert resolved chunk knowledge into character belief graph (`EpistemicClaim`).
- [x] Store resolved chunk objects in transient buffer for 8 turns (`meta.source=knowledge_resolution`).

## Phase 2 — Truth vs Belief Enforcement
- [ ] Add a single comparator utility: `truth_overrides_belief()`.
- [ ] Mark contradictions explicitly (contested status), do not auto-resolve without evidence.
- [ ] Prevent retrieval payloads from directly mutating truth objects/graphs.

## Phase 3 — Prompt Contract Simplification
- [ ] Inject only three epistemic blocks into prompts:
  1. validated truth slice
  2. contested/claimed belief slice
  3. retrieval recall slice
- [ ] Add one clear rule: if unknown in truth and belief, model must say unknown.
- [ ] Keep prompt size bounded by fixed caps per slice.

## Phase 4 — Belief Graph Projection (Optional but Preferred)
- [ ] Add projection API from `BeliefState` to graph edges for query/debug.
- [ ] Do not create a second source of truth; projection remains derived from belief objects.

## Phase 5 — Transient Scene Buffer Integration
- [x] Introduce transient scene buffer policy from `TRANSIENT_BUFFER_DESIGN.md`.
- [x] Clear location-scoped transient entries on travel.
- [x] Auto-expire stale scene flavor entries by TTL/turn budget.
- [ ] Promote only gameplay-relevant facts from transient -> objects/graphs.
- [ ] Add optional promotion path from repeated knowledge-resolution claims to canonical truth review queue.

## Phase 6 — Tests (Must-Have)
- [ ] Unit: contradiction marking, truth precedence, namespace isolation, prompt slices.
- [ ] Unit: transient buffer reset on travel and TTL expiration.
- [ ] Integration: movement + claim + contradiction scenario stays deterministic.
- [ ] Integration: no epistemic bleed across `<user>-<story>-<instance>`.

## Hard Rejection Rules
- Reject any proposal that adds a fourth long-lived memory category.
- Reject any design where retrieval can overwrite truth.
- Reject any design that keeps unbounded transcript history in hot runtime memory.
