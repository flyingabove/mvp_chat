"""
Structural regression coverage for the "hard reload" button on the home
top-bar. iOS "Add to Home Screen" installs cache the service worker and
static assets aggressively; this button lets a user force-refresh the
installed webapp without deleting and re-adding it.

There is no JS test harness in this repo (see test_beta_api_base.py), so
this is a structural/string-level guard on frontend/index.html rather than a
real browser test — it asserts the button exists, is reachable pre-login,
and that the handler actually clears both the service worker registration
and CacheStorage (not just one), which is what makes it an effective cache
buster rather than a no-op reload.
"""
from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _read_index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_hard_reload_button_present_on_home_topbar():
    html = _read_index_html()
    assert 'id="home-hard-reload-btn"' in html
    # Must live inside the home screen top-bar, which renders before login
    # (no auth gate around #screen-home).
    home_screen_start = html.index('id="screen-home"')
    top_bar_end = html.index("</div>", html.index('class="top-actions"'))
    assert home_screen_start < html.index('id="home-hard-reload-btn"') < top_bar_end


def test_hard_reload_handler_clears_service_worker_and_cache_storage():
    html = _read_index_html()
    assert "function hardReloadApp" in html
    start = html.index("function hardReloadApp")
    end = html.index("\n}", start)
    fn_body = html[start:end]

    assert "getRegistrations" in fn_body and "unregister" in fn_body, (
        "hardReloadApp() must unregister existing service worker "
        "registrations, or a stale SW keeps intercepting fetches after reload."
    )
    assert "caches.keys" in fn_body and "caches.delete" in fn_body, (
        "hardReloadApp() must clear CacheStorage entries, or the PWA shell "
        "cache from sw.js survives the 'hard' reload."
    )
    assert "location.replace" in fn_body or "location.reload" in fn_body, (
        "hardReloadApp() must actually navigate/reload after clearing caches."
    )


def test_update_app_tab_reuses_the_cache_busting_hard_reload_action():
    html = _read_index_html()
    assert 'id="tab-update-app"' in html
    assert ">Refresh Cache<" in html
    assert 'data-action="hard-reload"' in html
    assert 'this.dataset.action === "hard-reload"' in html
    assert "hardReloadApp();" in html


def test_refresh_cache_clears_saved_browser_state_too():
    html = _read_index_html()
    start = html.index("function hardReloadApp")
    end = html.index("/* ─── iOS INSTALL PROMPT", start)
    fn_body = html[start:end]
    assert "localStorage.clear()" in fn_body
    assert "sessionStorage.clear()" in fn_body
    assert "indexedDB.databases()" in fn_body
    assert "document.cookie" in fn_body


def test_text_speed_has_slower_normal_fast_and_instant():
    html = _read_index_html()
    assert 'id="typewriter-speed" min="0" max="2"' in html
    assert 'var TYPEWRITER_SPEEDS = [4 / 0.6, (10 / 3.5) / 0.7, 0];' in html
    assert 'var TYPEWRITER_LABELS = ["Normal", "Fast", "Instant"];' in html
