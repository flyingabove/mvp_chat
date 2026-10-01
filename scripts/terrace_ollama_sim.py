"""Simulate Terrace on this machine with EVERY model call routed to Ollama (no cloud calls, no cost).

The game runs in-process (FastAPI TestClient against `backend.app.main:app`) with the same overrides the offline
arena uses (`.claude/skills/promote-to-prod/arena/local_release.py` `ollama_env`): the storyteller and every
extractor go to the local Ollama server and Jev is off, so NPC verdicts use the rules. Because the app is in-process
the simulation can read the world model directly (standing, aims, beats, day) and report gameplay dynamics, not just
text. Retrieval and background fact extraction are stubbed (as in the unit tests) to keep a turn to two model calls.

    python scripts/terrace_ollama_sim.py --gender M --turns 40 --out sim_runs/baseline.jsonl

The simulated player is a patient, warm human (no LLM): the same message pool as the hosted campaign driver, addressed
to one resident of the other gender, with time passing naturally unless --skip-every is set. It measures pacing
(game minutes per turn, turns per game day), progress (standing and tier toward the target), rival activity, reply
repetition and latency. Output: one JSON line per turn plus a summary. It never contacts a hosted server.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

OLLAMA_V1 = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "llama3.1-8b-ctx16k:latest"


def ollama_env(model: str, base_url: str = OLLAMA_V1) -> dict[str, str]:
    """Same overrides as the offline arena's `local_release.ollama_env` (kept inline: that file lives in a skill)."""
    return {
        "OPENAI_BASE_URL": base_url, "OPENAI_MODEL": model, "OPENAI_API_KEY": "ollama",
        "STORY_MASTER_BASE_URL": base_url, "STORY_MASTER_MODEL": model, "STORY_MASTER_API_KEY": "ollama",
        "TYPESAFE_ENABLED": "false", "TYPESAFE_API_KEY": "", "JEV_ENABLED_TASKS": "", "JEV_SHADOW_TASKS": "",
    }


CUE_MARKERS = (("warm", "responds warmly"), ("cool", "reacts coolly"), ("flat", "unmoved by"),
               ("stale", "stopped landing"))


def repeated_sentence_share(texts: list[str], min_words: int = 5) -> float:
    """Share of sentences (>= min_words words) that already appeared earlier in the run."""
    seen: set[str] = set()
    total = repeats = 0
    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            words = re.findall(r"[\w']+", sentence.lower())
            if len(words) < min_words:
                continue
            key = " ".join(words)
            total += 1
            repeats += key in seen
            seen.add(key)
    return repeats / total if total else 0.0


def summarise(rows: list[dict]) -> dict:
    """Pacing, progress, rivals, repetition and latency from the per-turn rows."""
    if not rows:
        return {}
    minutes = [r["game_minute"] for r in rows]
    spans = [b - a for a, b in zip(minutes, minutes[1:]) if b >= a]
    days = max(r["game_day"] for r in rows) - min(r["game_day"] for r in rows) + 1
    standings = [r["standing"] for r in rows if r["standing"] is not None]
    talk = [r for r in rows if r["label"] in ("warm", "confess")]
    gains = [r["gain"] for r in talk]
    by_day: dict[int, list[float]] = {}
    for r in talk:
        by_day.setdefault(r["game_day"], []).append(r["gain"])
    texts = [r["reply_text"] for r in rows]
    return {
        "turns": len(rows),
        "game_days_touched": days,
        "avg_game_minutes_per_turn": round(sum(spans) / len(spans), 1) if spans else 0,
        "turns_per_game_day": round(len(rows) / days, 1),
        "avg_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 1),
        "max_latency_s": max(r["latency_s"] for r in rows),
        "avg_prompt_tokens": round(sum(r["prompt_tokens"] for r in rows) / len(rows)),
        "zero_gain_share_of_talk_turns": round(sum(1 for g in gains if g <= 0) / len(gains), 2) if gains else None,
        "gain_by_game_day": {str(d): round(sum(v), 1) for d, v in sorted(by_day.items())},
        "turns_by_game_day": {str(d): len(v) for d, v in sorted(by_day.items())},
        "first_turn_with_no_gain_after_progress": next(
            (i + 1 for i, g in enumerate(gains) if g <= 0 and any(x > 0 for x in gains[:i])), None),
        "standing_start": standings[0] if standings else None,
        "standing_end": standings[-1] if standings else None,
        "final_tier": rows[-1]["tier"],
        "together_at_turn": next((r["turn"] for r in rows if r["together"]), None),
        "target_spoke_share": round(sum(r["target_spoke"] for r in rows) / len(rows), 2),
        "rival_compete_beats": sum(r["compete_beats"] for r in rows),
        "turns_with_a_reaction_cue": sum(1 for r in rows if r.get("cues")),
        "cue_kinds": {k: sum(r.get("cues", []).count(k) for r in rows) for k, _ in CUE_MARKERS},
        "turns_with_a_tag": sum(1 for r in rows if r.get("tags")),
        "rivals_with_aims": rows[-1]["rivals_with_aims"],
        "avg_reply_words": round(sum(len(t.split()) for t in texts) / len(texts)),
        "repeated_sentence_share": round(repeated_sentence_share(texts), 3),
        "ending": next((r["ending"] for r in rows if r["ending"]), None),
        "extractor_errors": sum(r["extractor_error"] for r in rows),
        "pending_choice_seen": any(r["card"] for r in rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--gender", choices=["M", "F"], default="M")
    parser.add_argument("--turns", type=int, default=40)
    parser.add_argument("--skip-every", type=int, default=0, help="send a one-day skip after every N talk turns (0 = never)")
    parser.add_argument("--confess-after", type=int, default=12, help="first confession after N talk turns, then every 10")
    parser.add_argument("--out", default="")
    parser.add_argument("--seed", type=int, default=0, help="house seed (cast draw)")
    parser.add_argument("--base-mins", type=int, default=0, help="override time.base_turn_mins (0 = the story's own)")
    parser.add_argument("--mins-per-word", type=float, default=-1, help="override time.mins_per_word (-1 = the story's own)")
    args = parser.parse_args(argv)

    os.environ.update(ollama_env(args.model))                    # BEFORE any backend import: settings read env once
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    import random
    from fastapi.testclient import TestClient

    from backend.app.api import prompt_engine as pe
    from backend.app.db import database, repos
    from backend.app.engine import cast_lifecycle
    from backend.app.engine.world_model.standing import Standing  # noqa: F401 (imported for side-effect-free typing)
    from scripts.verify_terrace_win_hosted import (
        CONFESS, ASK, WARM, load_cast, pick_message, pick_target, speakers, together,
    )

    cast_lifecycle.secrets.SystemRandom = lambda: random.Random(args.seed)     # a repeatable house
    tmp = Path(tempfile.mkdtemp(prefix="terrace_sim_"))
    database.DATA_DIR = tmp
    database.DB_PATH = tmp / "storieschat.db"
    repos.DATA_DIR = tmp
    database.init_db()
    pe.retrieve_knowledge = lambda *a, **k: ([], {})                          # no retrieval index (see docstring)

    async def no_facts(*a, **k):
        return []
    pe.extract_facts_from_message = no_facts                                 # no background fact-extraction calls

    from collections import Counter
    events: Counter = Counter()

    def spy(event: dict) -> None:                                           # count engine events, keep stdout readable
        events[str(event.get("kind"))] += 1
    pe._log = spy

    from backend.app import main as app_main
    client = TestClient(app_main.app)
    cast = load_cast()
    sid = "sim-session"
    started = time.time()

    def post(message: str, **extra):
        t0 = time.time()
        reply = client.post("/api/chat", json={"session_id": sid, "message": message, **extra})
        return reply.json(), time.time() - t0

    first, _ = post(f"__cmd_newgame__:six_strangers|{args.gender}|Sam", persona_mode="default",
                    persona_name="Paul Dingus", persona_other="")
    print("new game ok:", bool(first.get("reply")), "| model:", args.model, flush=True)
    live_cfg = pe.SESSIONS[sid]["state"].story_cfg
    if args.base_mins or args.mins_per_word >= 0:                              # pace experiments (this process only)
        live_cfg.setdefault("time", {})
        if args.base_mins:
            live_cfg["time"]["base_turn_mins"] = args.base_mins
        if args.mins_per_word >= 0:
            live_cfg["time"]["mins_per_word"] = args.mins_per_word
    print("pace:", live_cfg.get("time"), flush=True)

    rows: list[dict] = []
    target, last, talk_turns = "", "", 0
    errors_seen = 0
    seen = {"events": 0, "effects": 0}

    def record(label: str, body: dict, elapsed: float) -> None:
        nonlocal errors_seen
        state = pe.SESSIONS[sid]["state"]
        model = state.world_model
        view = model.view
        new_errors, errors_seen = events["turn_extraction_error"] - errors_seen, events["turn_extraction_error"]
        found = speakers(body)
        standing = model.standing.get(target, "player", "romance") if target else None
        tier = model.standing.tier(target, "player", "romance") if target else None
        rivals = [c for c, g in ((k, v["gender"]) for k, v in cast.items()) if g == args.gender and c in model.characters]
        usage = body.get("usage") or {}
        new_tags = [e.payload.get("tag") for e in model.world.events[seen["events"]:]
                    if e.kind == "behavior" and e.payload.get("actor") == "player"]
        seen["events"] = len(model.world.events)
        fresh = model.standing.journal[seen["effects"]:]
        seen["effects"] = len(model.standing.journal)
        mine = [(e.tag, round(getattr(e, "proposed", 0) or 0, 2), round(e.applied, 2)) for e in fresh
                if e.owner == target and e.target == "player"]
        value = round(standing.value, 1) if standing is not None else None
        previous = next((r["standing"] for r in reversed(rows) if r["standing"] is not None), 0.0)
        rows.append({
            "tags": new_tags, "effects": mine,
            "cues": [kind for kind, marker in CUE_MARKERS for line in view.must_address if marker in line], "gain": round((value or 0.0) - previous, 1), "game_day_start": rows[0]["game_day"] if rows else 0,
            "turn": len(rows) + 1, "label": label, "latency_s": round(elapsed, 1),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0), "game_minute": int(model.world.minute),
            "game_day": model.world.day_index(model.world.minute), "location": getattr(state, "location_id", ""),
            "target": target, "target_spoke": bool(target and target in found),
            "standing": round(standing.value, 1) if standing is not None else None, "tier": tier.id if tier else None,
            "together": together(body), "card": bool(body.get("pending_choice")),
            "ending": (body.get("ending") or {}).get("id"),
            "compete_beats": sum("ONE small" in line for line in view.must_address),
            "rivals_with_aims": sum(1 for r in rivals if any(i.kind == "pursue" for i in model.agendas.get(r, []))),
            "extractor_error": new_errors, "reply_text": " ".join(s.get("text", "") for s in body.get("segments") or []),
        })
        print(f"t{rows[-1]['turn']:03d} d{rows[-1]['game_day']} {label:7s} {elapsed:5.1f}s tags={new_tags} fx={mine} tier={rows[-1]['tier']} "
              f"standing={rows[-1]['standing']} spoke={rows[-1]['target_spoke']} together={rows[-1]['together']} "
              f"card={rows[-1]['card']} beats={rows[-1]['compete_beats']}", flush=True)

    def say(label: str, message: str) -> dict:
        nonlocal target, last
        body, elapsed = post(message)
        last = message
        if not target:
            target = pick_target(speakers(body), cast, args.gender)
        record(label, body, elapsed)
        return body

    say("greet", "Hi everyone, I'm Sam. It's lovely to meet you all. What are your names?")
    while len(rows) < args.turns:
        if not target:
            say("greet", "Hello! I'm Sam. Could everyone tell me their names?")
            if len(rows) >= args.turns or len(rows) > 8 and not target:
                break
            continue
        name = cast[target]["first"]
        if rows[-1]["ending"]:
            break
        if rows[-1]["together"] and talk_turns > 0 and rows[-1]["standing"] and rows[-1]["standing"] >= 70:
            body = say("ask", pick_message(ASK, name, talk_turns, last))
            if body.get("pending_choice"):
                say("confirm", "__choice__:leave_together:leave_now")
            continue
        talk_turns += 1
        if not rows[-1]["together"] and talk_turns >= args.confess_after and (talk_turns - args.confess_after) % 10 == 0:
            say("confess", pick_message(CONFESS, name, talk_turns, last))
        else:
            say("warm", pick_message(WARM, name, talk_turns, last))
        if args.skip_every and talk_turns % args.skip_every == 0 and len(rows) < args.turns:
            say("skip", "__cmd_skip__:DAY")

    summary = summarise(rows)
    summary["engine_events"] = {k: v for k, v in sorted(events.items())
                                if k in ("turn_extraction_error", "turn_extraction_movement_applied",
                                         "storyteller_repeat_regenerated", "player_feelings_trimmed", "npc_decision",
                                         "leave_meaning", "chat_response")}
    summary["wall_minutes"] = round((time.time() - started) / 60, 1)
    summary["model"] = args.model
    summary["gender"] = args.gender
    summary["skip_every"] = args.skip_every
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print("SUMMARY", json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
