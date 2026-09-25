# BL-27 — Memory/knowledge mechanisms: small problems (one list)

- **Type:** tech-debt (with a few latent bugs)
- **Found:** 2026-09-24, memory/retrieval audit (same audit as BL-26)
- **Severity:** low to medium: each item is small, but together they mean several stores are written, then never read or never bounded

## Problem
The audit mapped every place the game stores "what characters know". The issues are listed together here because each one
is small. Tick an item off (or delete its row) when it is fixed; delete this file when the table is empty.
The namespace filter row is its own item, **BL-26** (high). Fix that separately.

| # | Mechanism | Where | Problem |
|---|-----------|-------|---------|
| 1 | Static index (`chunks.jsonl` + FAISS/BM25) | `knowledge/runtime/retrieve.py` `retrieve_knowledge` → `RETRIEVED_MEMORY` tier (`engine/prompt_builder.py`) | Namespace filter drops every hit (**BL-26**). Also: chunks carry no visibility (`known_by`), and there is one bundle per story (main character only). |
| 2 | Canonical facts | `state.canonical_facts`, seeded in `api/prompt_engine.py` (~L178), rendered in `prompt_builder.py` (~L441-L492) | The focal NPC's prompt includes the "others" group ("Known by others — the focal character does not know this"), which leaks facts it shouldn't know. Visibility matching uses exact text. |
| 3 | `canonical_truth` | `state.canonical_truth`, backfilled in `prompt_engine.py` ~L311 | `List[str]` duplicate of the canonical facts, used only in truth mode. Derive it from `canonical_facts` instead. |
| 4 | `BeliefState` | `state.beliefs[cid]`, rendered at `prompt_builder.py` ~L405 (`claims_list[:10]`) | Only the main character's beliefs are written and read. The list is unbounded, and the `[:10]` slice cuts off claims from knowledge resolution. |
| 5 | `epistemic_log` | `engine/state.py` L314, appended at ~L438 | Duplicates the beliefs and claims. Only the playback scenario (`integration_playback/scenarios/scenario_epistemic_iu.py`) reads it. It isn't persisted and is re-seeded. |
| 6 | `observation_log` | `engine/state.py` L315, saved/restored in `prompt_engine.py` ~L1555/L1814 | Dead: only `belief_seeds` write it, nothing reads it into the prompt, yet it is persisted. |
| 7 | Transient text | `state.transient_entries` (`prompt_engine.py` ~L650, ~L718) | The entry fields `id`, `scope` and `meta` are ignored. The kr/`story_extra` entries are never used. Only the debug panel reads them. |
| 8 | Markers | also in `transient_entries` | Room presence is stored as string entries in `transient_entries`, and `SceneContext` and the scene brief parse it back out. It needs a typed field. |
| 9 | `SceneKnowledge` | `state.scene_knowledge_entries` (`engine/state.py` L344, L498) | 8-item queue written 3× per turn, so the entries churn: each write overwrites the last. Read only for carryover and fallback. |
| 10 | `SessionChunkStore` | `knowledge/runtime/session_chunk_store.py` | Unbounded. No speaker or visibility tag, so player claims become facts. Persistence is lossy, and the DB copy is never read back. |
| 11 | Jev selection | `knowledge/runtime/dynamic_context.py` | `_eligible` is effectively a no-op because chunks have no `not_known_by`. On an exception, up to 200 candidates (`JEV_CONTEXT_CANDIDATE_LIMIT`) can reach the prompt unselected. |
| 12 | Conversation log | `sess.log`, `prompt_engine.py` ~L3333 (`log[-MEMORY_TURNS:]`) | Only the last 6 messages are sent, and nothing summarizes older turns, so everything earlier is lost. |
| 13 | Graph edges | `engine/character_graph.py` | `edge.narrative` is never written during play (only restore, ~L652). `disposition` is persisted but never read. Only the main character's outgoing edges reach the prompt. |
| 14 | Behavior log | `state.recent_behavior_log` (`prompt_engine.py` ~L1361-L1392) | Enough tags shift goals and dispositions, but part of that output is never read (see row 13, `disposition`). |
| 15 | `tells` | `Character.tells` (`prompt_engine.py` ~L374, L1748, L2580) | Dead: loaded from the story, never put into the prompt. Either render it or remove the field. |

## Fix direction
- Remove the dead stores (rows 5, 6, 15 or render tells, and 3) with tests that pin save/restore compatibility.
- Put a cap on the unbounded stores (4, 10) and add speaker and visibility tags to session chunks (10).
- Fix the visibility leaks (2 "others" group, 11 exception path). Each fix gets a unit test asserting the fact or chunk is absent from the prompt.
- Typed presence field instead of marker strings (8). Write or remove `narrative`/`disposition` (13, 14).
- Log summarization (12) is design work. Route it through the character-object redesign.

## Why deferred / cautions
Rows 2, 4, 10, 11, 12 and 15 change what the model sees. Each needs the hosted arena gate, and none should ship bundled with BL-26.
Rows 3, 5, 6, 7 and 8 are refactors that don't change the prompt, but they do touch the save format, so keep restore of old saves working.
The long-term home for per-character memory is the character-object redesign
(`LIVING_WORLD_INVESTIGATION_AND_CONVERSATION_DESIGN.md` §12). Features must stay generic across games, with no house or event log.

## Touches
`backend/app/engine/state.py`, `backend/app/engine/prompt_builder.py`, `backend/app/engine/character_graph.py`,
`backend/app/api/prompt_engine.py`, `backend/app/knowledge/runtime/{retrieve,dynamic_context,session_chunk_store}.py`,
`tests/backend/app/...` (per-row tests).
