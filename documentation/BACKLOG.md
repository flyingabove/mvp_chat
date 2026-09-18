# Backlog

> **What this doc is for:** Tracks deferred follow-up work — findings, gaps, or manual actions that were identified but not fully resolved. Add an entry whenever work is knowingly deferred instead of finished; remove/move to "Done" once actually resolved (link the commit).
>
> Referenced from `.claude/CLAUDE.md` — check this file at session start alongside the doc index.

---

## Open

### BL-01 — Non-atomic turn snapshot (source: audit A08, P1)
**What:** The turn save happens before `over`/`last_turn_*` updates and before async background fact-extraction completes; belief/observation state isn't fully snapshotted and gets re-seeded on restore.
**Why deferred:** Audit itself calls this "a meaningful refactor" — needs a versioned snapshot boundary plus a durable outbox for background fact-extraction, not a quick patch. Rushing it risked a bad abstraction.
**What's needed:** Design a turn-commit boundary that atomically persists core state + `over` + `last_turn_*` + belief/observation state together; move background fact-extraction to a durable queue/outbox with its own completion marker. Add a restore-fidelity test (save mid-turn → restore → assert `over`/`last_turn_*`/beliefs match).
**Touches:** `backend/app/api/prompt_engine.py`, `backend/app/db/repos.py`, `backend/app/engine/state.py`.

### BL-02 — Turn retry idempotency (source: audit A12 remainder, P1)
**What:** Per-session corruption is now prevented via an `asyncio.Lock` (commit `9c3070f`), but a *retried* request (e.g. client timeout + resend) can still double-apply a turn — there's no request-ID based idempotency.
**Why deferred:** Scoped down deliberately to ship the corruption fix first; idempotency needs a request-ID column + dedup check, which is separate surface area.
**What's needed:** Accept a client-generated request ID per turn; store the last-applied request ID (or a short window of them) per session; short-circuit a repeat with the cached prior result instead of reprocessing.
**Touches:** `backend/app/api/prompt_engine.py`, `backend/app/db/repos.py`.

### BL-04 — `frontend/debug.html` doesn't send the new operator token (source: audit A03 follow-up)
**What:** Debug/playback/authoring routes now require `X-Operator-Token` (commit `f443238`), but the hosted debug UI (`frontend/debug.html`) was never updated to send it, so it will 401 against a real deployment with `DEBUG_TOOLS_ENABLED=1`.
**Why deferred:** Out of scope for the security-fix pass (frontend UI wiring, not a vulnerability).
**What's needed:** Add an operator-token input/storage to `debug.html` and send it as `X-Operator-Token` (REST) / `operator_token` query param (WebSocket) on every debug/playback request.
**Touches:** `frontend/debug.html`.

### BL-05 — Rotate any API key that went through the old Docker build-arg path (source: audit A11)
**What:** Before commit `1cf4c9d`, the Dockerfile persisted an `OPENAI_API_KEY` build ARG into image `ENV`, meaning any image actually built that way has the key baked into its config/layers.
**Why deferred:** Not something an agent should do — key rotation is an owner action.
**What's needed:** If that build path was ever run with a real key, rotate the key in the provider dashboard and update the deployment secret.
**Owner action required:** yes.

### BL-06 — NPC→player and NPC↔NPC relationship drift is not mechanically driven (source: social_sim mode + Common Room work, 2026-09-17)
**What:** The numeric relationship extractor (see `backend/app/engine/prompt_builder.py` relationship layer and `backend/app/api/prompt_engine.py` turn extraction) only accepts player→NPC updates today; only the main NPC has a narrative-tag-driven affection path. `relationships.edges` in story JSON seed the *initial* state for all directed pairs (including NPC-NPC edges, as used in `backend/app/stories/6_common_room/`), and player-driven changes to player-facing edges are supported, but nothing updates NPC-initiated or NPC-NPC edges during play.
**Why deferred:** A genuinely dynamic ensemble house sim (e.g. Mina and Dae-ho's friendship visibly drifting from something the player does) needs this, but it's a meaningful extension of the turn-extraction schema, not a small patch, and was out of scope for adding the `mode` layer itself.
**What's needed:** Extend the single-call turn extractor's schema/prompt to propose NPC↔NPC and NPC→player relationship deltas (not just player→NPC), and apply them the same way player-facing deltas are applied today.
**Touches:** `backend/app/engine/extractors/turn_extractor.py`, `backend/app/api/prompt_engine.py`, `backend/app/engine/character_graph.py`.

### BL-08 — No quest/schedule/resource engine (source: social_sim mode + Common Room work, 2026-09-17; pre-existing gap)
**What:** `backend/app/engine/gameplay.py` has no scripted event loop, quest triggers, schedule/job simulation, or resource tracking. A Terrace-House-style social sim game is built entirely from free-form roleplay + `character_self_knowledge` + `epistemic_seed` + the relationship graph + the location/travel graph — see `documentation/model_output_docs/SOCIAL_MODE_DESIGN.md` and `documentation/model_output_docs/GAME_DESIGN_SYSTEMS.md`. Chores/jobs/daily rhythms in story content (e.g. Common Room's chore wheel) are narrative/roleplay content the NPCs can talk about, not mechanically enforced systems.
**Why deferred:** A real scheduling/quest/resource engine is a substantial, genre-spanning feature, not something to bolt on while adding one story mode layer.
**What's needed:** Design a lightweight, story-JSON-declarable schedule/trigger primitive (e.g. NPC location-by-time-of-day, simple flag-gated triggers) that both mystery and social_sim stories could opt into.
**Touches:** `backend/app/engine/gameplay.py`, story JSON schema, `documentation/model_output_docs/GAME_DESIGN_SYSTEMS.md`.

---

## Done

_(move resolved items here with the commit SHA that closed them)_

### BL-07 — `character_self_knowledge` is architecturally single-character (source: social_sim mode + Common Room work, 2026-09-17)
**Resolved by:** `e3a38d8` (`fix(engine): resolve BL-07 - character_self_knowledge is now per-character`), pushed to `beta`.
**What was done:** `Character.from_dict()`/`to_dict()` in `backend/app/engine/state.py` now parse/serialize a per-character `self_knowledge` field (previously silently dropped into `meta` and never read). Both character-roster-construction sites in `backend/app/api/prompt_engine.py` (new-game path, restore path) now prefer a character's own `self_knowledge` when present, falling back to the legacy top-level `character_self_knowledge` array only for the `is_main` character. `_character_identity_section()` in `backend/app/engine/prompt_builder.py` now injects one identity block per qualifying character: the main character's block stays unconditional (unchanged legacy behavior), and every other present character (via `_get_people_present_keys`) with their own `self_knowledge` also gets a block. `backend/app/stories/6_common_room/common_room_story.json` was updated so all three housemates (Mina, Dae-ho, Priya) now author their own `self_knowledge`, demonstrating genuinely ensemble character identity. Backward compatibility with all 5 pre-existing mystery stories is regression-tested (byte-identical single-block output for `iu_murder_mystery`). Full suite: 469 passed, 1 xpassed, 0 failed, 0 skipped.

### BL-03 — Beta/prod isolation via `/beta/` path (source: audit A15, P1 investigation) — CONFIRMED then fixed
**Resolved by:** live-verified via curl (`https://storieschat.ai/api/stories` lacked `common_room`; `https://beta-api.storieschat.ai/api/stories` had it, confirming the beta page was actually reaching prod), then fixed in `frontend/index.html`.
**What was done:** this was upgraded from "unverified" to a confirmed live bug: `frontend/index.html` computed `API_BASE = window.location.origin + "/api"`, so a page loaded from `https://storieschat.ai/beta/` called `https://storieschat.ai/api/...`, which Cloudflare routes to the **prod** Railway origin, not beta — meaning the hosted beta UI's chat feature was silently talking to prod. `frontend/debug.html` already had the correct fix for this exact problem (`_isBeta` detection → `beta-api.storieschat.ai`); `index.html` did not, despite already having a partial version of it for OAuth only (`LOGIN_AUTH_BASE`). Fix: introduced `BACKEND_ORIGIN`, computed the same way `LOGIN_AUTH_BASE` already was, and derived `API_BASE`/`AUTH_BASE` from it instead of a bare `window.location.origin`; also fixed `getStoriesEndpointCandidates()`'s fallback, which previously hardcoded the prod URL unconditionally (would have silently re-introduced the bug on any primary-fetch failure from a beta page). Added `tests/frontend/test_beta_api_base.py` (no JS test harness exists in this repo, so this is a structural/string-level regression guard on the shipped file, not a real browser test). Full suite: 471 passed, 1 xpassed, 0 failed, 0 skipped.
