# Real browser UI development and verification

Use this with `SKILL.md` for any visible frontend change. A viewport resize in
Chromium does not test WebKit. Playwright's `devices["iPhone 13"]` supplies an
iPhone user agent, touch support, scale factor, and viewport; launch it with
`playwright.webkit`. `navigator.standalone = true` is a useful layout simulation,
but none of these modes proves behavior on a physical iOS Home Screen install.

## 1. Prepare the local run

Run from the repository root on `beta`. Use the existing `storieschat` conda
environment. On this Windows checkout:

```powershell
$py = 'C:\Users\Christian\miniconda3\envs\storieschat\python.exe'
& $py -c 'import playwright; print("Playwright available")'
& $py -m playwright install chromium webkit  # only if browser binaries are missing
& $py -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8899
```

Keep the server process running in its terminal/session. If port 8899 belongs
to another agent, select a free port and pass the same URL to the scripts.
Do not kill an unknown process. Local Google OAuth is not registered; use the
guest UI for interaction checks.

Store screenshots outside the repository so runtime data is never staged:

```powershell
& $py scripts/verify_ui_browser.py --url http://127.0.0.1:8899/ --output "$env:TEMP\storieschat-ui-qa\local" --expected-api-host 127.0.0.1:8899
& $py scripts/verify_mobile_pwa_browser.py --url http://127.0.0.1:8899/ --output "$env:TEMP\storieschat-ui-qa\local-feature" --expected-api-host 127.0.0.1:8899
```

`verify_ui_browser.py` is a baseline: it saves desktop Chromium, iPhone 14
Safari WebKit, and iPhone 14/15/16 standalone WebKit home screenshots plus
`report.json`. Its iPhone 14 short-viewport case deliberately gives WebKit a
664px visual viewport and an 844px device screen. This reproduces the
installed-app height discrepancy reported on a physical iPhone. Verify the
standalone app shell and tab bar reach the 844px screen bottom while ordinary
Safari ends at its 664px visible viewport. The script also checks console
errors, failed requests, and API hosts.
The feature script clicks through gameplay, map enlargement and pinch zoom,
speaker portrait popout, swipe/resume/delete confirmation, and Refresh Cache.
It verifies the authored opening's separate narration/speaker beats, portrait
and map image dimensions, the map close target, and a simulated keyboard
viewport transition in standalone mode. Its keyboard screenshot shows a blank
area where the native iOS keyboard would be; it tests composer placement, not
the keyboard's appearance. Inspect the screenshots, especially header overlap,
top safe area, bottom navigation, and composer position.

For an iOS Home Screen report, verify the **launch path**, not only the page's
appearance. An older production install can launch `/` even when Safari shows
`/beta/`; its Update App button reloads `/` again. Run
`scripts/reproduce_ios_installed_app.py --url http://127.0.0.1:8899` to compare
the committed production install with beta entirely offline. It asserts the
old bottom gap, visible keyboard tab bar, small map close control, missing
pinch zoom, and upload action against the beta equivalents. Check that the
beta page uses `manifest-beta-v2.json`, that this manifest starts at `/beta/`,
and that Refresh Cache leaves the page on `/beta/`. The older root worker cached
`/beta/manifest.json`, so that filename alone is not an install check.
Use it when those flows are relevant. For other changes, copy its Playwright
pattern and add interactions and assertions for the changed feature. A home
page load alone is never a feature test.

The feature script uses a real story-model reply by default. If that external
provider returns `story master is unavailable`, the script now shows the API
payload immediately. For **UI-only** verification during such an outage, rerun
with `--mock-chat-reply` (and optionally `--mode desktop`, `iphone`, or
`standalone`). This routes only the post-opening chat call to a deterministic
two-speaker response, so it verifies rendering and controls, **not** live model
or backend turn behavior. Mock mode blocks service workers so WebKit cannot
intercept Playwright's route; use the normal mode or `verify_pwa_upgrade.py`
to test worker behavior. Keep the failed real-provider result in the report
and repeat the real path when the provider recovers; never present a mocked
run as end-to-end gameplay success.

## 2. Write useful feature checks

Use one fresh browser context per mode so service workers, local storage, and
guest sessions cannot leak between checks:

```python
with sync_playwright() as playwright:
    for mode in ("desktop", "iphone", "standalone"):
        engine = playwright.chromium if mode == "desktop" else playwright.webkit
        device = {"viewport": {"width": 1440, "height": 1000}} if mode == "desktop" else playwright.devices["iPhone 13"]
        browser = engine.launch()
        context = browser.new_context(**device)
        if mode == "standalone":
            context.add_init_script("Object.defineProperty(navigator, 'standalone', {value:true})")
        page = context.new_page()
        # Register pageerror, console, request, requestfailed and response
        # listeners BEFORE navigating. See scripts/verify_ui_browser.py.
        page.goto(url, wait_until="domcontentloaded")
        # Wait for a visible ready-state selector or the relevant API response.
        # Click the actual controls, assert behavior, and save screenshots.
        context.close()
        browser.close()
```

Prefer `locator.wait_for`, `expect_response`, and an observable state change
over fixed sleeps. Capture the page **before and after** the interaction that
matters. For every mode, inspect screenshots yourself, including the top edge,
chat composer, tab bar and safe-area region. Screenshots are evidence to review,
not proof by their mere existence. Also inspect portrait and map overlays for
clipping and usable close controls. Check text and names at phone width; desktop
can hide overlap and wrapping problems.

Record JavaScript exceptions, `console.error`, failed requests, HTTP 4xx/5xx,
and which host receives `/api/` calls. Classify expected failures explicitly;
do not suppress all errors to make a script pass. On hosted beta, page requests
go to `storieschat.ai/beta/` while game API calls go to
`beta-api.storieschat.ai`. A successful page load with the wrong API host is a
failed check.

If a real browser check finds a bug, turn the observation into a regression
test (Node test under `tests/frontend/`, a structural Python check, or a
task-specific Playwright assertion), fix it, and repeat local verification.

## 3. PWA checks

For `sw.js`, manifest, caching or refresh changes, also run:

```powershell
& $py scripts/verify_pwa_upgrade.py --url http://127.0.0.1:8899/
```

That script installs the legacy worker, seeds stale cached script bytes, then
proves Chromium and WebKit replace them and delete the old cache. Test the
installed-app layout with standalone mode. Inspect `index.html`, `sw.js`,
`manifest.json`, `version.json`, and hashed asset URLs/Cache-Control headers.
Do not claim a physical iPhone installation was tested unless one was used.

## 4. Repeat after beta deploy

Wait until `https://beta-api.storieschat.ai/api/health` reports the pushed
commit before browser testing. Railway builds can take several minutes. The
read-only `railway deployment list --limit 1 --json` and
`railway logs <deployment-id> --build --lines 20` show build progress when
health remains old. Then run:

```powershell
& $py scripts/verify_ui_browser.py --url https://storieschat.ai/beta/ --output "$env:TEMP\storieschat-ui-qa\hosted" --expected-api-host beta-api.storieschat.ai
& $py scripts/verify_mobile_pwa_browser.py --url https://storieschat.ai/beta/ --output "$env:TEMP\storieschat-ui-qa\hosted-feature" --expected-api-host beta-api.storieschat.ai
```

Use the feature-specific script appropriate to the task and inspect the new
hosted screenshots too. Confirm the real API endpoint and frontend page
separately. Note the actual mode, engine, API host, test results, screenshot
locations, and any physical-device gap in the completion report.
