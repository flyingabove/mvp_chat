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

1. `git pull --rebase origin beta` before starting (multi-agent workflow —
   see `documentation/ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md`).
2. Activate the `storieschat` conda env for anything Python.
3. For a bug fix: write a test that reproduces the bug FIRST, confirm it
   fails, then fix, then confirm it passes. For a new feature: write tests
   that verify the new behavior. No exceptions — this is a hard project rule,
   not a suggestion (`.claude/CLAUDE.md` §7).
4. If you're changing frontend JS in `frontend/index.html` or
   `frontend/debug.html`: there is no JS test harness in this repo. The
   precedent (see `tests/frontend/test_beta_api_base.py`, from the BL-03 fix)
   is a structural/string-level regression test asserting the specific
   pattern you fixed is present and the specific bug pattern is absent. This
   is a floor, not a substitute for the live browser check below — a
   string assertion cannot catch a runtime JS error, a CORS rejection, or a
   layout break.
4a. **Any UI-visible change (frontend/index.html, frontend/debug.html, CSS,
    manifest.json, sw.js) MUST be checked in a real browser against your
    local dev server BEFORE you commit** — not just before calling the task
    done. Use the Playwright MCP tools (`playwright@claude-plugins-official`
    — confirm with `claude plugin list` if tools aren't showing up) to run
    both of the following against `localhost`, using the exact procedure in
    Phase 3 step 12 below:
    - **Desktop Chromium** — default Playwright viewport/browser.
    - **iPhone-sized WebKit** — `browser_resize` to 390×844 (or 430×932),
      plus true WebKit engine + iOS Safari UA + touch emulation via
      `browser_run_code_unsafe` (Playwright's `devices['iPhone 13']`
      descriptor), per the detailed steps in Phase 3 step 12.
    Check the console for JS errors in both, and actually click the golden
    path for what you changed — don't just load and screenshot. **Always
    inspect the resulting screenshots or live browser surface yourself before
    committing**: evidence must visibly include the full top edge, the fixed
    bottom navigation, and the safe-area region beneath it. This is mandatory
    for iOS standalone/PWA work, where a technically successful load can
    still leave clipped content or an empty black viewport band. If Playwright
    tools are genuinely unavailable, say so explicitly and do not commit a
    UI-visible change without this check; escalate to the user instead of
    skipping it silently.
5. Run the full suite: `python -m pytest tests/ -x -q`. Must be 100% pass,
   zero skips (conftest.py hard-fails any skip attempt — this is
   intentional, don't work around it).
6. `git pull --rebase origin beta` again before committing (catch parallel
   agent pushes). If new commits landed, re-run the full suite — integration
   with someone else's change is a real failure mode, not paranoia.

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
12. **Drive it in a real browser** using the Playwright MCP tools (installed
    via `claude plugin install playwright@claude-plugins-official` — if
    those tools aren't available in your current tool list, the plugin was
    installed after this session started and needs a Claude Code
    restart/reconnect to load; say so explicitly rather than silently
    skipping this step). This project is primarily played as an iOS
    "Add to Home Screen" webapp, so **verify BOTH a standard desktop/website
    view AND an iOS-simulated view — every time, not just for PWA/cache
    changes**:
    - **Website mode**: default Playwright viewport, navigate to
      `https://storieschat.ai/beta/`.
    - **iOS-simulated mode**: the Playwright MCP tools here don't expose a
      device picker directly, so simulate iOS with what they do give you:
      1. `browser_resize` to an iPhone viewport (390×844 for iPhone 13/14,
         or 430×932 for a Pro Max) — this alone catches most layout/touch
         sizing bugs.
      2. For true Safari/WebKit engine + iOS user-agent + touch emulation
         (not just viewport size), use
         `browser_run_code_unsafe` to drive Playwright's own device
         descriptors, e.g.:
         `async (page) => { const { devices } = require('playwright'); /* if unavailable in this context, fall back to context.newPage with a manually-set userAgent + viewport + hasTouch:true, isMobile:true matching devices['iPhone 13'] */ }`
         — if `browser_run_code_unsafe` can't load Playwright's `devices`
         registry in this sandboxed context, at minimum set the iPhone
         Safari UA string manually
         (`Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)
         AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0
         Mobile/15E148 Safari/604.1`) alongside the resized viewport.
      3. This project's PWA-specific behavior (service worker caching,
         `standalone` display mode, `manifest.json`, the iOS install
         prompt, the hard-reload button) is exactly the class of bug that
         only reproduces under iOS Safari's cache/rendering quirks — a
         desktop Chrome pass alone is not sufficient for any change
         touching `sw.js`, `manifest.json`, or anything under the
         `iOS INSTALL PROMPT` / `HARD RELOAD` blocks in
         `frontend/index.html`.
    - For BOTH modes: open the browser console and check for JS errors on
      load and after each interaction — a silent console error is exactly
      the class of bug unit tests and curl checks both miss.
    - Actually click through the golden path relevant to your change (pick a
      story card, send a chat message, navigate a menu — whatever you
      touched), not just load the page and screenshot it.
    - Take at least one screenshot per mode as evidence, inspect both images
      yourself for clipping, safe-area gaps, and bottom-bar placement, and
      note both in your report.
    - Check the Network tab / requests for which host API calls actually hit
      (this is how BL-03 would have been caught immediately instead of via
      manual curl comparison).
    If Playwright tools are genuinely unavailable this session, fall back to
    API-level verification via curl/PowerShell against the real hosted
    endpoints and say explicitly that browser-level QA (console errors,
    visual layout, click-through, and the iOS-simulated pass) was not done
    and why — never claim "smoke tested in browser" or "verified on iOS"
    when you only checked curl output or a desktop-viewport pass.

    The same website-mode + iOS-simulated-mode pass applies locally too
    (Phase 1/local dev server), not just against the deployed beta site —
    catch layout/PWA regressions before they ever reach beta.
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
