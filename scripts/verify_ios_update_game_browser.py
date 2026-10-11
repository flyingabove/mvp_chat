"""Exercise an update mismatch while actually playing a guest game in WebKit."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-api-host", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        for mode in ("desktop", "iphone", "standalone"):
            browser = (playwright.chromium if mode == "desktop" else playwright.webkit).launch()
            device = {"viewport": {"width": 1440, "height": 1000}} if mode == "desktop" else dict(playwright.devices["iPhone 13"])
            context = browser.new_context(**device)
            context.add_init_script("localStorage.setItem('storieschat_ios_install_dismissed','1')")
            if mode == "standalone":
                context.add_init_script("Object.defineProperty(navigator, 'standalone', {value:true})")
            page = context.new_page()
            navigations, errors, api_hosts, failed_api, http_api_errors = [], [], set(), [], []
            page.on("framenavigated", lambda frame: navigations.append(frame.url) if frame == page.main_frame else None)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.on("request", lambda request: api_hosts.add(urlsplit(request.url).netloc) if "/api/" in urlsplit(request.url).path else None)
            page.on("requestfailed", lambda request: failed_api.append(request.url) if "/api/" in urlsplit(request.url).path else None)
            page.on("response", lambda response: http_api_errors.append((response.status, response.url)) if "/api/" in urlsplit(response.url).path and response.status >= 400 else None)
            page.route("**/version.json", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"shell_revision": "simulated-new-revision"})))
            try:
                page.goto(args.url, wait_until="domcontentloaded")
                page.locator("#tab-update-app[data-update-ready='true']").wait_for(timeout=15000)
                for _ in range(5):
                    page.evaluate("window.dispatchEvent(new Event('pageshow'))")
                page.evaluate("navigator.serviceWorker.dispatchEvent(new Event('controllerchange'))")
                page.wait_for_timeout(1200)
                assert len(navigations) == 1, f"update detection navigated {len(navigations)} times"
                page.screenshot(path=str(output / f"{mode}-update-notice.png"))

                page.locator("#home-guest-pill").click()
                page.locator(".game-card").filter(has_text="Terrace in the City").first.click()
                page.locator("#modal-play-btn").click()
                page.locator("#onboard-continue-btn").click()
                page.locator("#briefing-start-btn").click()
                page.locator("#chat-messages .msg-bubble.npc").first.wait_for(timeout=120000)
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
                opening = page.locator("#chat-messages .msg-bubble.npc").first.inner_text()
                assert opening.strip(), "game opening is empty"
                page.screenshot(path=str(output / f"{mode}-opening.png"))

                prior = page.locator("#chat-messages .msg-bubble.npc").count()
                page.locator("#chat-text-input").fill("Hi, I'm Alex. What is your name?")
                with page.expect_response(lambda response: "/api/chat" in response.url, timeout=180000) as turn:
                    page.locator("#chat-send-btn").click()
                assert turn.value.status == 200, f"game turn HTTP {turn.value.status}"
                page.wait_for_function("count => document.querySelectorAll('#chat-messages .msg-bubble.npc').length > count", arg=prior, timeout=120000)
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
                reply = page.locator("#chat-messages .msg-bubble.npc").last.inner_text()
                assert reply.strip(), "game reply is empty"
                page.screenshot(path=str(output / f"{mode}-reply.png"))
                assert len(navigations) == 1, f"gameplay navigated {len(navigations)} times"
                assert api_hosts == {args.expected_api_host}, api_hosts
                assert not errors and not failed_api and not http_api_errors, (errors, failed_api, http_api_errors)
                result = {"mode": mode, "engine": "chromium" if mode == "desktop" else "webkit", "navigations": len(navigations), "api_hosts": sorted(api_hosts), "opening_excerpt": opening[:160], "reply_excerpt": reply[:250], "errors": errors}
                print(json.dumps(result, ensure_ascii=False), flush=True)
                (output / f"{mode}-report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            finally:
                context.close()
                browser.close()


if __name__ == "__main__":
    main()
