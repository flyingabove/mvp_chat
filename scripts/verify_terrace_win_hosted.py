"""Play Terrace like a patient human to see whether the win path works against a real server (BL-33).

Runs one guest session against `--base` (default: hosted beta) with the real storyteller, extractor and Jev, the way
a browser would: no operator endpoints, no secrets, a random guest id. Each story day it finds a resident of the
opposite gender, seeks them out, spends a few warm turns, confesses once the days allow, asks to leave together the
day after they become a couple, answers the choice card, and stops at the ending. Progress is read only from what a
player sees (the response's `goal.status`, `pending_choice`, `ending`).

    python scripts/verify_terrace_win_hosted.py --gender M
    python scripts/verify_terrace_win_hosted.py --gender F --max-days 25 --max-turns 120

Cost is bounded by the caps. It prints the commit under test and a compact log; exit code 0 only on a win.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Callable

STORY = Path(__file__).resolve().parents[1] / "backend" / "app" / "stories" / "7_six_strangers" / "six_strangers_story.json"
ROOMS = ("living room", "kitchen", "dining room", "terrace")
WARM = (
    "{n}, you look like you've had a long day. Can I make you some tea?",
    "{n}, I really enjoyed talking with you earlier. How was your day?",
    "I offer to help {n} with whatever they are doing, and listen properly while we work.",
    "{n}, tell me something about yourself that most people here don't know. I'd like to hear it.",
    "I tell {n} honestly that I admire how considerate they are with everyone in the house.",
    "{n}, want to sit and chat for a while? I'll bring us something to eat.",
    "I ask {n} what they are hoping for from this house, and I really mean it.",
    "{n}, you were quiet earlier. Is everything all right? I'm here if you want to talk.",
    "I give {n} a genuine compliment about something specific they did today.",
    "{n}, I love how easy it is to be around you. Tell me about what you like to do.",
)
CONFESS = (
    "{n}, I have to be honest with you: I have feelings for you. Would you like to go out with me, properly?",
    "{n}, I really like you, more than a friend. I'd love to be together. What do you think?",
)
ASK = (
    "{n}, I'd like us to leave this house together, as a couple, for good. Will you leave with me?",
    "{n}, I want to leave the house with you and start our life together. Will you come with me?",
)


def load_cast(path: Path = STORY) -> dict[str, dict[str, str]]:
    """{key: {"gender": "M"|"F", "first": first name}} from the repo's story file."""
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return {c["key"]: {"gender": str(c.get("gender") or "").upper(), "first": str(c.get("name") or c["key"]).split()[0]}
            for c in cfg["characters"]}


def speakers(body: dict) -> set[str]:
    return {str(s.get("speaker_id")) for s in body.get("segments") or []
            if s.get("kind") == "dialogue" and s.get("speaker_id")}


def together(body: dict) -> bool:
    status = str((body.get("goal") or {}).get("status") or "")
    return status.startswith("You and") and "together" in status


def pick_target(seen: set[str], cast: dict, player_gender: str, current: str = "") -> str:
    """Keep the current target; otherwise the first (alphabetical, so repeatable) opposite-gender resident seen."""
    if current:
        return current
    return next((k for k in sorted(seen) if cast.get(k, {}).get("gender") not in ("", player_gender)
                 and cast.get(k)), "")


def pick_message(pool: tuple[str, ...], name: str, counter: int, last: str = "") -> str:
    """Rotate through the pool, never the same line twice in a row."""
    for offset in range(len(pool)):
        text = pool[(counter + offset) % len(pool)].format(n=name)
        if text != last:
            return text
    return pool[counter % len(pool)].format(n=name)


def rival_evidence(body: dict, cast: dict, player_gender: str) -> list[str]:
    """Narration or speech that shows a same-gender resident making a move: an invitation they are the subject of."""
    firsts = {v["first"] for k, v in cast.items() if v["gender"] == player_gender}
    lines = []
    for seg in body.get("segments") or []:
        text = str(seg.get("text") or "")
        if any(re.search(rf"\b{re.escape(f)}\b[^.!?]*?\binvit", text, re.I) for f in firsts):
            lines.append(text[:160])
    return lines


class Campaign:
    def __init__(self, post: Callable[..., tuple[int, dict]], gender: str, cast: dict, *, max_days: int = 25,
                 max_turns: int = 120, log: Callable[[str], None] = print):
        self.post, self.gender, self.cast = post, gender, cast
        self.max_days, self.max_turns, self.log = max_days, max_turns, log
        self.turns = self.day = 0
        self.target = ""
        self.last = ""
        self.together_day = None
        self.evidence: list[str] = []
        self.ending: dict | None = None
        self.outcomes: list[str] = []

    # -- one request -------------------------------------------------------------------------------------------------
    def say(self, label: str, message: str) -> dict:
        self.turns += 1
        status, body = self.post(message)
        self.last = message
        body = body if isinstance(body, dict) else {}
        found = speakers(body)
        if not self.target:
            self.target = pick_target(found, self.cast, self.gender)
        if self.together_day is None and together(body):
            self.together_day = self.day
        for line in rival_evidence(body, self.cast, self.gender):
            self.evidence.append(f"day {self.day}: {line}")
        if body.get("ending"):
            self.ending = body["ending"]
        self.log(f"d{self.day:02d} t{self.turns:03d} {label:7s} http={status} target_spoke={self.target in found} "
                 f"together={together(body)} card={bool(body.get('pending_choice'))} "
                 f"ending={(body.get('ending') or {}).get('id')}")
        return body

    def done(self) -> bool:
        return bool(self.ending) or self.turns >= self.max_turns

    def name(self) -> str:
        return self.cast.get(self.target, {}).get("first", "everyone") if self.target else "everyone"

    # -- the day ---------------------------------------------------------------------------------------------------
    def seek(self) -> dict:
        """The target did not answer: look for them, room by room."""
        body: dict = {}
        for room in ROOMS:
            if self.done():
                break
            self.say("go", f"I go to the {room}.")
            body = self.say("seek", pick_message(WARM, self.name(), self.turns, self.last))
            if self.target in speakers(body):
                break
        return body

    def play_day(self) -> None:
        if not self.target:
            self.say("greet", "Hi everyone, I'm Sam. It's lovely to meet you all. What are your names?")
            for room in ROOMS:                       # nobody of the other gender spoke: look in the other rooms
                if self.target or self.done():
                    break
                self.say("go", f"I go to the {room}.")
                self.say("greet", "Hello! I'm Sam. What are your names?")
            if not self.target:
                return
        body = self.say("warm", pick_message(WARM, self.name(), self.turns, self.last))
        if self.target not in speakers(body):
            body = self.seek()
        if self.done():
            return
        if self.together_day is not None and self.day > self.together_day:
            body = self.say("ask", pick_message(ASK, self.name(), self.day, self.last))
            if body.get("pending_choice"):
                self.say("confirm", "__choice__:leave_together:leave_now")
            return
        if self.together_day is None and self.day >= 3 and self.day % 2 == 1:
            self.say("confess", pick_message(CONFESS, self.name(), self.day, self.last))
        for _ in range(2):
            if self.done():
                break
            self.say("warm", pick_message(WARM, self.name(), self.turns, self.last))

    def run(self) -> dict:
        while not self.done():
            if self.day >= self.max_days:
                break
            self.day += 1
            self.play_day()
            if self.done():
                break
            self.say("skip", "__cmd_skip__:DAY")
        return {"won": bool(self.ending and self.ending.get("kind") == "win"), "ending": self.ending,
                "days": self.day, "turns": self.turns, "target": self.target,
                "together_day": self.together_day, "rival_evidence": self.evidence}


def main(argv: list[str] | None = None) -> int:
    import requests
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="https://beta-api.storieschat.ai")
    parser.add_argument("--gender", choices=["M", "F"], required=True)
    parser.add_argument("--name", default="Sam")
    parser.add_argument("--max-days", type=int, default=25)
    parser.add_argument("--max-turns", type=int, default=120)
    args = parser.parse_args(argv)
    guest, session = str(uuid.uuid4()), str(uuid.uuid4())
    headers = {"X-Guest-Id": guest}
    try:
        health = requests.get(args.base + "/api/health", timeout=20).json()
        print("commit under test:", health.get("commit"), "env:", health.get("environment"))
    except Exception as exc:                                                    # noqa: BLE001 - informational only
        print("health check failed:", exc)

    def post(message: str, **extra):
        payload = {"session_id": session, "message": message, "request_id": str(uuid.uuid4()), **extra}
        reply = requests.post(args.base + "/api/chat", headers=headers, json=payload, timeout=300)
        return reply.status_code, reply.json()

    status, first = post(f"__cmd_newgame__:six_strangers|{args.gender}|{args.name}", persona_mode="default",
                         persona_name="Paul Dingus", persona_other="")
    print("new game:", status, "ok" if first.get("reply") else first)
    result = Campaign(post, args.gender, load_cast(), max_days=args.max_days, max_turns=args.max_turns).run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["won"] else 1


if __name__ == "__main__":
    sys.exit(main())
