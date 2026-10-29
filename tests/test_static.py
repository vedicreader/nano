'Static files: every real asset is served, and nothing outside static/ is reachable through a traversal URL.'
import pytest
from pathlib import Path
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
ASSETS = sorted(p.relative_to(ROOT / 'static').as_posix() for p in (ROOT / 'static').rglob('*') if p.is_file() and not p.name.startswith('.'))

@pytest.fixture
def client(monkeypatch):
    monkeypatch.chdir(ROOT)   # the app's static dirs are relative to the repo root
    import nano.app as m
    return TestClient(m.nano)

# nano/core/theme.css is source outside static/ with an extension fast_app's catch-all ({ext:static}) served from the app root
PROBES = ['/static/%2e%2e/nano/core/theme.css', '/static/%2E%2E/nano/core/theme.js', '/static/..%2fnano/core/theme.css',
          '/static/%2e%2e%2fnano%2fcore%2ftheme.css', '/static/svg/%2e%2e/%2e%2e/nano/core/theme.css', '/nano/core/theme.css',
          '/%2e%2e/nano/nano/core/theme.css', '/static/vendor/%2e%2e/%2e%2e/nano/core/theme.css']

@pytest.mark.parametrize('url', PROBES)
def test_traversal_outside_static_refused(client, url):
    r = client.get(url, follow_redirects=False)
    assert r.status_code != 200, f'{url} served {r.text[:80]!r}'

def test_traversal_outside_repo_refused(client, tmp_path):
    'An encoded ../ chain from static/ to a probe file outside the repo.'
    probe = tmp_path / 'probe.txt'; probe.write_text('secret')
    up = '%2e%2e/' * (len((ROOT / 'static').parts) - 1)
    r = client.get('/static/' + up + probe.as_posix().lstrip('/'), follow_redirects=False)
    assert r.status_code != 200, r.text[:80]

def test_catch_all_removed():
    import nano.app as m
    assert not [r for r in m.nano.router.routes if getattr(r, 'path', '') == '/{fname:path}.{ext:static}']

@pytest.mark.parametrize('nm', ASSETS)
def test_real_asset_served(client, nm):
    r = client.get(f'/static/{nm}')
    assert r.status_code == 200 and r.content == (ROOT / 'static' / nm).read_bytes()

def test_linked_assets_served(client):
    'Every /static/ URL the home page links (favicons, vendor, generated theme assets) resolves.'
    import re
    html = client.get('/').text
    urls = sorted(set(u.split('?')[0] for u in re.findall(r'(?:href|src|content)="(/static/[^"]+)"', html)))
    assert urls, 'home page links no /static/ asset'
    bad = [(u, client.get(u).status_code) for u in urls if client.get(u).status_code != 200]
    assert not bad, bad
