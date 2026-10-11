"""Play scripted turns as a guest and print every reply for human review.

Each --turn is one player message; "{greeter}" becomes the first character who
spoke in the opening. With --db (local server only) it also prints the saved
world-model fields named by --field after each turn. Makes real model calls.
"""
import argparse
import json
import sqlite3
import sys
import uuid

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8899")
    parser.add_argument("--story", default="six_strangers")
    parser.add_argument("--player", default="Paul")
    parser.add_argument("--gender", default="M")
    parser.add_argument("--turn", action="append", required=True)
    parser.add_argument("--db")
    parser.add_argument("--field", action="append", default=[])
    args = parser.parse_args()

    headers = {"X-Guest-Id": str(uuid.uuid4())}
    session_id = "play-" + uuid.uuid4().hex[:12]
    with httpx.Client(base_url=args.api, timeout=180) as client:
        def post(message):
            r = client.post("/api/chat", headers=headers, json={
                "session_id": session_id, "message": message, "request_id": uuid.uuid4().hex})
            r.raise_for_status()
            return r.json()

        opening = post(f"__cmd_newgame__:{args.story}|{args.gender}|{args.player}")
        spoke = [s.get("speaker_id") for s in opening.get("segments") or []
                 if s.get("kind") == "dialogue" and s.get("speaker_id") not in (None, "unknown")]
        greeter = spoke[0].replace("_", " ").title() if spoke else ""
        print(f"SESSION {session_id}\nOPENING SPEAKERS {spoke}")
        for index, message in enumerate(args.turn, 1):
            message = message.replace("{greeter}", greeter)
            reply = post(message)
            print(f"\n=== TURN {index}: {message}\n{reply.get('reply')}")
            if args.db and args.field:
                conn = sqlite3.connect(args.db)
                row = conn.execute("SELECT state_json FROM game_sessions WHERE id = ?", (session_id,)).fetchone()
                conn.close()
                world = json.loads(row[0]).get("world_model") or {}
                print("STATE:", json.dumps({f: world.get(f) for f in args.field}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
