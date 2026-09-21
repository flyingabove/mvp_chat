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


def test_map_modal_uses_metadata_and_versioned_artwork():
    html = (Path(__file__).resolve().parents[2] / "frontend/index.html").read_text(
        encoding="utf-8"
    )
    assert "new WorldMapView(atlasHost, meta.world_map" in html
    assert 'encodeURIComponent(meta.world_map_image_revision || "")' in html
    assert '<script src="world-map.js?v=1"></script>' in html
    assert '<link rel="stylesheet" href="world-map.css?v=1">' in html
