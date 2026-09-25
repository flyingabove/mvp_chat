---
name: ship-and-verify
description: StoriesChat's end-to-end change workflow — implement with tests, verify offline, push to beta, poll the live Railway deploy, then actually exercise the feature on the hosted beta site before calling anything done. Use this for any non-trivial code change in this repo (backend or frontend), not just for hotfixes.
user-invocable: true
---

# /ship-and-verify — implement, test, deploy, prove it works live

This project's standing failure mode is stopping at "tests pass locally" and
calling that done. Tests passing is necessary, not sufficient — this repo has
already shipped confirmed bugs (BL-03: a frontend fix that passed the full
local suite but silently called the wrong backend once actually deployed,
because the bug only exists in the deployed/browser context, not in pytest).
This skill closes that gap by treating "deployed and confirmed live" as part
of the definition of done, not a separate follow-up step.

Read `documentation/BACKLOG.md` and `documentation/AI_DOC_INDEX_CATALOGUE.md`
first if you haven't already this session — check whether the thing you're
about to do is already a tracked backlog item (update it instead of
duplicating), and find the right doc to update for whatever you change.

## Phase 1 — Implement offline, prove it with unit tests

1. Work on `beta` only. Confirm the checkout is clean, then run
   `git pull --no-rebase origin beta` before making changes. This shared checkout can receive another
   agent's commits; read their intent before merging and never force-push.
2. Activate the `storieschat` conda env for anything Python.
3. For a bug fix: write a test that reproduces the bug FIRST, confirm it
   fails, then fix, then confirm it passes. For a new feature: write tests
   that verify the new behavior. No exceptions — this is a hard project rule,
   not a suggestion (`.claude/CLAUDE.md` §7).
4. Frontend tests exist: use Node's built-in test runner for
   `tests/frontend/*.test.cjs` and structural pytest checks under
   `tests/frontend/`. For PowerShell, run
   `node --test (Get-ChildItem tests/frontend -Filter '*.test.cjs' | ForEach-Object FullName)`.
   Add a regression check for the actual bug.
   These tests cannot replace a browser pass.
4a. **For every UI-visible change, run real browser checks locally before
    committing.** Follow [BROWSER_QA.md](BROWSER_QA.md) with the `storieschat`
    Python environment. Launch desktop Chromium (1440×1000), iPhone 13
    **WebKit** (`playwright.devices["iPhone 13"]`), and simulated standalone
    WebKit (`navigator.standalone = true` before page load). A resized desktop
    Chromium page is not a WebKit/iOS check. Use
    `scripts/verify_ui_browser.py` for baseline load, errors and screenshots,
    then run or adapt `scripts/verify_mobile_pwa_browser.py` to click through
    the feature. Check console/network errors, API host, touch interactions,
    top and bottom edges, safe-area gap and overlays. Inspect the screenshots
    yourself. If Playwright tooling is missing, install its Chromium/WebKit
    browser binaries in the `storieschat` environment; do not silently skip
    visual QA or claim a physical iOS device was tested.
5. Run the full suite: `python -m pytest tests/ -x -q`. Must be 100% pass,
   zero skips (conftest.py hard-fails any skip attempt — this is
   intentional, don't work around it).
6. Fetch current `origin/beta` again before shipping. Commit a checkpoint on
   `beta` if substantial work needs protection, merge newer commits while
   preserving both agents' intent, then rerun the full suite and any affected
   browser flows. Resolve conflicts by reading the commits, not by choosing
   blanket ours/theirs.

## Phase 2 — Ship it

7. Commit with a detailed message: WHY, WHAT CHANGED per file, SIDE EFFECTS
   (see `documentation/ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md`
   for the exact format — another agent may need to resolve a merge conflict
   from this message alone).
8. Push to `beta` ONLY. Never `prod`, never `main` (deleted, don't recreate
   it). Only merge `beta` → `prod` when the user explicitly asks.
9. If you touched `documentation/BACKLOG.md` items, move them to Done with
   the closing commit SHA in the same push.

## Phase 3 — Poll the real deploy, then actually use the feature

Railway auto-deploys `beta` on push, but the build (Docker, heavy deps like
torch) can take several minutes — don't assume it's live immediately, and
don't silently skip this phase because polling is slower than you'd like.

10. **Poll for the new build**, don't just wait a fixed guess-time.
    `/api/health` DOES carry a commit-SHA stamp (confirmed 2026-09-21) — poll
    it directly and compare against your pushed SHA, this is the most
    reliable signal since it doesn't depend on what you happened to change:
    `curl -s https://beta-api.storieschat.ai/api/health` →
    `{"ok":true,...,"commit":"<full sha>","environment":"beta",...}`. For a
    frontend-only change you can also poll for a content-level signal
    specific to what you shipped — e.g. `curl -s
    https://beta-api.storieschat.ai/api/stories | grep -o '<new_story_id>'`
    for new content, or a distinctive string from a frontend change via
    `curl -s https://storieschat.ai/beta/ | grep -o '<new_marker>'` — but
    prefer the `/api/health` commit check when in doubt, since it confirms
    the deploy landed even when your specific change has no easily-grepped
    marker. Note storieschat.ai/beta/ page responses are `CF-Cache-Status:
    DYNAMIC` (no edge caching), so a stale result there means the Railway
    origin itself hasn't redeployed yet, not a CDN cache issue. Poll on an
    interval matched to Railway's actual build
    time (start around 20-30s, don't hammer it every 2s) and don't block the
    conversation indefinitely — after a couple minutes without a hit, say so
    and either keep polling in the background or move on to other work and
    check back, rather than silently giving up and reporting success anyway.
11. **Hit the real endpoints**, not the local dev server, once the new build
    is confirmed live: `beta-api.storieschat.ai` directly, and
    `storieschat.ai/beta/` for the page itself (the two are NOT
    interchangeable — see BL-03; a page-level check alone would have missed
    that bug). Confirm the specific thing you changed actually behaves
    differently, not just that the server responds.
12. **Repeat the real browser flow against hosted beta.** Use the executable
    commands in [BROWSER_QA.md](BROWSER_QA.md), substituting
    `https://storieschat.ai/beta/` and an expected API host of
    `beta-api.storieschat.ai`. Run desktop Chromium, iPhone 13 WebKit, and
    simulated standalone WebKit in fresh contexts. `verify_ui_browser.py`
    catches load, console and API failures; the task-specific feature script
    must click the changed behavior. Save and personally inspect screenshots
    in every mode, including the full top edge, fixed bottom navigation and
    safe-area region. Inspect dialogs/maps/portraits and test their controls.
    Check API request hosts and HTTP failures after interactions, not only on
    initial page load. For PWA work, run the legacy-worker upgrade script
    locally before shipping and check live no-store HTML/worker, hashed asset
    URLs, matching shell revisions and `/beta/` manifest scope.

    Playwright MCP tools may be used for exploration, but are optional when
    the Python Playwright scripts are available. A resized Chromium viewport
    cannot stand in for WebKit. If browser binaries are unavailable and cannot
    be installed, state the exact gap; never claim iOS/visual QA from curl or
    screenshots taken in desktop Chromium. Simulated standalone is not a
    physical iPhone installation.
13. If live verification finds a bug that local tests didn't catch: that's a
    real bug in production-adjacent (beta) infrastructure. Go back to Phase
    1 — write a test that would have caught it if at all feasible (matching
    the `tests/frontend/` structural-guard pattern for anything untestable
    by the Python suite), fix it, and re-run this whole skill rather than
    patching live and calling it done.

## Reporting

State plainly: what was tested offline (and how), what was pushed and when,
how long the deploy took to go live, what was checked on the actual live
site (curl-level and, if available, browser-level), and any gap you weren't
able to close (tool unavailable, infra you can't verify from the repo,
scoped-out follow-up) — add a `documentation/BACKLOG.md` entry for the last
category rather than letting it evaporate. Never report a feature as
"working" or "deployed" based on local test results alone.
