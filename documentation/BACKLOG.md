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

---

## Done

_(move resolved items here with the commit SHA that closed them)_
