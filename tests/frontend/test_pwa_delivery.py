import re

from fastapi.testclient import TestClient
from backend.app.main import app


def test_shell_assets_are_versioned_and_never_stale():
    client = TestClient(app)
    for prefix in ('', '/beta'):
        page = client.get(prefix + '/')
        assert 'no-store' in page.headers.get('cache-control', '')
        assets = re.findall(r'(?:src|href)="(assets/[^\"]+\.(?:js|css))"', page.text)
        assert len(assets) == 4
        for asset in assets:
            assert re.search(r'\.[a-f0-9]{16}\.(js|css)$', asset)
            assert client.get(prefix + '/' + asset).status_code == 200
        for name in ('sw.js', 'version.json', 'manifest.json', 'dialogue.js'):
            assert 'no-store' in client.get(prefix + '/' + name).headers.get('cache-control', '')


def test_beta_install_stays_on_beta():
    client = TestClient(app)
    manifest = client.get('/beta/manifest.json').json()
    assert manifest['start_url'] == '/beta/'
    assert manifest['scope'] == '/beta/'
    assert manifest['id'] == '/beta/'


def test_beta_install_bypasses_legacy_root_worker_manifest_cache():
    client = TestClient(app)
    page = client.get('/beta/').text
    assert 'rel="manifest" href="manifest-beta-v2.json"' in page
    assert 'apple-mobile-web-app-title" content="StoriesChat Beta"' in page
    assert 'StoriesChat <small class="beta-badge">Beta</small>' in page
    response = client.get('/beta/manifest-beta-v2.json')
    assert response.status_code == 200
    assert 'no-store' in response.headers.get('cache-control', '')
    manifest = response.json()
    assert manifest['name'] == 'StoriesChat Beta'
    assert manifest['short_name'] == 'StoriesChat Beta'
    assert manifest['start_url'] == manifest['scope'] == manifest['id'] == '/beta/'
    assert 'manifest-beta-v2.json' not in client.get('/').text


def test_worker_contains_current_shell_revision():
    client = TestClient(app)
    worker = client.get('/beta/sw.js').text
    assert '__SHELL_REVISION__' not in worker
    assert 'storieschat-' in worker


def test_editing_an_asset_changes_both_its_url_and_worker_revision(tmp_path, monkeypatch):
    from backend.app import main
    for name in ('index.html', 'sw.js', 'manifest.json', *main._SHELL_ASSETS):
        (tmp_path / name).write_bytes((main._INDEX_HTML_PATH.parent / name).read_bytes())
    monkeypatch.setattr(main, '_INDEX_HTML_PATH', tmp_path / 'index.html')
    old_url, old_revision = main._asset_name('dialogue.js'), main._shell_revision()
    asset = tmp_path / 'dialogue.js'
    asset.write_text(asset.read_text(encoding='utf-8') + '\n// next deployment', encoding='utf-8')
    assert main._asset_name('dialogue.js') != old_url
    assert main._shell_revision() != old_revision
