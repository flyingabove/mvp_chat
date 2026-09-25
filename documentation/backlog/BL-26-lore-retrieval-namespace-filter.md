# BL-26 — Authored lore never reaches the prompt (namespace filter)

- **Type:** bug (production)
- **Found:** 2026-09-24, memory/retrieval audit
- **Severity:** high: authored character lore is silently unused in every story

## Problem
Every turn, `_chat_handler_impl` (`backend/app/api/prompt_engine.py`, retrieval block around `retrieve_knowledge(...)`) passes
`namespace=build_namespace_key(user_id, story_id, instance)`, e.g. `default_user-iu_murder_mystery-1`.
`retrieve_knowledge` (`backend/app/knowledge/runtime/retrieve.py`, `_filter_by_namespace`) drops every chunk whose
`namespace`/`ns` field differs. The authored bundles `backend/app/knowledge/characters/{1_iu,7_mizuki}/chunks.jsonl`
carry no namespace field (0 of 57 and 0 of 3 lines), so BM25 and FAISS both return nothing. Only session chunks come back.
The Jev path (`retrieve_context_candidates`, `knowledge/runtime/dynamic_context.py`) goes through the same filter.

Reproduced 2026-09-24 against the IU index with the query "who killed IU and where did it happen?":
- live path (with namespace): **0** static chunks
- `namespace=""`: **8** relevant chunks

The namespace argument dates to at least `90e15db` (2026-02-22), so this has probably been broken for months.

## Fix direction
Apply the namespace filter only to session/dynamic chunks, which are the ones tagged per playthrough. Authored static chunks
must always be eligible. Add a regression test: static recall with a non-empty namespace returns authored chunks.

## Why deferred / cautions
The fix changes what the model is told (IU gains 57 authored facts), so what IU says will change. Ship it as its own change
with the hosted arena gate. Don't bundle it with another release. The long-term home is per-character memory in the
character-object redesign (see `LIVING_WORLD_INVESTIGATION_AND_CONVERSATION_DESIGN.md` §12). This fix shouldn't wait
for that work.

## Touches
`backend/app/knowledge/runtime/retrieve.py`, `backend/app/knowledge/runtime/dynamic_context.py`,
`backend/app/api/prompt_engine.py`, `tests/backend/app/knowledge/` (new test).
