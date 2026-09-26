# Phase 5 — reusable frontend and coherent assets: implementation design

September 22, 2026. Implementation-level design for
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md` Phase 5.

**Status: design only. Nothing here is implemented.**

---

## 1. Correction to the original plan's factual claims

The plan states: *"the current index does not load that module or consume
`world_map`; it still uses the older image path"* and *"the webhook's asset
list also omits those files."* **Both are now stale**, verified against the
current tree:

- `frontend/index.html:1284,1687` load `world-map.css`/`world-map.js`.
- `backend/app/main.py:408-417` serves both via explicit FastAPI routes
  (`@app.get("/world-map.js")` / `.css`, plus `/beta/` variants).
- `index.html:2784` reads `meta.world_map_image_revision` — the map *is*
  wired to live data, not the older static image path alone.
- The gitwebhook's asset list is moot regardless: Phase 0A established that
  mechanism has no live listener (Railway serves everything). Its omitted
  file list can't cause a production asset gap because it never runs.

This correction matters for scope: the map is **integrated**, not unfinished.
This phase's asset-manifest work (§5) is about giving `world-map.js/css` (and
`dialogue.js/css`) a declared place in one manifest, not about finishing an
integration that already shipped. Verify current live state before doing
manifest work, in case another parallel session's commits have moved further.

---

## 2. Current state, measured

`frontend/index.html`: **3,772 lines** (measured 2026-09-22; the plan's cited
3,798 was accurate at audit time — 26 lines moved since, consistent with the
ongoing parallel map-related commits visible in git log). One file: markup,
CSS, and all JS state/network/rendering code together, IIFE-wrapped, no build
step (this is a deliberate project constraint per `AI_UI_WORKFLOW.md`, not
something this phase removes).

`sendMessage()` at `index.html:2901` already has, from prior shipped work:
- a `request_id` generated per logical send (`genUUID()`, reused only for a
  genuine retry per its own comment) — this is the frontend half of BL-02,
  already wired to Phase 1.1's backend dedup.
- The gap the plan names: **no visible retry UI**. A failed `fetch` shows an
  error message; the player must retype and resend, not tap "retry" on the
  exact same `request_id`.

---

## 3. What this phase does NOT do

Per the plan's explicit instruction, repeated here because it is a hazard for
this specific phase: **preserve the existing appearance before any product
change.** This phase is an internal file-boundary refactor. No visual diff is
an acceptable outcome of any step below; a visual diff is a bug to fix, not a
byproduct to explain away.

No bundler/build step is introduced. `AI_UI_WORKFLOW.md`'s existing constraint
(single-file, no build) becomes single-*directory*, still no build — modules
are separate `<script>`-tag-loaded files (matching how `dialogue.js` and
`world-map.js` already work today), not ES modules requiring a bundler.

---

## 4. Module extraction

### 4.1 Target layout

```
frontend/
  index.html          shell: markup + <script src> tags in dependency order,
                       shrinks from ~3,772 lines toward markup + wiring only
  app/
    api.js             fetch wrapper, apiHeaders(), request_id generation,
                       retry queue (§4.4)
    session-store.js    localStorage read/write for storieschat_sessions,
                       storieschat_profile, storieschat_stats
  features/
    chat.js            sendMessage, addMessage, typing indicator, dialogue
                       rendering hookup (calls into existing dialogue.js)
    catalogue.js        home screen story cards, story fetch/render
    journal.js           journal modal fetch/render (already a self-contained
                       block per its own modal pattern — lowest-risk first
                       extraction)
    roster.js            cast roster modal fetch/render
    map.js               inline world-map wiring (renderInlineWorldMap etc.) —
                       coordinates with the EXISTING world-map.js, does not
                       replace it
    auth.js              login modal, guest-bypass toggle, ?token= callback
  shared/
    dialogs.js           generic modal open/close helpers used by 4+ features
    formatting.js         genUUID, timestamp/display-name helpers
    motion.js             reduced-motion preference read/write (§6)
  dialogue.js           UNCHANGED — already its own file
  dialogue.css          UNCHANGED
  world-map.js          UNCHANGED — already its own file, already loaded
  world-map.css         UNCHANGED
```

### 4.2 Extraction order — smallest blast radius first

| Step | Module | Why first/last |
| --- | --- | --- |
| 1 | `shared/formatting.js` | Pure functions (`genUUID`, display-name helpers), zero DOM coupling, easiest to verify byte-identical behavior |
| 2 | `shared/dialogs.js` | Generic modal helpers reused by journal/roster/map modals — extracting this before those three avoids triplicating the extraction |
| 3 | `features/journal.js` | Already the most self-contained feature (one fetch, one modal, no cross-feature state) — Phase 1.4's shipped journal work makes this the best-understood surface to move first |
| 4 | `features/roster.js` | Same modal pattern as journal, second-lowest risk |
| 5 | `app/session-store.js` | Used by many features but itself has no feature logic — extracting it before `chat.js`/`catalogue.js` means those two don't each reimplement localStorage access |
| 6 | `app/api.js` | The retry-queue work (§4.4) lands here — do this before `chat.js` since `chat.js` will call into it |
| 7 | `features/catalogue.js` | Home screen, independent of chat state |
| 8 | `features/map.js` | Coordinates with `world-map.js` (unchanged) — must come after `app/api.js` since map data comes from a fetch |
| 9 | `features/auth.js` | Touches the guest-bypass flag and login modal; left late because Phase 0's auth design (`AUTH_AND_PERSISTENCE_DESIGN.md`) is the authority here and any surprise interaction should surface after simpler extractions are proven safe |
| 10 | `features/chat.js` | Largest, most stateful, done last — by this point six other modules exist and chat.js mostly becomes wiring between them |

Each step: copy the relevant functions into the new file unchanged, add a
`<script src="app/formatting.js">`-style tag in `index.html` in dependency
order, delete the now-duplicated code from `index.html`, and run the full
browser verification in §7 before moving to the next step. **One module per
commit** — this phase produces ~10 small, independently revertible commits,
not one large one.

### 4.3 How modules communicate without a build step

No ES `import`/`export` (would require `type="module"` and CORS-sensitive
`file://` behavior during local dev, plus stricter script-order requirements
than the current tolerant global-scope pattern). Instead: each module attaches
its public surface to one namespace object, matching the existing pattern
`dialogue.js` already uses (verified: it exposes functions the main script
calls directly, no module system).

```js
// app/api.js
window.StoriesChat = window.StoriesChat || {};
window.StoriesChat.api = {
  send: async function(payload) { ... },
  apiHeaders: function() { ... },
};
```

`index.html`'s remaining wiring code calls `StoriesChat.api.send(...)` instead
of a bare `sendMessage`'s old inline fetch. This is the minimum-risk
compromise between "no build step" and "no global namespace pollution" — one
namespace, not dozens of bare globals.

### 4.4 Pending-request persistence + retry UX

The actual new behavior this phase adds (not just extracted, genuinely new):

```js
// app/api.js
StoriesChat.api.send = async function(sessionId, text, options) {
  const requestId = (options && options.requestId) || StoriesChat.formatting.genUUID();
  const pending = { sessionId, text, requestId, ts: Date.now() };
  StoriesChat.sessionStore.savePendingRequest(pending);   // localStorage, survives a reload

  try {
    const result = await fetch(CHAT_URL, { method: "POST", body: JSON.stringify({
      session_id: sessionId, message: text, request_id: requestId,
    })});
    StoriesChat.sessionStore.clearPendingRequest(sessionId);
    return result;
  } catch (err) {
    // pending request stays in localStorage; caller shows retry UI
    throw new PendingRetryableError(requestId, err);
  }
};
```

On chat screen load, `StoriesChat.sessionStore.getPendingRequest(sessionId)`
is checked: a leftover pending request (page was closed/crashed mid-send)
surfaces a "Resend?" banner using the **same `requestId`** — which Phase 1.1's
backend dedup (already shipped) will either replay the completed reply for
(if it actually succeeded server-side before the client lost the response) or
process fresh (if it genuinely never reached the server). This is the
"pending-request persistence plus timeout/retry UX, paired with Phase 1.1's
request-ID dedup so a user-visible retry is safe by construction" the plan
calls for, made concrete.

**Timeout UX:** a fetch exceeding a client-side timeout (recommend 45s,
comfortably above the storyteller's own 30s server-side timeout so the client
never "gives up" before the server would have) shows the same retry banner
rather than a bare error, using the identical `requestId`.

### 4.5 Test plan (module extraction)

Frontend tests in this repo are Node (`.test.cjs`, per `tests/frontend/`) plus
Python-driven browser checks (per `test_cast_roster_ui.py` etc.) — this phase
follows both existing patterns, adds none new.

| Test | Assertion |
| --- | --- |
| `formatting.test.cjs` | `genUUID()` produces the same format as today's inline version; existing display-name helpers unchanged |
| `api_retry.test.cjs` | `StoriesChat.api.send` persists a pending request before the fetch resolves, clears it on success, leaves it on failure |
| `test_pending_request_survives_reload.py` (Playwright) | simulate a network failure mid-send, reload the page, assert the retry banner appears with the same `requestId` (inspect via `page.evaluate` reading `localStorage`) |
| `test_retry_uses_same_request_id.py` (Playwright) | click "Resend", assert the outgoing request's `request_id` matches the original (network intercept) |
| one characterization test per extracted module | before/after: call the function through the OLD inline location vs the NEW module path with identical inputs, assert identical output — written before each step 1-10 extraction, per the plan's general "characterization tests before moving behavior" rule |

---

## 5. Asset manifest

### 5.1 Problem, restated correctly (per §1's correction)

The real gap is not "the map isn't wired" (it is). The real gap is that
**there is no single declared list** of which static files the frontend
depends on — `index.html`'s own `<script src>`/`<link>` tags are the only
place this exists today, duplicated by nothing (the previously-cited webhook
asset list is dead code per Phase 0A and irrelevant to what actually ships).
So the risk this row protects against is real but different from how the
plan described it: **a future asset added to `index.html` with no
corresponding cache-busting/service-worker awareness**, not a deployment-path
omission.

### 5.2 Design

```json
// frontend/asset-manifest.json — new, single source of truth
{
  "version": 6,
  "assets": [
    {"path": "dialogue.js", "cache": "versioned"},
    {"path": "dialogue.css", "cache": "versioned"},
    {"path": "world-map.js", "cache": "versioned"},
    {"path": "world-map.css", "cache": "versioned"},
    {"path": "manifest.json", "cache": "shell"},
    {"path": "sw.js", "cache": "shell"}
  ]
}
```

Three consumers, each reading this file instead of hardcoding a list:

1. **`index.html`**: a small inline script reads `asset-manifest.json` at load
   and appends `?v={version}` to each `<script src>`/`<link href>` — replacing
   today's manually-typed `?v=1` query strings (verified present:
   `world-map.css?v=1`, `world-map.js?v=1`). One version bump in the manifest
   updates every asset's cache-buster at once, instead of hand-editing each
   tag.
2. **`backend/app/main.py`**: the existing per-file `FileResponse` routes stay
   (no route consolidation — that would be a bigger, riskier change than this
   phase's scope), but a new test (§5.3) asserts every `path` in the manifest
   has a corresponding route, so an asset can't be added to the manifest
   without also being served.
3. **`sw.js`**: `SHELL_URLS` (currently a hardcoded array,
   `frontend/sw.js:5`) is generated from the manifest's `"cache": "shell"`
   entries at build-time-equivalent (a small script run manually or in CI,
   since there's no bundler) rather than hand-maintained.

`CACHE_NAME` in `sw.js` (currently `'storieschat-v5'`, hand-incremented) is
tied to `asset-manifest.json`'s `"version"` field going forward — one number
to bump, not two files to remember to keep in sync.

### 5.3 Test plan

| Test | Assertion |
| --- | --- |
| `test_every_manifest_asset_has_a_backend_route` | for each `path` in `asset-manifest.json`, `backend/app/main.py` defines a `FileResponse` route serving it (reflection over the FastAPI route table, or a simple grep-based check — either is acceptable, the point is CI catches a mismatch) |
| `test_sw_shell_urls_generated_from_manifest` | `sw.js`'s `SHELL_URLS` array matches the manifest's `"cache": "shell"` entries |
| `test_index_html_uses_manifest_version_for_cache_busting` | the inline version-read script appends the manifest's current version to each asset URL (Playwright: inspect actual `<script>` `src` attributes after page load) |
| `test_world_map_assets_still_referenced` (already exists: `test_world_map_assets.py`) | re-run unmodified — confirms this phase does not regress the already-shipped map integration |

---

## 6. Accessible motion settings

### 6.1 Current state — corrected after verification

The plan's phrasing ("preserve... the existing animation option") turned out
to describe real, already-shipped functionality more extensive than an
initial search suggested. Verified in `index.html`:

```js
var TYPEWRITER_SPEED_KEY = "storieschat_typewriter_speed";
var TYPEWRITER_SPEEDS = [10, 4, 2.5];      // ms per character, 3 user-selectable speeds

function getTypewriterDelay(){
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return 0;
  var idx = parseInt(localStorage.getItem(TYPEWRITER_SPEED_KEY) || "1", 10);
  ...
  return TYPEWRITER_SPEEDS[idx];
}
```

So today: (1) the OS-level `prefers-reduced-motion: reduce` is **already
respected** and forces instant (0-delay) reveal; (2) a 3-speed typewriter
setting already exists and is already localStorage-backed; (3) history replay
already passes `skipTypewriter: true` (`index.html:2637,2697`) so loaded past
messages never re-animate.

**The actual, narrower gap:** there is no **in-app override** independent of
the OS setting. A player on a shared/managed device without OS-level access,
or one who simply wants instant reveal without changing system accessibility
settings, has no in-app "always skip animation" control — only the 3 speed
levels, none of which is "off," and the only "off" path is the OS setting
`getTypewriterDelay()` already checks. This is a much smaller change than a
new motion subsystem — it is one more value alongside the existing 3 speeds.

### 6.2 Design

```js
// shared/motion.js — wraps the EXISTING mechanism, does not replace it
window.StoriesChat = window.StoriesChat || {};
StoriesChat.motion = {
  // Index 3 = new "instant" option, appended after the existing 3 speeds
  // so TYPEWRITER_SPEED_KEY's stored values (0/1/2, real player data) stay
  // valid and unchanged in meaning.
  SPEEDS: TYPEWRITER_SPEEDS.concat([0]),

  getDelay: function() {
    // Preserves getTypewriterDelay()'s exact OS-check-first order; the only
    // change is reading from the extended SPEEDS array.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return 0;
    var idx = parseInt(localStorage.getItem(TYPEWRITER_SPEED_KEY) || "1", 10);
    if (!Number.isFinite(idx) || idx < 0 || idx >= this.SPEEDS.length) idx = 1;
    return this.SPEEDS[idx];
  },
};
```

`getTypewriterDelay()` becomes a thin call into `StoriesChat.motion.getDelay()`
(one of §4.2's extraction steps, folded into `shared/motion.js` rather than
staying inline) — same OS-check-first order, same storage key, same stored
value semantics for existing players (index 0/1/2 unchanged), with index 3
added as the new always-instant option in whatever settings UI already
exposes the 3-speed picker.

**This does not touch BL-13's larger scope** (keyboard-safe shell, map/sheet
redesign) — those remain deferred pending BL-13's own re-audit, per §1's
finding that re-auditing before acting is the standing instruction for that
backlog item specifically.

### 6.3 Test plan

| Test | Assertion |
| --- | --- |
| `motion.test.cjs` | `getDelay()` returns 0 when `matchMedia` reports reduced motion, REGARDLESS of stored speed index (OS check must stay first, matching today's exact order) |
| `motion.test.cjs` | `getDelay()` returns each of the 4 `SPEEDS` values for stored indices 0-3 |
| `test_existing_speed_settings_unaffected.py` (Playwright) | a player with `storieschat_typewriter_speed=0` stored from BEFORE this change still gets the same slow speed after it (index semantics preserved) |
| `test_new_instant_option_skips_reveal_animation.py` (Playwright) | selecting the new 4th option renders a new NPC reply in full immediately |
| `test_reduced_motion_still_forces_instant.py` (Playwright, `prefers-reduced-motion: reduce` emulated) | unchanged existing behavior, re-verified after the extraction |

---

## 7. Verification protocol (unchanged from CLAUDE.md §9, restated as this phase's own checklist)

Per each extraction step in §4.2 and each of §5/§6's additions:

1. **Desktop Chromium** against local dev server — visual diff check (none
   expected) + the specific characterization test for that step.
2. **iPhone-sized WebKit session** — same page, same checks. This is where a
   module-loading order mistake (a `<script>` tag moved before its dependency)
   would most likely surface as a console error, per BL-13's history of
   mobile-specific findings.
3. After all steps land locally and pass both modes: push to beta, repeat both
   modes against the live hosted beta site (not just local dev server) —
   **this is the step Phase 4's `BL-03` incident (referenced in
   `ship-and-verify`'s own skill doc) exists to prevent skipping**: a bug that
   only exists in the deployed/browser context, not in local dev or pytest.

**Exit criteria (unchanged from the plan):** desktop Chromium and iPhone-sized
WebKit checks per CLAUDE.md §9, local then live beta; no duplicate send;
guest/auth resume, history, roster, map, journal, and offline upgrade all
work; stale-cache upgrade and rollback tested on both hosts (the asset-
manifest version bump from §5.2 is the concrete mechanism this last item
tests against).

## 8. What this phase deliberately does not do

- Does not introduce a bundler, transpiler, or `npm run build` step.
- Does not touch `dialogue.js`/`world-map.js` internals — both are already
  separate files with working integrations (§1); this phase only gives them a
  declared place in the manifest.
- Does not act on BL-13's keyboard-safe-shell or map/sheet-redesign items —
  those need BL-13's own re-audit first, per that backlog entry's explicit
  instruction.
- Does not change the PWA's `manifest.json`/`sw.js` *behavior*, only how
  `sw.js`'s asset list is generated (from the new manifest instead of
  hand-maintained).
