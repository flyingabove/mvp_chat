# iPhone PWA and web app UI learnings (September 2026)

This records the iPhone 14 Home Screen incident and the related mobile UI work. The user confirmed that installing the new **StoriesChat Beta** icon worked. That confirmation closes the stale-install mismatch; the automated keyboard and layout checks remain simulations, so do not describe them as physical keyboard measurements.

## What went wrong

Safari at `/beta/` displayed the updated split chat, portraits, Refresh Cache, large map close button and pinch zoom. The installed icon showed the older single bubble, upload control, Update App, tiny map close button and a large bottom gap. Treating this as one CSS defect delayed the diagnosis: the two views were running different app versions.

The older production manifest had `start_url: "/"`. Its root service worker also cached the fixed URL `/beta/manifest.json`, carrying that root start URL. Therefore visiting beta in Safari, adding the app to the Home Screen again, or pressing Update App on the existing icon could still launch production `/`. A beta-only deployment cannot change where an existing production icon starts. The old production UI then reproduced the gap and the other apparent formatting failures together.

The fix gave beta a distinct manifest URL (`/beta/manifest-beta-v2.json`), `name`/Home Screen title **StoriesChat Beta**, and `start_url`, `scope` and `id` of `/beta/`. The visible Beta badge makes the active channel recognizable. The new manifest URL bypasses the old worker's fixed-name cached response. Refresh Cache on that beta icon clears its app caches and reloads the current `/beta/` URL; it does not switch an old production icon to beta. Production was not deployed as part of this fix.

## What to check before changing CSS

1. Compare the actual launch URL, page title, install manifest, worker scope, app label and a recognizable UI marker in Safari and the installed app. Different controls or markup usually mean different code is running.
2. Read the manifest returned **through the installed app's existing worker**, not only the network response seen in a fresh browser context. Check `start_url`, `scope` and `id`. A no-store server header cannot override bytes an older worker serves from CacheStorage.
3. Confirm `/api/health` reports the pushed beta SHA before hosted UI tests. Confirm the page at `storieschat.ai/beta/` and API at `beta-api.storieschat.ai` separately, including the API host used by browser calls.
4. If an old icon points to `/`, change the beta install identity and ask for one fresh Beta Home Screen installation. Do not promise that a cache reset inside `/` can rewrite its install start URL.

## Standalone layout and interaction rules

- Safari's visible viewport and a Home Screen app's full screen may report different heights. The shell uses `visualViewport`, `screen.height`, `navigator.standalone` and `display-mode: standalone` to set `--app-height`. In standalone mode it fills the device screen at rest; after a real keyboard shrink it uses the visible viewport. Safe-area variables position the fixed header, tab bar and overlays. A CSS-only `100vh` screenshot cannot prove this behavior.
- When focus plus a sufficiently smaller visual viewport indicates the keyboard, the chat shell gets `keyboard-open`, hides bottom navigation and keeps the composer above the simulated keyboard. On blur it restores the full-height shell. Test focus, viewport resize, scroll, blur and orientation changes; look for both the top overlap and bottom blank area.
- The full-screen map uses the same app height. Its close control is 56×56 CSS pixels, placed below the top safe area, and the image handles two-finger pinch and drag. Test that the control can be tapped and that image scale changes, not just that it is visible.
- Speaker presentation needs ordered narration and named speech beats in the first new-game message and later replies. A single outer reply can contain several speakers; each speech beat must retain its own speaker name and portrait. The Terrace opening is authored and structured; Jev is a fallback for unmarked speech. Portrait URLs were versioned after hosted beta served older cached 96px files, and the larger chat portraits can open full-size images. Inspect real browser output, because a passing data test cannot reveal one giant bubble or the wrong cached asset.
- Keep the upload control absent, preserve distinct AI/narrator and player styling, and check the complete mobile chat flow. The installed app previously showed the old upload button because it was running the old shell, so a fresh install/version check comes before debugging that control.

## Reproduction and proof that mattered

From the repo root, start the local FastAPI server, then run `scripts/reproduce_ios_installed_app.py --url http://127.0.0.1:8899`. It serves the committed production shell/manifest at `/` and current beta at `/beta/` with public requests blocked. iPhone 14 WebKit uses a 390×664 visible viewport against an 844px device screen. Before the fix, the old route produced a 180px bottom gap, old upload/Update App UI, visible tab bar during simulated keyboard focus, 36px map close control and no pinch zoom. The beta route filled 844px in standalone mode, hid the tab during keyboard simulation, and had a 56px close control with pinch scaling.

Run `scripts/verify_pwa_upgrade.py --url http://127.0.0.1:8899/` to install the legacy root worker, prove it can serve stale `/beta/manifest.json`, prove the new manifest path escapes that cache, then verify worker upgrade deletes the stale cache in Chromium and WebKit. `scripts/verify_ui_browser.py` covers desktop Chromium, iPhone Safari WebKit and iPhone 14/15/16 simulated standalone sizes. `scripts/verify_mobile_pwa_browser.py` clicks through Refresh Cache, chat, map, portrait, swipe/delete and keyboard layout. Follow `.claude/skills/ship-and-verify/BROWSER_QA.md` for commands and hosted checks. Simulated standalone WebKit cannot fully reproduce iOS system bars or the native keyboard; the physical install report is the final check.

Beta runtime commit `f639128c9630dc1e2dd0ad932f6ad351e780f569` deployed as Railway `ac508d48-5a44-437d-808f-6b0be8937cc4`. Local verification: 1017 repository tests passed, 1 expected failure, 129 separate arena tests, 10 Node tests, the legacy-worker test, seven viewport modes and three interactive modes. Hosted verification: health reported the exact commit; beta page and manifest were no-store; seven viewport modes and three interactive modes passed without browser/API errors; screenshots were inspected. The user then reported that the new install worked on their iPhone.

## Prevent the same mistake

For every PWA release, test both a clean install and an upgrade from the actual previous production worker/manifest. Record the effective install URL and worker cache behavior. Make beta and production install identities visibly distinct. Version asset URLs when their bytes or dimensions change. Run real WebKit at phone sizes, a standalone simulation and the hosted beta flow, then seek a physical iPhone observation for system UI issues. When the user reports Safari and Home Screen differences, establish whether they run the same code before changing layout styles.
