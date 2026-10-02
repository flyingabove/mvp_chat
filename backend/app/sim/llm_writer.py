"""The real `Writer` for a `SeasonRunner`: a language model writes each scene, then reads it back as consequences (P-06).

Two calls per scene through the one provider switch (`backend/app/llm/chat.py`: Gemini by default, OpenAI as the paid
alternative): `write_scene` produces the prose, `extract` turns that prose into a `SceneUpdate` (a one-line summary and
feeling changes between the people who were present). The prompt is deliberately neutral: setting, the two residents'
authored facts and a format rule, with no drama nudges (those are the P-12 knobs), so the rubric score of this writer is
the baseline every later stage is compared against.

Grounding stays the runner's job: this writer reports whatever the model says, and the runner rejects anything about
someone who was not in the scene. A reply that is not valid JSON becomes a summary-only update, never a guess.

`SeasonRunner` is synchronous and `get_chat` is async (its shared HTTP client belongs to one event loop), so the
caller runs the runner in a worker thread and `bridge_chat` hands each call back to the main loop.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Callable, Optional

from backend.app.sim.story_loader import SeasonSetup
from backend.app.sim.writer import RelationshipDelta, SceneUpdate, participants_from

Chat = Callable[[str, str, float, int], str]            # (system, user, temperature, max_tokens) -> text
SCENE_TOKENS, EXTRACT_TOKENS = 2000, 1200               # Gemini's hidden reasoning counts against max_tokens (chat.py)
DELTA_LIMIT = 0.3                                       # one scene never moves a feeling by more than this
FEELINGS = ("trust", "affection", "suspicion", "fear")

SCENE_SYSTEM = (
    "You write one scene of {title}. Setting: {premise}\n"
    "Write about 200 to 350 words of prose: third person, past tense, with spoken dialogue in quotation marks. Only the "
    "people listed as present speak or act. Do not add other residents, and do not state facts about their pasts beyond "
    "what you are given. Show what happens between them; do not summarise it or comment on it. Output the scene only.")
EXTRACT_SYSTEM = (
    "You read a finished scene and report what changed. Reply with JSON only, no prose, in this shape: "
    '{{"summary": "<one sentence on what happened>", "relationship_deltas": [{{"a": "<id>", "b": "<id>", '
    '"trust": 0, "affection": 0, "suspicion": 0, "fear": 0}}]}}. "a" and "b" are character ids from the list you '
    "are given and must both be present in the scene; a delta is how a feels about b after the scene, between "
    f"-{DELTA_LIMIT} and {DELTA_LIMIT}. Leave out pairs whose feelings did not change.")


class CallCapReached(RuntimeError):
    """The writer's hard cap on model calls; raised before the call, never after money or quota is spent."""


class LLMWriter:
    def __init__(self, chat: Chat, setup: SeasonSetup, max_calls: int) -> None:
        self.chat, self.setup, self.max_calls = chat, setup, max_calls
        self.calls = 0
        self.unparsed = 0                              # extraction replies that were not usable JSON
        self._last: tuple[str, list[str]] = ("", [])   # (text, present ids): the runner always extracts what it just wrote

    # ------------------------------------------------------------------------------------------ the protocol
    def write_scene(self, prompt: str) -> str:
        present = participants_from(prompt)
        text = self._ask(SCENE_SYSTEM.format(title=self.setup.title, premise=self.setup.premise),
                         self._scene_brief(prompt, present), 0.9, SCENE_TOKENS).strip()
        self._last = (text, present)
        return text

    def extract(self, text: str) -> SceneUpdate:
        remembered, present = self._last
        present = present if text == remembered else []         # not our scene: there is nobody to attribute it to
        if not present:
            return SceneUpdate(summary=_first_sentence(text))
        listing = "\n".join(f"- {self.setup.name(cid)} (id {cid})" for cid in present)
        raw = self._ask(EXTRACT_SYSTEM, f"People present:\n{listing}\n\nScene:\n{text}", 0.1, EXTRACT_TOKENS)
        parsed = parse_json_object(raw)
        if parsed is None:
            self.unparsed += 1
            return SceneUpdate(summary=_first_sentence(text))
        return SceneUpdate(summary=str(parsed.get("summary") or "").strip() or _first_sentence(text),
                           relationship_deltas=tuple(_deltas(parsed.get("relationship_deltas"))))

    # ----------------------------------------------------------------------------------------------- helpers
    def _ask(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        if self.calls >= self.max_calls:
            raise CallCapReached(f"writer call cap of {self.max_calls} reached")
        self.calls += 1
        return self.chat(system, user, temperature, max_tokens)

    def _scene_brief(self, prompt: str, present: list[str]) -> str:
        place = next((line[len("Place: "):] for line in prompt.splitlines() if line.startswith("Place: ")), "")
        minute = next((line[len("Minute: "):] for line in prompt.splitlines() if line.startswith("Minute: ")), "0")
        when = self.setup.clock(int(minute)) if minute.lstrip("-").isdigit() else ""
        lines = [f"Where and when: {self.setup.place(place)}" + (f", {when}" if when else "") + ".", "Present:"]
        for cid in present:
            note = self.setup.cast.get(cid)
            facts = [part for part in (note.role if note else "", f"personality type {note.mbti}" if note and note.mbti else "",
                                       f"wants: {note.motive}" if note and note.motive else "") if part]
            lines.append(f"- {self.setup.name(cid)}" + (f" ({'; '.join(facts)})" if facts else ""))
        lines.append("Write what happens between them.")
        return "\n".join(lines)


def _deltas(raw) -> list[RelationshipDelta]:
    out = []
    for row in raw if isinstance(raw, list) else []:
        if not isinstance(row, dict) or not row.get("a") or not row.get("b"):
            continue
        values = {f"{name}_delta": _clamp(row.get(name)) for name in FEELINGS}
        if any(values.values()):
            out.append(RelationshipDelta(str(row["a"]).strip(), str(row["b"]).strip(), **values))
    return out


def _clamp(value) -> float:
    try:
        return max(-DELTA_LIMIT, min(DELTA_LIMIT, round(float(value), 3)))
    except (TypeError, ValueError):
        return 0.0


def _first_sentence(text: str) -> str:
    body = " ".join(text.split())
    match = re.search(r"(.+?[.!?])(\s|$)", body)
    return (match.group(1) if match else body)[:200]


def parse_json_object(raw: str) -> Optional[dict]:
    """The first JSON object in a model reply (tolerates a code fence or a sentence around it); None when there is none."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def bridge_chat(loop: asyncio.AbstractEventLoop, provider: Optional[str] = None, model: Optional[str] = None,
                retries: int = 1) -> Chat:
    """A blocking `Chat` for the runner's worker thread: each call runs `get_chat` on `loop` (the main event loop)."""
    from backend.app.llm.chat import get_chat

    def chat(system: str, user: str, temperature: float, max_tokens: int) -> str:
        for attempt in range(retries + 1):
            future = asyncio.run_coroutine_threadsafe(
                get_chat(system, [{"role": "user", "content": user}], provider=provider, model=model,
                         max_tokens=max_tokens, temperature=temperature), loop)
            try:
                return future.result().text
            except Exception:
                if attempt == retries:
                    raise
        raise AssertionError("unreachable")

    return chat
