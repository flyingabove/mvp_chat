"""
Regression coverage for BL-03: frontend/index.html must not silently call the
PROD api when the page is loaded from storieschat.ai/beta/.

There is no JS test harness in this repo (confirmed during the A06 fix), so
this is a structural/string-level guard on frontend/index.html rather than a
real browser test. It exists to stop this specific bug from being
reintroduced, not to fully exercise the JS. See documentation/BACKLOG.md
BL-03 and documentation/model_output_docs/INFRASTRUCTURE.md for the routing
context this depends on (Cloudflare only routes /beta/* PAGE requests to the
beta origin, not a same-origin /api call issued by that page).
"""
from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _read_index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_backend_origin_is_beta_aware():
    """API_BASE/AUTH_BASE must be derived from a beta-aware BACKEND_ORIGIN,
    not a bare window.location.origin, so a page served from
    storieschat.ai/beta/ talks to beta-api.storieschat.ai instead of prod."""
    html = _read_index_html()

    assert "var BACKEND_ORIGIN" in html, (
        "Expected a BACKEND_ORIGIN variable computing the beta-aware API "
        "host; if this was renamed/removed, re-verify BL-03 isn't back."
    )
    assert '"https://beta-api.storieschat.ai"' in html

    # API_BASE/AUTH_BASE must be derived from BACKEND_ORIGIN, not straight
    # from window.location.origin (that was the original bug).
    assert 'var API_BASE    = BACKEND_ORIGIN + "/api";' in html or \
        "var API_BASE = BACKEND_ORIGIN + \"/api\";" in html
    assert "var AUTH_BASE   = BACKEND_ORIGIN;" in html or \
        "var AUTH_BASE = BACKEND_ORIGIN;" in html


def test_stories_fallback_does_not_hardcode_prod_url():
    """getStoriesEndpointCandidates()'s fallback previously hardcoded
    https://storieschat.ai/api/stories unconditionally, which would silently
    re-route a failed beta fetch to prod. The fallback must now be derived
    from BACKEND_ORIGIN so it stays in the same environment."""
    html = _read_index_html()
    start = html.index("function getStoriesEndpointCandidates")
    end = html.index("\n}", start)
    fn_body = html[start:end]

    assert '"https://storieschat.ai/api/stories"' not in fn_body, (
        "getStoriesEndpointCandidates() must not hardcode the prod URL as "
        "its canonical fallback — that silently defeats BACKEND_ORIGIN's "
        "beta detection whenever the primary candidate fails (BL-03)."
    )
    assert "BACKEND_ORIGIN" in fn_body
