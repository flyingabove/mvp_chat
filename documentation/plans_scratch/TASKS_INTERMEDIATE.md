# Intermediate Tasks (Canonical)

Use this file as the single source of truth for intermediate execution tasks.

## Active

### Terrace in the City mobile/PWA and six-resident correctness

- [x] Add reachable cache-clearing Update App navigation action and simplify text-speed choices.
- [x] Eliminate iOS standalone safe-area gap and inspect desktop/mobile screenshots before shipping.
- [x] Randomize valid starting five-NPC roster, enforce player-bedroom opening variants, and retain atomic same-gender replacements.
- [ ] Regenerate the world-map artwork without any guest-room representation; keep it on-demand in a clean full-screen viewer, then deploy beta and live-test.

### Six Strangers researched atlas and isolated Codex checkout

- [x] Clone latest beta into `mvp_chat_for_codex_only`; create `codex/six-strangers-world-atlas`.
- [x] Restore artwork and reusable map/location/route models without touching the shared checkout.
- [x] Model all supplied research IDs, uncertainty, area containers, and estimated travel relationships.
- [x] Finish reusable map UI and verify desktop/mobile behavior locally (Chromium + iPhone 13 WebKit; no page errors or failed requests).
- [ ] Run the full suite, integrate latest beta changes, and retest as needed.
- [ ] Commit, deploy beta, and verify live artwork, data, and interactions.

- [x] Finalize the two-story catalog: keep only IU Murder Mystery and Six Strangers, delete stale inactive games, and align runtime tests to the active catalogue.
- [x] Keep the server-backed default persona system and temp persona flow for the active titles.
- [ ] Push the final beta-ready branch after the live validation step.

## Consumed History

- 2026-09-21: Single-bubble dominant-speaker presentation completed and deployed to beta in `0043948` (Railway deployment `90f2b537-63d8-454f-a5b8-de17aab77f7f`).
	- Restored one bubble per AI reply while retaining structured speaker metadata for reliable attribution.
	- The canonical speaker with the greatest total spoken text supplies the avatar; ties use first appearance.
	- Narration, unknown/side characters, and characters without dedicated art use the game cover.
	- Replaced the Terrace in the City cover with an optimized, realistic Tokyo house image.
	- Verification: `768 passed, 1 xfailed`; four Node renderer tests; local and hosted desktop/390×844 browser passes; hosted console clean; live health endpoint reported `0043948`.

- 2026-03-21: Initialized canonical intermediate-task workflow file.
- 2026-03-22: Save/resume hardening complete.
	- Added persisted runtime snapshots for `character_graph`, `character_locations`, `last_turn_*`, and `session_chunk_store` facts in `state_json`.
	- Added restore logic to rehydrate runtime graph edge state and session BM25 chunks after cache miss/restart.
	- Synced Home-page resume sources to backend `/api/user/sessions` cache so Home and My Games resume the same sessions.
	- Verification: `C:/Users/Christian/miniconda3/envs/storieschat/python.exe -m pytest -q` -> `414 passed, 1 xpassed`.
- 2026-03-22: Cloudflare routing/control-plane documentation hardening complete.
	- Documented current path-based Cloudflare behavior for `storieschat.ai` (`/beta/*` to beta origin, catch-all to prod origin).
	- Added explicit tamper vectors showing how domain-preserving reroutes to different Railway projects can happen via Cloudflare changes.
	- Added required controls: least-privilege tokens, change approval, audit log review, synthetic origin-identity checks, and incident response steps.

## Cleanup Rules (Quick Reference)

1. Keep only open items in `Active`.
2. Move completed lists to `Consumed History` at task completion.
3. If this file exceeds ~200 lines, archive older consumed entries to `ARCHIVE_TASKS_INTERMEDIATE.md`.
