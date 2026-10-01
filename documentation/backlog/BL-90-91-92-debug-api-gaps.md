# Debug API gaps (found by the 2026-10-01 audit)

Surface map: `documentation/ai_learnings_mistakes/AI_SCORER_SYSTEM.md` ("Debug surfaces for agents").

## BL-90 — No way to inspect a live session's full state or the turn's internals
- **Open:** an agent verifying beta sees only `debug_box` (clock, location, speakers, people present, transient entries,
  last 3 NPC decisions) and, with the operator token, `prompt_debug`. Everything else the turn computes stays in the
  server log or is invisible: the per-stage timings (`StageTimer.as_ledger`, logged as `turn_stage_ledger` at
  `prompt_engine.py` ~3975), the extractor result (`extraction.movement_intent/destination_id/confidence/knowledge_updates`,
  logged only as counts in `turn_extraction_complete`), the retrieved chunk ids, and the whole `WorldModel`
  (`to_dict()`: counters, standing, agendas, agreements, epistemics, endings, pending_choice). To see any of it an agent
  must replay locally. Beta's operator token is not available to agents, so the operator path can only be proven locally.
- **Next:** (a) operator-only `GET /api/debug/session/{session_id}` returning `state` and `world_model.to_dict()` from the
  persisted session (read-only, never mutates); (b) operator-only `turn_trace` in the `/api/chat` response next to
  `prompt_debug`: `stage_ms`, extractor result, retrieved chunk ids, NPC decision mode used, token usage;
  (c) operator probe `GET /api/debug/ping` returning `{enabled, token_ok}` so an agent learns in one call whether the
  operator surface works on a given host; advertise all three in `eval_capabilities.py`. Tests: each field present for an
  operator request and absent for a player request (extend `tests/backend/app/api/test_prompt_engine.py`).
- **Touches:** `backend/app/api/prompt_engine.py`, `backend/app/api/debug_engine.py` (or a new small router),
  `backend/app/api/eval_capabilities.py`, `AI_SCORER_SYSTEM.md`, `ship-and-verify` skill.

## BL-91 — `debug_box` is thin for non-Terrace features
- **Open:** `debug_box` (`prompt_engine.py` ~3871) has no turn number, no flag state (`truth_mode`, `epistemic_state`,
  `chinese_mode`), no world-clock counters or standing, and shows only the last 3 `decision_log` records. A new mechanic
  that keeps state outside those fields is invisible on a live player session, which is what `[D]` is for.
- **Next:** add `turn`, `flags`, `counters` and a generic `mechanics` dict that a subsystem fills through one registration
  helper (so a new feature adds one line, not an edit to the handler). Player-safe fields only: anything that spoils the
  story goes in the operator `turn_trace` (BL-90), never `debug_box`.
- **Touches:** `backend/app/api/prompt_engine.py`, `tests/backend/app/api/test_prompt_engine.py`.

## BL-92 — Debug-surface hardening
- **Open:** (a) `auth/dependencies.py` compares the operator token with `!=` in `_check_operator_token` and
  `is_operator_request` (not constant time); (b) the token may travel as an `operator_token` query parameter, which URL
  logs record; (c) `GET /api/auth/debug-config` (`api/auth.py` ~201) is unauthenticated and reports which secrets are set
  and their lengths.
- **Next:** `hmac.compare_digest`; keep the query parameter for WebSocket only; put `debug-config` behind
  `require_operator`. Tests: wrong/missing token and unauthenticated `debug-config` are refused.
- **Touches:** `backend/app/auth/dependencies.py`, `backend/app/api/auth.py`, their tests.
