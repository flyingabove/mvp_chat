"""Exercise the real map UI in desktop Chromium and iPhone WebKit.

Requires the optional Playwright package and its chromium/webkit browsers in the
storieschat environment. Results are written to a caller-selected directory.
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8899/")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        for mode in ("desktop", "iphone"):
            browser = (
                playwright.chromium if mode == "desktop" else playwright.webkit
            ).launch()
            context = browser.new_context(
                **(
                    {"viewport": {"width": 1440, "height": 1000}}
                    if mode == "desktop"
                    else playwright.devices["iPhone 13"]
                )
            )
            page = context.new_page()
            errors, requests, failed = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: (
                    requests.append(request.url) if "/api/" in request.url else None
                ),
            )
            page.on(
                "response",
                lambda response: (
                    failed.append({"url": response.url, "status": response.status})
                    if response.status >= 400
                    else None
                ),
            )
            try:
                page.goto(args.url, wait_until="networkidle")
                if mode == "iphone":
                    page.locator("#ios-install-dismiss").click()
                page.locator("#home-guest-pill").click()
                page.locator(".game-card").filter(
                    has_text="Terrace in the City"
                ).first.click()
                page.locator("#modal-play-btn").click()
                with page.expect_response(
                    lambda response: "/api/story/six_strangers" in response.url
                ):
                    page.locator("#onboard-continue-btn").click()
                page.locator("#chat-menu-btn").click()
                page.locator("#dd-map").click()
                host = page.locator(".atlas-host")
                host.wait_for(state="visible")
                page.wait_for_function(
                    "document.querySelector('.atlas-stage img')?.naturalWidth > 0"
                )
                assert page.locator(".atlas-place").count() == 103
                page.screenshot(path=str(output / f"{mode}-artwork.png"))
                host.get_by_role("button", name="Regions", exact=True).click()
                assert page.locator(".atlas-marker").count() == 14
                host.get_by_role("button", name="Nearby", exact=True).click()
                host.get_by_label("Filter locations by region").select_option(
                    "yokohama"
                )
                assert page.locator(".atlas-place").count() == 5
                host.get_by_label("Search map locations").fill("E49")
                assert page.locator(".atlas-place").count() == 1
                page.locator(".atlas-place").click()
                assert "estimated travel" in page.locator(".atlas-detail").inner_text()
                assert "Factory" in page.locator(".atlas-detail h3").inner_text()
                page.screenshot(path=str(output / f"{mode}-route.png"))
                host.get_by_role("button", name="Interiors", exact=True).click()
                assert page.locator(".atlas-marker").count() == 19
                host.get_by_role("button", name="Swimming Pool", exact=True).click()
                assert "H15, O13" in page.locator(".atlas-detail").inner_text()
                page.screenshot(path=str(output / f"{mode}-interiors.png"))
                # Verify artwork can be reopened and the enlarged viewer scrolls.
                host.get_by_role("button", name="Artwork", exact=True).click()
                host.get_by_role("button", name="Enlarge artwork", exact=True).click()
                assert page.locator(".atlas-stage.enlarged").count() == 1
                host.get_by_role("button", name="Fit artwork", exact=True).click()
                page.locator("#map-modal-close").click()
                page.locator("#chat-menu-btn").click()
                page.locator("#dd-map").click()
                assert page.locator(".atlas-host").count() == 1
                assert not errors, errors
                map_failures = [
                    r
                    for r in failed
                    if "world-map" in r["url"] or "story-image" in r["url"]
                ]
                assert not map_failures, map_failures
                results.append(
                    {
                        "mode": mode,
                        "passed": True,
                        "page_errors": errors,
                        "api_hosts": sorted({url.split("/")[2] for url in requests}),
                        "failed_responses": failed,
                    }
                )
            finally:
                browser.close()
    (output / "result.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
