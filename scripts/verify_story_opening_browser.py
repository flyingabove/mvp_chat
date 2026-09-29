"""Open a story as a guest and check its authored opening renders cleanly.

Runs desktop Chromium, iPhone WebKit and simulated standalone WebKit. Fails if
the raw /api/chat reply or the rendered opener contains a literal backslash
escape or a U+FFFD replacement character, and saves one screenshot per mode.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

BACKSLASH = chr(92)


def check_mode(p, mode, args, output):
    browser = (p.chromium if mode == "desktop" else p.webkit).launch()
    device = {"viewport": {"width": 1440, "height": 1000}} if mode == "desktop" else dict(p.devices["iPhone 13"])
    context = browser.new_context(**device)
    context.add_init_script("localStorage.setItem('storieschat_ios_install_dismissed','1');")
    if mode == "standalone":
        context.add_init_script("Object.defineProperty(navigator, 'standalone', {value:true});")
    page = context.new_page()
    errors, hosts, chat_bodies = [], set(), []
    page.on("response", lambda r: chat_bodies.append(r) if urlsplit(r.url).path.endswith("/api/chat") else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
    page.on("request", lambda r: hosts.add(urlsplit(r.url).netloc) if "/api/" in urlsplit(r.url).path else None)
    try:
        page.goto(args.url, wait_until="networkidle")
        page.locator("#home-guest-pill").click()
        page.locator(".game-card").filter(has_text=args.story_title).first.click()
        page.locator("#modal-play-btn").click()
        if page.locator("#onboard-continue-btn").count():
            page.locator("#onboard-continue-btn").click()
        opener = page.locator("#chat-messages .msg-bubble.npc").first
        opener.wait_for(timeout=120000)
        page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
        text = opener.inner_text()
        opener.evaluate("e=>e.scrollIntoView({block:'start'})")
        page.screenshot(path=str(output / f"{mode}-opening.png"))
        # The UI unescapes literal "\n" itself, so the raw API body is where an
        # authored double-escape stays visible (history, previews, debug).
        raw = "".join(r.text() for r in chat_bodies)
        result = {
            "raw_api_literal_escapes": raw.count(BACKSLASH * 2 + "n"),
            "raw_api_replacement_chars": raw.count("�") + raw.lower().count(BACKSLASH + "ufffd"),
            "mode": mode,
            "chars": len(text),
            "literal_escapes": text.count(BACKSLASH + "n") + text.count(BACKSLASH + "t"),
            "replacement_chars": text.count("�"),
            "paragraph_breaks": text.count("\n"),
            "api_hosts": sorted(hosts),
            "errors": errors,
        }
        if args.check_first_arrival:
            first_ids = {segment.get("speaker_id") for segment in chat_bodies[-1].json().get("segments", [])
                         if segment.get("kind") == "dialogue" and segment.get("speaker_id")}
            assert len(first_ids) == 1, f"expected one first resident, saw {first_ids}"
            arrival_response = None
            for line in ("Hi, I'm Chris. It feels strange being the first two here.",
                         "What made you want to come to this house?"):
                page.locator("#chat-text-input").fill(line)
                with page.expect_response(lambda r: urlsplit(r.url).path.endswith("/api/chat")
                                          and r.request.method == "POST", timeout=120000) as pending:
                    page.locator("#chat-send-btn").click()
                arrival_response = pending.value.json()
                assert "error" not in arrival_response, arrival_response.get("error")
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
            arrived_ids = [segment.get("speaker_id") for segment in arrival_response.get("segments", [])
                           if segment.get("kind") == "dialogue" and segment.get("speaker_id") not in first_ids]
            result["first_resident_ids"] = sorted(first_ids)
            result["arrived_ids"] = arrived_ids
            result["first_arrival_visible"] = len(arrived_ids) == 1
            page.locator("#chat-messages .msg-bubble.npc").last.evaluate("e=>e.scrollIntoView({block:'end'})")
            page.screenshot(path=str(output / f"{mode}-first-arrival.png"))
        ok = (
            bool(chat_bodies)
            and result["raw_api_literal_escapes"] == 0
            and result["raw_api_replacement_chars"] == 0
            and result["literal_escapes"] == 0
            and result["replacement_chars"] == 0
            and result["paragraph_breaks"] > 0
            and not errors
            and (not args.expected_api_host or hosts == {args.expected_api_host})
            and (not args.check_first_arrival or result["first_arrival_visible"])
        )
        result["ok"] = ok
        return result
    finally:
        context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8899/")
    parser.add_argument("--story-title", required=True, help="Visible text on the story's game card")
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-api-host")
    parser.add_argument("--check-first-arrival", action="store_true",
                        help="Send two real Terrace turns and verify a newly arrived resident speaks")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        results = [check_mode(p, mode, args, output) for mode in ("desktop", "iphone", "standalone")]
    (output / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
