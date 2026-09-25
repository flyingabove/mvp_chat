"""Prove an installed legacy worker releases stale fixed-name assets on update."""
import argparse
import subprocess
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8899/')
args = parser.parse_args()
legacy_commit = '76a06522f81fb67c136e03400f420359d5b92d05'
legacy = subprocess.check_output(['git', 'show', f'{legacy_commit}:frontend/sw.js']).decode()
legacy_manifest = subprocess.check_output(['git', 'show', f'{legacy_commit}:frontend/manifest.json'])
current = urllib.request.urlopen(args.url.rstrip('/') + '/sw.js').read().decode()
new_beta_manifest = urllib.request.urlopen(args.url.rstrip('/') + '/beta/manifest-beta-v2.json').read()
state = {'upgraded': False}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.split('?')[0] in ('/sw.js', '/beta/sw.js'):
            body = (current if state['upgraded'] else legacy).encode()
            mime = 'application/javascript'
        elif self.path.split('?')[0] in ('/manifest.json', '/beta/manifest.json'):
            body = legacy_manifest
            mime = 'application/manifest+json'
        elif self.path.split('?')[0] == '/beta/manifest-beta-v2.json':
            body = new_beta_manifest
            mime = 'application/manifest+json'
        else:
            body = b'<html><body>Upgrade test</body></html>'
            mime = 'text/html'
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        for engine in (p.chromium, p.webkit):
            state['upgraded'] = False
            browser = engine.launch()
            page = browser.new_page()
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.evaluate("async()=>{await navigator.serviceWorker.register('/sw.js');await navigator.serviceWorker.ready;}")
            page.wait_for_function('navigator.serviceWorker.controller')
            page.evaluate("async()=>{const c=await caches.open('storieschat-v5');await c.put('/dialogue.js?v=3',new Response('STALE'));}")
            assert page.evaluate("async()=>await (await fetch('/dialogue.js?v=3')).text()") == 'STALE'
            # The old root worker cached a beta manifest whose start_url was
            # '/', so re-adding from beta could still launch production.
            assert page.evaluate("async()=>await (await fetch('/beta/manifest.json')).json().then(m=>m.start_url)") == '/'
            # The distinct beta URL bypasses that old cache, even before the
            # new beta worker installs.
            assert page.evaluate("async()=>await (await fetch('/beta/manifest-beta-v2.json')).json().then(m=>m.start_url)") == '/beta/'
            state['upgraded'] = True
            page.evaluate("async()=>{await (await navigator.serviceWorker.getRegistration()).update();}")
            page.wait_for_function("async()=>!(await caches.keys()).includes('storieschat-v5')")
            assert page.evaluate("async()=>await (await fetch('/dialogue.js?v=3')).text()") != 'STALE'
            print(engine.name + ': stale asset replaced and legacy cache deleted', flush=True)
            browser.close()
finally:
    server.shutdown()
