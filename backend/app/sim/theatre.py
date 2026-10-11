"""The Drama Theatre: a season that runs scene by scene while an admin watches, chats, nudges and skips time (BL-86, P-13).

Built on the same parts as the headless `SeasonRunner`: the world stepper moves every resident through their routine and
a `Writer` (the real LLM writer in production, `FakeWriter` in tests) writes each scene, which is committed through the
runner's own grounding-checked `_commit_scene`. What differs is that the run is *driven*:

- `step()` moves the clock forward until some residents are together, picks the most interesting gathering (the camera:
  group size, how long they were together, who has not had a scene lately, and anyone the admin just nudged about) and
  writes it as ONE scene for everybody there. Other gatherings in that stretch are listed as "also" lines, never written.
- `nudge()` queues the admin's words for the next scene; the writer is told, the people are not. `@name text` whispers the
  nudge to one resident. The nudge shapes what happens; it never states an outcome.
- `skip()` moves the clock (to evening, to the next morning, N hours, a day) without writing the gatherings it crosses;
  they are summarised in one deterministic "meanwhile" line each, so the world still advances everywhere.
- `say()` is the one entry point for the admin's typed line: a skip command ("skip to evening", "skip 3 hours", "next day")
  or else a nudge.

The residents' private aims (P-07 goals) and how they feel about each other go to the writer with every scene, plus the last
few scene summaries so scenes build on earlier ones. Nothing here is a player-facing log: this is the admin watch mode.
Every beat (scene, skip, nudge) is appended to a JSONL file so a session can be replayed later.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from backend.app.engine.rules.personality import personalities
from backend.app.engine.world_model.goals import active_goal, card_note
from backend.app.engine.world_model.offscreen import Encounter, find_encounters
from backend.app.engine.world_model.stepper import step_world
from backend.app.sim.invariants import check_day
from backend.app.sim.runner import SeasonRunner
from backend.app.sim.story_loader import SeasonSetup, build_season
from backend.app.sim.writer import Writer

CHUNK_MIN = 90                    # how far one look-ahead moves the clock before checking who is together
MAX_LOOKAHEAD_MIN = 24 * 60       # a step that finds nobody together in a whole day gives up and says so
RECENT_BEATS = 3                  # earlier scene summaries handed to the writer for continuity
CALLS_PER_SCENE = 2
DEFAULT_CALL_CAP = 300
MAX_NUDGE_CHARS = 400
LOG_DIR = Path("/data/theatre") if Path("/data").exists() else Path("./data/theatre")

TONE = ("Real life, dramatized: plausible but very dramatic. People want things, hide things and push on each other; small "
        "frictions can escalate and sparks can catch. Let something change by the end of the scene (a decision, a reveal, "
        "a rift, a moment of nerve) instead of settling into a quiet beat. Never resolve what these people would not resolve, "
        "and never announce a character's private aim: show it through what they do.")

SPOTS = {"evening": "19:00", "tonight": "19:00", "night": "23:00", "bedtime": "23:00", "morning": "08:00", "noon": "12:00",
         "lunch": "12:00", "afternoon": "15:00", "dinner": "19:00", "midnight": "00:00"}


class TheatreCapReached(RuntimeError):
    """The session's hard cap on model calls; raised before a scene is written, never mid-write."""


class NothingHappens(RuntimeError):
    """A whole day passed with nobody together (a step cannot find a scene)."""


@dataclass
class Gathering(Encounter):
    """Everyone in one place together for a stretch. `a` and `b` (the first two) keep the pair-shaped Encounter contract."""
    people: tuple[str, ...] = ()


@dataclass(frozen=True)
class Command:
    kind: str                     # skip | nudge | next
    text: str = ""
    to: str = ""                  # nudge: a resident id when whispered
    minutes: int = 0              # skip: relative minutes (0 when `clock` is set)
    clock: str = ""               # skip: "HH:MM", the next time the clock reads that


def parse_command(text: str, names: dict[str, str]) -> Command:
    """The admin's line as a command. `names` maps resident id -> display name (for `@name` whispers)."""
    line = (text or "").strip()
    skip = re.match(r"^/?(skip|jump|fast[- ]?forward|wait|time ?skip)\b(.*)$", line, re.I)
    if skip:
        return _skip(skip.group(2).strip().lower())
    if re.fullmatch(r"(next( scene)?|go on|continue|/next)", line, re.I):
        return Command("next")
    if re.fullmatch(r"(next day|tomorrow|the next day)", line, re.I):
        return Command("skip", minutes=24 * 60)
    whisper = re.match(r"^@(\w+)\s+(.+)$", line, re.S)
    if whisper:
        wanted = whisper.group(1).lower()
        target = next((cid for cid, name in names.items() if wanted in (cid.lower(), name.lower().split()[0])), "")
        if target:
            return Command("nudge", whisper.group(2).strip()[:MAX_NUDGE_CHARS], to=target)
    return Command("nudge", line[:MAX_NUDGE_CHARS])


def _skip(rest: str) -> Command:
    rest = re.sub(r"^(to|until|till|ahead to|forward to|the)\s+", "", rest).strip()
    rest = re.sub(r"^(the )?", "", rest)
    if not rest or rest in ("scene", "this scene", "ahead"):
        return Command("next")
    match = re.search(r"(\d+(?:\.\d+)?|an?|one)\s*(h|hr|hrs|hour|hours)\b", rest)
    if match:
        count = 1.0 if match.group(1) in ("a", "an", "one") else float(match.group(1))
        return Command("skip", minutes=max(1, int(count * 60)))
    match = re.search(r"(\d+|an?|one)\s*days?\b", rest)
    if match or rest in ("tomorrow", "next day", "a day"):
        count = 1 if not match or match.group(1) in ("a", "an", "one") else int(match.group(1))
        return Command("skip", minutes=24 * 60 * max(1, count))
    clock = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", rest)
    if clock and (clock.group(2) or clock.group(3)):
        hour, minute = int(clock.group(1)) % 12 if clock.group(3) else int(clock.group(1)), int(clock.group(2) or 0)
        hour += 12 if clock.group(3) == "pm" else 0
        return Command("skip", clock=f"{hour % 24:02d}:{minute:02d}")
    for word, spot in SPOTS.items():
        if word in rest:
            return Command("skip", clock=spot)
    return Command("nudge", f"skip {rest}")          # not a time we understand: treat it as the admin's words


def cluster(encounters: list[Encounter]) -> list[Gathering]:
    """Merge pair encounters in one place into gatherings (people who share a place and a stretch of time)."""
    groups: dict[str, list[set[str]]] = {}
    for enc in encounters:
        merged = {enc.a, enc.b}
        keep = []
        for existing in groups.setdefault(enc.place, []):
            if existing & merged:
                merged |= existing
            else:
                keep.append(existing)
        groups[enc.place] = keep + [merged]
    out = []
    for place, sets in sorted(groups.items()):
        for people in sets:
            mine = [e for e in encounters if e.place == place and {e.a, e.b} <= people]
            ordered = tuple(sorted(people))
            out.append(Gathering(ordered[0], ordered[1], place, min(e.minute for e in mine),
                                 max(e.duration for e in mine), ordered))
    return out


class Theatre:
    """One running season for one admin. Synchronous: callers run `step` and `say` on a worker thread."""

    def __init__(self, setup: SeasonSetup, writer: Writer, *, session_id: str = "", seed: str = "",
                 call_cap: int = DEFAULT_CALL_CAP, tone: str = TONE, log_dir: Optional[Path] = LOG_DIR) -> None:
        self.setup, self.writer, self.id, self.seed = setup, writer, session_id, seed
        self.call_cap, self.tone = call_cap, tone
        self.runner = SeasonRunner(setup.story, seed, writer, days=1)
        self.people = personalities(setup.cfg)
        self.beats: list[dict[str, Any]] = []
        self.nudges: list[dict[str, str]] = []                # not yet used by a scene: {text, to}
        self.last_scene_step: dict[str, int] = {}             # resident -> beat number of their last scene
        self.pending: Optional[Gathering] = None              # a gathering whose writing failed: retried first
        self.log_path = (log_dir / f"{session_id or 'session'}.jsonl") if log_dir is not None else None

    # ----------------------------------------------------------------------------------------------- views
    @property
    def model(self):
        return self.setup.story.model

    @property
    def minute(self) -> int:
        return self.model.world.minute

    def names(self) -> dict[str, str]:
        return {cid: self.setup.name(cid) for cid in self.model.characters}

    def clock(self) -> str:
        return self.setup.clock(self.minute)

    def calls(self) -> int:
        calls = getattr(self.writer, "calls", 0)
        return len(calls) if isinstance(calls, list) else int(calls or 0)

    def state(self, since: int = 0) -> dict[str, Any]:
        """Everything the page needs: the clock, where everyone is, the director view and beats after `since`."""
        names = self.names()
        cast = []
        for cid in sorted(self.model.characters):
            goal = active_goal(self.model.goals, cid, self.people.get(cid))
            cast.append({"id": cid, "name": names[cid], "role": getattr(self.setup.cast.get(cid), "role", ""),
                         "place": self.setup.place(self.model.world.place_of(cid) or ""),
                         "availability": self.model.characters[cid].availability,
                         "aim": card_note(goal, self.model.goals.weight(cid, goal), names) if goal else "",
                         "feelings": self._feelings(cid, names)})
        return {"id": self.id, "story": self.setup.title, "clock": self.clock(), "minute": self.minute, "cast": cast,
                "beats": [b for b in self.beats if b["n"] > since], "last": len(self.beats),
                "nudges": [dict(n) for n in self.nudges], "calls": self.calls(), "call_cap": self.call_cap}

    def _feelings(self, cid: str, names: dict[str, str]) -> list[str]:
        out = []
        for other in sorted(self.model.characters):
            if other != cid:
                words = feeling_words(self.setup.story.relationships.feelings(cid, other))
                if words:
                    out.append(f"{words} {names[other]}")
        return out

    # ---------------------------------------------------------------------------------------------- driving
    def say(self, text: str) -> list[dict[str, Any]]:
        """Handle one typed line: a skip command, or a nudge for the next scene. Returns the beats it made."""
        command = parse_command(text, self.names())
        if command.kind == "skip":
            return [self.skip(minutes=command.minutes, clock=command.clock)]
        if command.kind == "nudge":
            return [self.nudge(command.text, command.to)]
        return []

    def nudge(self, text: str, to: str = "") -> dict[str, Any]:
        text = text.strip()[:MAX_NUDGE_CHARS]
        if not text:
            raise ValueError("a nudge needs some words")
        self.nudges.append({"text": text, "to": to})
        who = f" (whispered to {self.setup.name(to)})" if to else ""
        return self._beat("nudge", text=text + who)

    def skip(self, minutes: int = 0, clock: str = "") -> dict[str, Any]:
        """Move the clock without writing the gatherings it crosses; each becomes one "meanwhile" line."""
        now = self.minute
        target = now + minutes if minutes else self._next_clock(clock, now)
        if target <= now:
            raise ValueError("there is nothing to skip: that time is not ahead of the clock")
        meanwhile = []
        cursor = now
        while cursor < target:
            end = min(target, cursor + 6 * 60)
            step = step_world(self.model, cursor, end, scene_present=set())
            meanwhile.extend(self._also(cluster(find_encounters(step))))
            cursor = end
        self.pending = None
        self._check_invariants()
        return self._beat("skip", text=f"Time passes. It is now {self.clock()}.", also=meanwhile[:6],
                          place_names=self._where())

    def step(self) -> dict[str, Any]:
        """Advance to the next gathering and write it as one scene. Raises TheatreCapReached or NothingHappens."""
        if self.calls() + CALLS_PER_SCENE > self.call_cap:
            raise TheatreCapReached(f"this session has used {self.calls()} of its {self.call_cap} model calls")
        gathering, also = (self.pending, []) if self.pending else self._find_gathering()
        self.pending = gathering                         # kept until it is written, so a model failure loses nothing
        used = self.nudges[:]
        text = self.writer.write_scene(self._prompt(gathering, used))
        update = self.writer.extract(text)
        rejections = self.runner._commit_scene(gathering, update)
        self.pending = None
        self.nudges = [n for n in self.nudges if n not in used]
        self._check_invariants()
        names = self.names()
        beat = self._beat(
            "scene", text=text, summary=update.summary, place=self.setup.place(gathering.place),
            people=[{"id": cid, "name": names.get(cid, cid)} for cid in gathering.people], also=also,
            deltas=[{"a": d.a, "b": d.b, "trust": d.trust_delta, "affection": d.affection_delta,
                     "suspicion": d.suspicion_delta, "fear": d.fear_delta} for d in update.relationship_deltas],
            moves=[[cid, self.setup.place(place)] for cid, place in update.movements], rejections=rejections,
            nudged=[n["text"] for n in used])
        for cid in gathering.people:
            self.last_scene_step[cid] = beat["n"]
        return beat

    # ---------------------------------------------------------------------------------------------- internals
    def _find_gathering(self) -> tuple[Gathering, list[str]]:
        waited = 0
        while waited < MAX_LOOKAHEAD_MIN:
            start = self.minute
            step = step_world(self.model, start, start + CHUNK_MIN, scene_present=set())
            waited += CHUNK_MIN
            found = cluster(find_encounters(step))
            if found:
                best = max(found, key=lambda g: (self._interest(g), g.place))
                return best, self._also([g for g in found if g is not best])
        raise NothingHappens("nobody was together for a whole day")

    def _interest(self, gathering: Gathering) -> float:
        """The camera: bigger groups, longer time together, people who have been off screen, and anyone just nudged about."""
        beat = len(self.beats)
        score = 2.0 * len(gathering.people) + gathering.duration / 60.0
        score += sum(min(6, beat - self.last_scene_step.get(cid, 0)) for cid in gathering.people) * 0.5
        for nudge in self.nudges:
            wanted = {nudge["to"]} if nudge["to"] else {cid for cid, name in self.names().items()
                                                        if re.search(rf"\b{re.escape(name.split()[0])}\b", nudge["text"], re.I)}
            score += 4.0 * len(wanted & set(gathering.people))
        return score

    def _also(self, gatherings: list[Gathering]) -> list[str]:
        names = self.names()
        return [f"{_join([names.get(c, c) for c in g.people])} were in the {self.setup.place(g.place)}"
                f" ({self.setup.clock(g.minute)})" for g in gatherings]

    def _where(self) -> dict[str, str]:
        names = self.names()
        return {names[cid]: self.setup.place(self.model.world.place_of(cid) or "") for cid in sorted(self.model.characters)}

    def _prompt(self, gathering: Gathering, nudges: list[dict[str, str]]) -> str:
        names = self.names()
        lines = [f"Present: {', '.join(gathering.people)}", f"Place: {gathering.place}", f"Minute: {gathering.minute}",
                 "Context:"]
        recent = [b["summary"] for b in self.beats if b["type"] == "scene" and set(p["id"] for p in b["people"])
                  & set(gathering.people)][-RECENT_BEATS:]
        if recent:
            lines.append("Earlier (build on this; do not repeat it): " + " | ".join(recent))
        for cid in gathering.people:
            goal = active_goal(self.model.goals, cid, self.people.get(cid))
            if goal is not None:
                lines.append(f"{names[cid]}: {card_note(goal, self.model.goals.weight(cid, goal), names)}")
            for other in gathering.people:
                if other != cid:
                    words = feeling_words(self.setup.story.relationships.feelings(cid, other))
                    if words:
                        lines.append(f"{names[cid]} {words} {names[other]}")
        for nudge in nudges:
            if nudge["to"] and nudge["to"] in gathering.people:
                lines.append(f"A nudge only {names[nudge['to']]} feels (they act on it; the others do not know): {nudge['text']}")
            elif not nudge["to"]:
                lines.append(f"The director's nudge for this scene (let it shape events; do not state an outcome): {nudge['text']}")
        return "\n".join(lines)

    def _next_clock(self, hhmm: str, now: int) -> int:
        start = _start(self.setup.start)
        moment = start + timedelta(minutes=now)
        hour, minute = (int(part) for part in hhmm.split(":"))
        target = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= moment:
            target += timedelta(days=1)
        return int((target - start).total_seconds() // 60)

    def _check_invariants(self) -> None:
        violations = check_day(self.setup.story.model, self.setup.story.cast_lifecycle, self.setup.story.expected_cast_size)
        if violations:
            self._beat("note", text="Invariant check: " + "; ".join(violations))

    def _beat(self, kind: str, **fields: Any) -> dict[str, Any]:
        beat = {"n": len(self.beats) + 1, "type": kind, "minute": self.minute, "clock": self.clock(), **fields}
        self.beats.append(beat)
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"ts": time.time(), **beat}, ensure_ascii=False) + "\n")
        return beat


def _start(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime(2000, 1, 3)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def feeling_words(edge: dict[str, float]) -> str:
    """A few plain words for how one person feels about another, or "" when nothing stands out."""
    parts = []
    if edge.get("affection", 0) >= 0.25:
        parts.append("is fond of")
    elif edge.get("affection", 0) <= -0.2:
        parts.append("is cool toward")
    if edge.get("trust", 0) <= -0.2:
        parts.append("distrusts")
    if edge.get("suspicion", 0) >= 0.25:
        parts.append("is suspicious of")
    if edge.get("fear", 0) >= 0.25:
        parts.append("is afraid of")
    return " and ".join(parts[:2])


def start_theatre(story_id: str, seed: str, writer_factory, *, session_id: str, call_cap: int = DEFAULT_CALL_CAP,
                  log_dir: Optional[Path] = LOG_DIR) -> Theatre:
    """Build the season's world and a Theatre over it. `writer_factory(setup, cap)` returns the writer."""
    setup = build_season(story_id, seed, ai_player_slot=True)
    return Theatre(setup, writer_factory(setup, call_cap), session_id=session_id, seed=seed, call_cap=call_cap,
                   log_dir=log_dir)
