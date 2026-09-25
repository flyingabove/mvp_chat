# BL-27 — Storyteller timeout crashes the turn with HTTP 500

- **Type:** bug (production code path)
- **Found:** 2026-09-24, promotion precheck `promote_91385aa_precheck` (`empty_reply (major)` finding)
- **Severity:** medium. The player gets a raw 500 and an empty reply instead of a retryable message.

## Problem
`_chat_handler_impl` (`backend/app/api/prompt_engine.py`, the storyteller call `client.post(f"{STORY_MASTER_BASE_URL}/chat/completions", ...)`
inside `httpx.AsyncClient(timeout=30.0)`) does not catch `httpx.ReadTimeout` or other `httpx.TransportError`s. They propagate out of
`chat_handler` as an ASGI 500. Only non-2xx *responses* are handled (they return `_PUBLIC_UPSTREAM_ERROR`).
Seen in `data/eval_arena/_local/server_beta.log` (`httpcore.ReadTimeout` → `POST /api/chat 500`) when a concurrent
Ollama run slowed the local 8B model past 30 s. The same path exists on prod. The new repeat-regeneration call (`storyteller_repeat_regenerated`) has the same exposure.

## Fix direction
Wrap both storyteller calls: on `httpx.TransportError`, log `chat_upstream_error` with `req_id` and return the same
`{"error": _PUBLIC_UPSTREAM_ERROR}` shape (no state mutation, so the retry is idempotent). For the regeneration call, keep the
first draft instead of failing the turn. Regression test: a fake `AsyncClient.post` raising `httpx.ReadTimeout` gives HTTP
200 with an `error` field, and the session log is unchanged.

## Why deferred / cautions
Found during a promotion. The fix is small, but it must not be bundled into the release being evaluated.
Arena note: never run two Ollama-backed arena runs at once. Contention causes timeouts that look like regressions.

## Touches
`backend/app/api/prompt_engine.py`, `tests/backend/app/api/test_prompt_engine.py`.
