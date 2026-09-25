"""Offline iPhone WebKit reproduction of an older Home Screen install.

The old installation manifest from prod commit 76a0652 launches `/`, even if
the user originally added the icon while looking at `/beta/`. Serve that exact
committed HTML at the local root and the current beta HTML at `/beta/`, with
no public-network requests. This records the gap, keyboard, map, and UI split.

Run with a local server: python -m uvicorn backend.app.main:app --port 8898
Then: python scripts/reproduce_ios_installed_app.py --url http://127.0.0.1:8898
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


OLD_PROD_COMMIT = "76a06522f81fb67c136e03400f420359d5b92d05"
ROOT = Path(__file__).resolve().parents[1]


def committed_file(path):
    return subprocess.check_output(
        ["git", "show", f"{OLD_PROD_COMMIT}:{path}"], cwd=ROOT
    )


def expose_map_hook(html):
    closing = b'showScreen("home");\n\n})();'
    assert closing in html
    return html.replace(closing, b'window.__testSetupMapInteraction=setupMapInteraction;\n' + closing)


def inspect(page, label, output, launch_url):
    page.goto(launch_url, wait_until="domcontentloaded")
    page.locator("#screen-home").wait_for()
    page.screenshot(path=str(output / f"{label}-home.png"), full_page=True)
    initial = page.evaluate("""() => ({
      url: location.pathname,
      upload: !!document.querySelector('#chat-image-btn'),
      updateLabel: document.querySelector('#tab-update-app')?.innerText,
      navBottom: document.querySelector('#tab-bar').getBoundingClientRect().bottom,
      screenHeight: screen.height,
      viewportHeight: innerHeight,
      appHeight: getComputedStyle(document.documentElement).getPropertyValue('--app-height')
    })""")
    page.evaluate("""() => {
      document.querySelector('#screen-home').classList.remove('active');
      document.querySelector('#screen-chat').classList.add('active');
    }""")
    page.locator("#chat-text-input").focus()
    page.evaluate("""() => {
      Object.defineProperty(visualViewport, 'height', {configurable:true,get:()=>500});
      visualViewport.dispatchEvent(new Event('resize'));
    }""")
    page.wait_for_timeout(300)
    keyboard = page.evaluate("""() => ({
      keyboardClass: document.documentElement.classList.contains('keyboard-open'),
      composerBottom: document.querySelector('#chat-input-area').getBoundingClientRect().bottom,
      tabVisible: getComputedStyle(document.querySelector('#tab-bar')).display !== 'none'
    })""")
    page.screenshot(path=str(output / f"{label}-keyboard.png"), full_page=True)
    page.locator("#chat-text-input").blur()
    page.evaluate("""() => {
      Object.defineProperty(visualViewport, 'height', {configurable:true,get:()=>664});
      visualViewport.dispatchEvent(new Event('resize'));
      const modal=document.querySelector('#map-modal');
      modal.style.display='flex'; modal.classList.add('fullscreen');
      document.querySelector('#map-modal-img').style.display='block';
      window.__testSetupMapInteraction();
    }""")
    map_before = page.locator("#map-modal-close").bounding_box()
    page.locator("#map-modal-img").evaluate("""e=>{
      const touch=(type,points)=>{const ev=new Event(type,{bubbles:true,cancelable:true});
        Object.defineProperty(ev,'touches',{value:points.map(([clientX,clientY])=>({clientX,clientY}))});
        e.dispatchEvent(ev)};
      touch('touchstart',[[120,300],[220,300]]);
      touch('touchmove',[[90,300],[250,300]]);
      touch('touchend',[]);
    }""")
    zoom = page.locator("#map-modal-img").get_attribute("style") or ""
    page.screenshot(path=str(output / f"{label}-map.png"), full_page=True)
    return {"home": initial, "keyboard": keyboard,
            "map": {"closeWidth": map_before["width"], "zoomStyle": zoom}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8898")
    parser.add_argument("--output", default=str(Path(tempfile.gettempdir()) / "storieschat-ios-repro"))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    old_html = expose_map_hook(committed_file("frontend/index.html"))
    old_manifest = json.loads(committed_file("frontend/manifest.json"))
    old_worker = committed_file("frontend/sw.js").decode("utf-8")
    origin = args.url.rstrip("/")
    with urlopen(origin + "/beta/") as response:
        beta_html = expose_map_hook(response.read())
    with urlopen(origin + "/beta/manifest-beta-v2.json") as response:
        beta_manifest = json.load(response)
    assert "/beta/manifest.json" in old_worker
    assert "/beta/manifest-beta-v2.json" not in old_worker
    assert old_manifest["start_url"] == "/"
    assert beta_manifest["start_url"] == beta_manifest["scope"] == "/beta/"
    with sync_playwright() as playwright:
        browser = playwright.webkit.launch()
        results = {}
        for label, start_path in (("old_install", old_manifest["start_url"]),
                                  ("beta_install", beta_manifest["start_url"])):
            device = dict(playwright.devices["iPhone 14"])
            device["viewport"] = {"width": 390, "height": 664}
            device["screen"] = {"width": 390, "height": 844}
            context = browser.new_context(**device, service_workers="block")
            context.add_init_script("""Object.defineProperty(navigator,'standalone',{value:true});
              localStorage.setItem('storieschat_ios_install_dismissed','1');
              document.addEventListener('DOMContentLoaded',()=>{
                document.documentElement.style.setProperty('--safe-top','47px');
                document.documentElement.style.setProperty('--safe-bottom','34px');
              });""")
            context.route("**/*", lambda route: route.abort() if
                          urlsplit(route.request.url).netloc != urlsplit(origin).netloc
                          else route.continue_())
            if label == "old_install":
                context.route(origin + "/", lambda route: route.fulfill(
                    status=200, content_type="text/html", body=old_html))
                context.route(origin + "/manifest.json", lambda route: route.fulfill(
                    status=200, content_type="application/manifest+json",
                    body=json.dumps(old_manifest)))
            else:
                context.route(origin + "/beta/", lambda route: route.fulfill(
                    status=200, content_type="text/html", body=beta_html))
            page = context.new_page()
            results[label] = inspect(page, label, output, origin + start_path)
            context.close()
        browser.close()
    (output / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    old, beta = results["old_install"], results["beta_install"]
    assert old["home"]["url"] == "/" and beta["home"]["url"] == "/beta/"
    assert old["home"]["upload"] and not beta["home"]["upload"]
    assert old["home"]["screenHeight"] - old["home"]["navBottom"] >= 170
    assert abs(beta["home"]["screenHeight"] - beta["home"]["navBottom"]) < 2
    assert not old["keyboard"]["keyboardClass"] and old["keyboard"]["tabVisible"]
    assert beta["keyboard"]["keyboardClass"] and not beta["keyboard"]["tabVisible"]
    assert beta["keyboard"]["composerBottom"] <= 510
    assert old["map"]["closeWidth"] == 36 and beta["map"]["closeWidth"] >= 56
    assert "scale(1.6)" not in old["map"]["zoomStyle"]
    assert "scale(1.6)" in beta["map"]["zoomStyle"]


if __name__ == "__main__":
    main()
