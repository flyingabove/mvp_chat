"""Check the goal pill and ending card in desktop Chromium, iPhone WebKit and
simulated standalone WebKit.

The new game and its goal come from the real server. The ending reply is
supplied by route interception (reaching a real ending needs a long
playthrough), so this proves rendering and input locking, not gameplay.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ENDING = {"reply": "They walk out together.\n\nEND GAME YOU WIN -- turns: 42",
          "segments": [{"kind": "narration", "text": "They walk out together."}],
          "ending": {"id": "left_together", "kind": "win", "label": "You won", "title": "You left together",
                     "summary": "You and Mako both chose to leave the house together.", "turns": 42,
                     "ends_run": True},
          "character": "default"}


def check(p, mode, args, output):
    browser = (p.chromium if mode == "desktop" else p.webkit).launch()
    device = {"viewport": {"width": 1440, "height": 1000}} if mode == "desktop" else dict(p.devices["iPhone 13"])
    context = browser.new_context(**device, service_workers="block")
    context.add_init_script("localStorage.setItem('storieschat_ios_install_dismissed','1');")
    if mode == "standalone":
        context.add_init_script("Object.defineProperty(navigator, 'standalone', {value:true});")
    page = context.new_page()
    errors, hosts = [], set()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
    page.on("request", lambda r: hosts.add(urlsplit(r.url).netloc) if "/api/" in urlsplit(r.url).path else None)
    result = {"mode": mode}
    try:
        page.goto(args.url, wait_until="networkidle")
        page.locator("#home-guest-pill").click()
        page.locator(".game-card").filter(has_text=args.story_title).first.click()
        page.locator("#modal-play-btn").click()
        if page.locator("#onboard-continue-btn").count():
            page.locator("#onboard-continue-btn").click()
            page.wait_for_selector("#briefing-start-btn", state="visible", timeout=10000)  # BL-49 briefing
            page.locator("#briefing-start-btn").click()
        page.locator("#chat-messages .msg-bubble.npc").first.wait_for(timeout=120000)
        pill = page.locator("#chat-goal-pill")
        pill.wait_for(state="visible", timeout=10000)
        result["goal_status"] = page.locator("#chat-goal-status").inner_text()
        pill.click()
        result["goal_text_visible"] = page.locator("#chat-goal-text").is_visible()
        page.screenshot(path=str(output / f"{mode}-goal.png"))

        page.route("**/api/chat", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(ENDING)))
        page.locator("#chat-text-input").fill("Let's go.")
        page.locator("#chat-send-btn").click()
        card = page.locator(".ending-card")
        card.wait_for(timeout=20000)
        result["card_text"] = card.inner_text()
        result["input_disabled"] = page.locator("#chat-text-input").is_disabled()
        result["send_disabled"] = page.locator("#chat-send-btn").is_disabled()
        card.scroll_into_view_if_needed()
        page.screenshot(path=str(output / f"{mode}-ending.png"))
        page.locator(".ending-home-btn").click()
        result["left_chat"] = page.locator("#screen-home").evaluate("e => e.classList.contains('active')") \
            and not page.locator("#screen-chat").evaluate("e => e.classList.contains('active')")
        result["errors"] = errors
        result["api_hosts"] = sorted(hosts)
        result["ok"] = bool(result["goal_status"] and result["goal_text_visible"]
                            and "You left together" in result["card_text"] and "you won" in result["card_text"].lower()
                            and result["input_disabled"] and result["send_disabled"] and result["left_chat"]
                            and not errors
                            and (not args.expected_api_host or hosts == {args.expected_api_host}))
        return result
    finally:
        context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8899/")
    parser.add_argument("--story-title", default="Terrace in the City")
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-api-host")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        results = [check(p, mode, args, output) for mode in ("desktop", "iphone", "standalone")]
    (output / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
