"""Exercise durable per-request turn receipts against a running server.

Plays a short guest game and checks that retries replay the committed reply
without advancing the turn, and that a reused request_id with different text
is rejected. Makes real story-model calls for the two gameplay turns.
"""
import argparse
import json
import sys
import uuid

import httpx

STORY_ID = "iu_murder_mystery"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8899", help="API origin, e.g. https://beta-api.storieschat.ai")
    parser.add_argument("--story", default=STORY_ID)
    args = parser.parse_args()

    headers = {"X-Guest-Id": str(uuid.uuid4())}
    session_id = "receipt-check-" + uuid.uuid4().hex[:12]
    checks = []

    def post(message, request_id):
        return client.post("/api/chat", headers=headers,
                           json={"session_id": session_id, "message": message, "request_id": request_id})

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    with httpx.Client(base_url=args.api, timeout=180) as client:
        newgame = f"__cmd_newgame__:{args.story}|F|Receipt Tester"
        first_game = post(newgame, "ng-1")
        check("new game 200", first_game.status_code == 200, first_game.status_code)
        retry_game = post(newgame, "ng-1")
        check("new game retry replays same opening",
              retry_game.status_code == 200 and retry_game.json() == first_game.json())

        turn1 = post("I look around the apartment.", "turn-1")
        check("turn 1 200", turn1.status_code == 200, turn1.text[:200] if turn1.status_code != 200 else "")
        turn2 = post("I check my phone for the time.", "turn-2")
        check("turn 2 200", turn2.status_code == 200, turn2.text[:200] if turn2.status_code != 200 else "")

        retry1 = post("I look around the apartment.", "turn-1")
        check("older request retry replays exact reply",
              retry1.status_code == 200 and retry1.json() == turn1.json())
        retry2 = post("I check my phone for the time.", "turn-2")
        check("latest request retry replays exact reply",
              retry2.status_code == 200 and retry2.json() == turn2.json())

        reused = post("I leave the building.", "turn-1")
        check("reused id with different text is 409", reused.status_code == 409, reused.status_code)

        turn3 = post("I sit down on the bed.", "turn-3")
        check("a new request still plays normally", turn3.status_code == 200, turn3.status_code)

    print(json.dumps({"api": args.api, "session_id": session_id, "checks": checks}, indent=2))
    sys.exit(0 if all(c["ok"] for c in checks) else 1)


if __name__ == "__main__":
    main()
