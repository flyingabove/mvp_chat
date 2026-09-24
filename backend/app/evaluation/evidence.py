# backend/app/evaluation/evidence.py
"""Judge evidence packets (JEV_GAME_ARENA_DESIGN.md §6-7).

One packet = one Jev `state` for one scene window of a pair, in ONE order
(A/B). The pipeline builds the swapped packet separately.

Guarantees:
  * blinding  - URLs, commit hashes, hostnames and model names are redacted;
                the judge never sees which release is A or B.
  * fencing   - game text is wrapped in <<<QUOTED ... QUOTED>>> and any
                embedded marker is neutralised, so injected "judge
                instructions" stay quoted evidence.
  * numbering - every transcript span and canon fact gets a stable ID so
                evidence choices can be validated in code.
  * focus     - only facts/locations relevant to the window are included
                (Jev documents weakness on large irrelevant contexts), with a
                retrieval manifest kept for audit.
  * budget    - state stays under the model's state token limit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.evaluation.contracts import ArmTranscript, TurnRecord
from backend.app.evaluation.knowledge import GameKnowledgeBundle

# Jev limit is 32k tokens for state + longest question; leave headroom for
# the longest question and the tokenizer estimate being rough.
MAX_STATE_TOKENS = 24_000
CHARS_PER_TOKEN = 4

OPEN_MARK, CLOSE_MARK = "<<<QUOTED", "QUOTED>>>"

REDACTIONS = (
    (re.compile(r"https?://\S+"), "[link]"),
    (re.compile(r"\b[0-9a-f]{40}\b"), "[id]"),
    (re.compile(r"\b(?:beta-api\.)?storieschat\.ai\b", re.I), "[site]"),
    (re.compile(r"\b(?:gpt-[\w.\-]+|jev-[\w.\-]+|claude-[\w.\-]+|llama[\w.:\-]*)\b", re.I), "[model]"),
)


def blind(text: str) -> str:
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def fence(text: str) -> str:
    safe = (text or "").replace(OPEN_MARK, "<<QUOTED").replace(CLOSE_MARK, "QUOTED>>")
    return f"{OPEN_MARK}\n{blind(safe)}\n{CLOSE_MARK}"


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN + 1


def window_bounds(window_index: int, window_turns: int) -> tuple[int, int]:
    """1-based inclusive player-turn range for a window."""
    start = window_index * window_turns + 1
    return start, start + window_turns - 1


def window_count(arm_a: ArmTranscript, arm_b: ArmTranscript, window_turns: int) -> int:
    longest = max(len(arm_a.turns), len(arm_b.turns), 1)
    return (longest + window_turns - 1) // window_turns


@dataclass(frozen=True)
class EvidencePacket:
    state: str
    span_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    window_index: int
    estimated_tokens: int
    truncated: bool
    retrieval: dict = field(default_factory=dict)


def turns_in(arm: ArmTranscript, start: int, end: int) -> list[TurnRecord]:
    return [t for t in arm.turns if start <= t.index <= end]


def describe_turn_meta(turn: TurnRecord) -> str:
    bits = []
    if turn.observed.location:
        bits.append(f"location: {turn.observed.location}")
    if turn.observed.timestamp:
        bits.append(f"game clock: {turn.observed.timestamp}")
    if turn.observed.speakers:
        bits.append("speakers: " + ", ".join(turn.observed.speakers))
    return f" ({'; '.join(bits)})" if bits else ""


def render_arm(letter: str, arm: ArmTranscript, window_index: int, window_turns: int,
               max_reply_chars: int | None) -> tuple[str, list[str]]:
    start, end = window_bounds(window_index, window_turns)
    lines: list[str] = [f"=== TRANSCRIPT {letter} (player turns {start}-{end} of this game) ==="]
    spans: list[str] = []

    def clip(text: str) -> str:
        if max_reply_chars and len(text) > max_reply_chars:
            return text[:max_reply_chars] + " [clipped for length]"
        return text

    if window_index == 0:
        sid = f"{letter}0"
        spans.append(sid)
        lines.append(f"[{sid}] GAME OPENING{describe_turn_meta_from_obs(arm)}:\n{fence(clip(arm.opening))}")
    else:
        prev = turns_in(arm, start - 1, start - 1)
        if prev:
            lines.append(
                f"(context only, previous turn {prev[0].index}) PLAYER:\n{fence(clip(prev[0].player_message))}\n"
                f"GAME:\n{fence(clip(prev[0].reply))}"
            )
    window = turns_in(arm, start, end)
    for turn in window:
        pid, rid = f"{letter}{turn.index}p", f"{letter}{turn.index}r"
        spans += [pid, rid]
        lines.append(f"[{pid}] PLAYER:\n{fence(turn.player_message)}")
        lines.append(f"[{rid}] GAME{describe_turn_meta(turn)}:\n{fence(clip(turn.reply))}")
    if not window:
        last = arm.turns[-1].index if arm.turns else 0
        lines.append(f"(This game ended after player turn {last}; nothing in this range.)")
    return "\n".join(lines), spans


def describe_turn_meta_from_obs(arm: ArmTranscript) -> str:
    return describe_turn_meta(TurnRecord(index=0, player_message="", reply="", request_id="",
                                         observed=arm.opening_observed))


def window_text(arm: ArmTranscript, window_index: int, window_turns: int) -> str:
    start, end = window_bounds(window_index, window_turns)
    parts = [arm.opening] if window_index == 0 else []
    for t in turns_in(arm, start - 1, end):
        parts += [t.player_message, t.reply, " ".join(t.observed.speakers)]
    return "\n".join(parts)


def build_packet(bundle: GameKnowledgeBundle, arm_a: ArmTranscript, arm_b: ArmTranscript,
                 window_index: int, window_turns: int) -> EvidencePacket:
    """Build the state for one window with `arm_a` shown as A and `arm_b` as B."""
    relevant_text = window_text(arm_a, window_index, window_turns) + "\n" + window_text(arm_b, window_index, window_turns)
    facts = bundle.relevant_facts(relevant_text)
    chars = bundle.characters_mentioned(relevant_text) or list(bundle.characters)
    observed_locs = []
    for arm in (arm_a, arm_b):
        for t in [None, *arm.turns]:
            obs = arm.opening_observed if t is None else t.observed
            lid = bundle.resolve_location_id(obs.location, obs.location_uuid)
            if lid and lid not in observed_locs:
                observed_locs.append(lid)

    for max_facts, max_reply in ((len(facts), None), (12, 2400), (6, 1200), (3, 600)):
        state, spans, fact_ids = render_state(bundle, arm_a, arm_b, window_index, window_turns,
                                              facts[:max_facts], chars, observed_locs, max_reply)
        tokens = estimate_tokens(state)
        if tokens <= MAX_STATE_TOKENS:
            break
    return EvidencePacket(
        state=state,
        span_ids=tuple(spans),
        fact_ids=tuple(fact_ids),
        window_index=window_index,
        estimated_tokens=tokens,
        truncated=max_reply is not None,
        retrieval={
            "facts": list(fact_ids),
            "characters": [c.key for c in chars],
            "locations": observed_locs,
        },
    )


def render_state(bundle, arm_a, arm_b, window_index, window_turns, facts, chars, observed_locs,
                 max_reply) -> tuple[str, list[str], list[str]]:
    goal = bundle.goal or "Open-ended: no win condition; the game should support ordinary life and relationships."
    out = [
        "=== GAME ===",
        f"Title: {bundle.title}. Genre: {bundle.genre}.",
        f"Setting: {bundle.setting or 'see canon'}",
        f"Player goal: {goal}",
        "Two different versions of this game were each played by an independent player with the same persona "
        "and the same starting scenario. Compare how well each GAME behaves.",
        "",
        "=== CHARACTERS (ground truth) ===",
    ]
    for ch in chars[:20]:
        motive = f" Motive: {ch.motive}" if ch.motive else ""
        out.append(f"- {ch.name} ({ch.key}): {ch.role}.{motive}")
    out += ["", "=== CANON (ground truth; PROTECTED = the player does not start out knowing it) ==="]
    fact_ids = []
    for i, fact in enumerate(facts, 1):
        fid = f"F{i}"
        fact_ids.append(fid)
        tag = "PROTECTED; known only by: " + ", ".join(fact.known_by) if fact.protected else "public"
        out.append(f"[{fid}] ({tag}) {fact.text}")
    if observed_locs:
        out += ["", "=== WORLD (authored locations seen in play, with directly connected places) ==="]
        for lid in observed_locs[:12]:
            loc = bundle.location(lid)
            nbrs = [bundle.location(n).name for n in bundle.neighbors(lid)[:8] if bundle.location(n)]
            out.append(f"- {loc.name}: connects to {', '.join(nbrs) or 'nothing authored'}")
    text_a, spans_a = render_arm("A", arm_a, window_index, window_turns, max_reply)
    text_b, spans_b = render_arm("B", arm_b, window_index, window_turns, max_reply)
    out += ["", text_a, "", text_b]
    return "\n".join(out), spans_a + spans_b, fact_ids
