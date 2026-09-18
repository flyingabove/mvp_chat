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

### BL-03 — Beta/prod isolation via `/beta/` path unverified (source: audit A15, P1 investigation)
**What:** `frontend/index.html` computes `API_BASE = window.location.origin + "/api"` with no `/beta` awareness, while `backend/app/main.py` serves `/beta/*` frontend routes on the same origin as prod, alongside separate `beta.storieschat.ai`/`beta-api.storieschat.ai` subdomains in the CORS allowlist.
**Why deferred:** Whether this is a live isolation bug depends on Cloudflare/DNS routing rules not present in this repo — can't verify or fix blind.
**What's needed:** Manually verify live Cloudflare/DNS routing for `/beta/*` paths vs the `beta.*` subdomains. If a page served under `/beta/` can call the prod API (or vice versa), fix the frontend's API base computation to respect a `/beta/` prefix.
**Owner action required:** yes — infra verification only the user can do.

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

### BL-07 — `character_self_knowledge` is architecturally single-character (source: social_sim mode + Common Room work, 2026-09-17)
**What:** `backend/app/engine/prompt_builder.py::_character_identity_section` and the seeding path in `backend/app/api/prompt_engine.py` (`_canonicalize_story_cfg` / game-init character-building) only ever attach the top-level `character_self_knowledge` array to whichever character is flagged `is_main` (or the first character, via the existing BUG-13 fallback, if none is). For an ensemble cast (e.g. The Common Room's three housemates) this means only one housemate gets a first-person "CHARACTER IDENTITY" prompt section; the others fall back to `motive` (authoring flavor, surfaced via transient story-detail injection) and per-character `epistemic_seed.canonical_facts`/`belief_seeds` for characterization.
**Why deferred:** A true multi-character self-knowledge layer (each present NPC contributing their own identity section when they're in the scene) would need `Character.self_knowledge` to be populated per-character at game init instead of only for `main_character`, plus a prompt_builder change to iterate present characters instead of just `state.main_character` — a change that touches a layer shared by all 5 existing mystery stories, out of scope for the `mode` layer work.
**What's needed:** Populate `Character.self_knowledge` per character (e.g. an optional per-character `self_knowledge` field on each `characters[]` entry), then have `_character_identity_section` (or a renamed multi-character equivalent) iterate present/speaking characters instead of only `state.main_character`. Needs regression coverage across all 5 existing stories to confirm single-character behavior is preserved when a story doesn't use the new per-character field.
**Touches:** `backend/app/engine/state.py` (`Character`), `backend/app/api/prompt_engine.py`, `backend/app/engine/prompt_builder.py`.

### BL-08 — No quest/schedule/resource engine (source: social_sim mode + Common Room work, 2026-09-17; pre-existing gap)
**What:** `backend/app/engine/gameplay.py` has no scripted event loop, quest triggers, schedule/job simulation, or resource tracking. A Terrace-House-style social sim game is built entirely from free-form roleplay + `character_self_knowledge` + `epistemic_seed` + the relationship graph + the location/travel graph — see `documentation/model_output_docs/SOCIAL_MODE_DESIGN.md` and `documentation/model_output_docs/GAME_DESIGN_SYSTEMS.md`. Chores/jobs/daily rhythms in story content (e.g. Common Room's chore wheel) are narrative/roleplay content the NPCs can talk about, not mechanically enforced systems.
**Why deferred:** A real scheduling/quest/resource engine is a substantial, genre-spanning feature, not something to bolt on while adding one story mode layer.
**What's needed:** Design a lightweight, story-JSON-declarable schedule/trigger primitive (e.g. NPC location-by-time-of-day, simple flag-gated triggers) that both mystery and social_sim stories could opt into.
**Touches:** `backend/app/engine/gameplay.py`, story JSON schema, `documentation/model_output_docs/GAME_DESIGN_SYSTEMS.md`.

---

## Done

_(move resolved items here with the commit SHA that closed them)_
