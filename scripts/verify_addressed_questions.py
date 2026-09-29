"""Play a short guest game and show how addressed questions are handled.

Starts a story, asks one present character two questions in one message, then
sends a neutral follow-up. Prints every reply so a human can judge whether the
addressee answered both. With --db (local server only), also prints the
engine's tracked questions from the saved session. Makes real model calls.
"""
import argparse
import json
import sqlite3
import sys
import uuid

import httpx


def speakers(reply: dict) -> list[str]:
    return [s.get("speaker_id") for s in reply.get("segments") or [] if s.get("kind") == "dialogue"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8899")
    parser.add_argument("--story", default="six_strangers")
    parser.add_argument("--db", help="Local SQLite path to read tracked questions from")
    parser.add_argument("--first", required=True, help="Message with two questions to one character")
    parser.add_argument("--second", default="Hmm, okay.")
    args = parser.parse_args()

    headers = {"X-Guest-Id": str(uuid.uuid4())}
    session_id = "questions-check-" + uuid.uuid4().hex[:12]
    with httpx.Client(base_url=args.api, timeout=180) as client:
        def post(message):
            r = client.post("/api/chat", headers=headers, json={
                "session_id": session_id, "message": message, "request_id": uuid.uuid4().hex})
            r.raise_for_status()
            return r.json()

        opening = post(f"__cmd_newgame__:{args.story}|M|Question Tester")
        present = [s for s in speakers(opening) if s and s != "unknown"]
        print("OPENING SPEAKERS:", present)
        greeter = present[0].replace("_", " ").title() if present else ""
        first = args.first.replace("{greeter}", greeter)
        for label, message in (("TURN 1", first), ("TURN 2", args.second)):
            reply = post(message)
            print(f"\n=== {label}: {message}\nSPEAKERS: {speakers(reply)}\n{reply.get('reply')}")
            if args.db:
                conn = sqlite3.connect(args.db)
                row = conn.execute("SELECT state_json FROM game_sessions WHERE id = ?", (session_id,)).fetchone()
                conn.close()
                convo = json.loads(row[0]).get("world_model", {}).get("conversation", {})
                print("TRACKED:", json.dumps(convo.get("questions", []), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
