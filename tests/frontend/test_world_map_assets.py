from pathlib import Path

from fastapi.testclient import TestClient
from backend.app.main import app


def test_map_assets_are_served_for_both_frontend_prefixes():
    client = TestClient(app)
    for prefix in ("", "/beta"):
        script = client.get(prefix + "/world-map.js")
        assert script.status_code == 200
        assert "class WorldMapView" in script.text
        style = client.get(prefix + "/world-map.css")
        assert style.status_code == 200
        assert ".atlas-host" in style.text


def test_map_appears_inline_and_opens_full_screen_without_location_dump():
    html = (Path(__file__).resolve().parents[2] / "frontend/index.html").read_text(
        encoding="utf-8"
    )
    assert html.count("renderInlineWorldMap(meta);") == 2
    inline_map = html.split("function renderInlineWorldMap(meta){", 1)[1].split(
        "function addDebugBox", 1
    )[0]
    assert 'imgWrap.addEventListener("click", showMapModal);' in inline_map
    assert "known_locations" not in inline_map
    assert "loc.description" not in inline_map
    assert 'modal.classList.add("fullscreen")' in html
    assert "map-modal-locations" not in html
    assert 'encodeURIComponent(meta.world_map_image_revision || "")' in html
    assert '<script src="world-map.js?v=1"></script>' in html
    assert '<link rel="stylesheet" href="world-map.css?v=1">' in html


def test_worker_update_does_not_race_initial_install_or_reject_unhandled():
    html = (Path(__file__).resolve().parents[2] / "frontend/index.html").read_text(encoding="utf-8")
    block = html.split('navigator.serviceWorker.register("sw.js")', 1)[1].split('navigator.serviceWorker.addEventListener', 1)[0]
    assert "if (reg.active && !reg.installing)" in block
    assert "reg.update().catch(" in block
