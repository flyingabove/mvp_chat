# BL-38 — Typed social events and provenance-preserving epistemic transactions

- **Type:** follow-up
- **Found:** 2026-09-26, user-requested engine architecture review
- **Severity:** high; gossip and consequential dialogue need enforceable authority boundaries.

## Problem
`world_model/gossip.py::share_memory` copies text with confidence decay and deduplicates by event ID, without proposition-level assertion/transmission provenance. `events.py::Event` has free-text truth. The engine has several knowledge representations and previous-turn extraction, which need a shared contract before richer social actions depend on them. These are code-review findings, not newly reproduced hosted failures.

## Fix direction
Implement phases 1–2 of [SOCIAL_ENGINE_V2_DESIGN.md](../model_output_docs/SOCIAL_ENGINE_V2_DESIGN.md): typed proposals/events, idempotent commit with final response, observation/assertion/transmission separation, belief support chains and perspective-safe projection. Preserve one canonical writer and legacy read adapters. Test false testimony, circular rumor corroboration, absent witnesses, protected confessionals, transaction retry and interrupted save/resume. BL-35 owns agreements; BL-34 owns rival initiative; BL-36 owns IU evidence behavior.

## Why deferred / cautions
This turn produces an engineering design, not a runtime migration. Requires schema versioning, compatible saved sessions and model-level leakage evaluation in addition to deterministic tests. Fictional secret disclosure must never weaken protection of confessionals or system-only content.

**Further implementation (2026-09-26):** Versioned snapshots, idempotent world event IDs with causal links, utterance observations, assertion/transmission provenance and root-source tracking now form a first adapter. The session row stores a completed state and retry reply together. Remaining: authoritative typed reducer for all writers, structured proposition/contradiction and reliability updates, a single retrieval/epistemic writer, before-display scene validation, cross-worker revision checking, full event replay, bounded hot state and model-level leakage gates. The JSONL side log remains separate from the session transaction.

## Touches
`backend/app/engine/world_model/`, `backend/app/engine/extractors/turn_extractor.py`, `backend/app/api/prompt_engine.py`, epistemic graph/retrieval and existing persistence transaction boundary.
