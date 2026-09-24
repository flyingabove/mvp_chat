"""Baseline UI browser check in desktop Chromium and iPhone WebKit.

Run this before the feature-specific browser flow. It checks real browser
loading, records console/network evidence, and saves one viewport screenshot
per mode. It does not replace clicking through the feature being changed.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def _path(url):
    parsed = urlsplit(url)
    return f"{parsed.netloc}{parsed.path}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Local page or hosted beta URL")
    parser.add_argument("--output", required=True, help="Directory outside the repo for QA evidence")
    parser.add_argument("--wait-selector", default=".game-card", help="Visible ready-state selector")
    parser.add_argument("--expected-api-host", help="Require API requests to use this host")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results = []

    with sync_playwright() as playwright:
        for mode in ("desktop", "iphone", "standalone"):
            engine = playwright.chromium if mode == "desktop" else playwright.webkit
            browser = engine.launch()
            device = {"viewport": {"width": 1440, "height": 1000}} if mode == "desktop" else playwright.devices["iPhone 13"]
            context = browser.new_context(**device)
            context.add_init_script("localStorage.setItem('storieschat_ios_install_dismissed', '1')")
            if mode == "standalone":
                context.add_init_script("Object.defineProperty(navigator, 'standalone', {value: true})")
            page = context.new_page()
            errors, failures, http_errors, api_hosts = [], [], [], set()
            page.on("pageerror", lambda error: errors.append(f"page: {error}"))
            page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)
            page.on("request", lambda request: api_hosts.add(urlsplit(request.url).netloc) if "/api/" in urlsplit(request.url).path else None)
            page.on("requestfailed", lambda request: failures.append(_path(request.url)))
            page.on("response", lambda response: http_errors.append({"path": _path(response.url), "status": response.status}) if response.status >= 400 else None)
            try:
                page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
                page.locator(args.wait_selector).first.wait_for(state="visible", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    pass  # A polling PWA need not become idle; the ready selector is authoritative.
                page.screenshot(path=str(output / f"{mode}-home.png"))
                metrics = page.evaluate("""() => ({
                  width: innerWidth, height: innerHeight, dpr: devicePixelRatio,
                  userAgent: navigator.userAgent, standalone: navigator.standalone === true,
                  navBottom: document.querySelector('#tab-update-app')?.parentElement?.getBoundingClientRect().bottom
                })""")
                result = {
                    "mode": mode, "engine": engine.name, "url": page.url,
                    "metrics": metrics, "api_hosts": sorted(api_hosts),
                    "page_or_console_errors": errors, "failed_requests": failures,
                    "http_errors": http_errors,
                }
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                assert not errors, errors
                assert not [e for e in http_errors if "/api/" in e["path"]], http_errors
                assert not [path for path in failures if "/api/" in path], failures
                if args.expected_api_host:
                    assert api_hosts == {args.expected_api_host}, api_hosts
                assert metrics["navBottom"] is not None and abs(metrics["navBottom"] - metrics["height"]) < 2, metrics
            except Exception:
                page.screenshot(path=str(output / f"{mode}-failure.png"))
                raise
            finally:
                context.close()
                browser.close()

    (output / "report.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
