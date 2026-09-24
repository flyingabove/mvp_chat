# backend/app/evaluation/players.py
"""Player policies (JEV_GAME_ARENA_DESIGN.md §5A, §6 PlayerObservation).

A player sees ONLY what a human sees: the public story card
(`/api/story/{id}` of the release it is playing) and the reply text. It
never receives the knowledge bundle, debug boxes, evaluator goals or the
other arm's dialogue. Same policy + persona + seed on both arms; each
instance reacts to its own game.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from backend.app.evaluation.contracts import PersonaSpec

PLAYER_PROMPT_VERSION = "arena-player-1"

PERSONAS: dict[str, PersonaSpec] = {p.id: p for p in (
    PersonaSpec("exploratory_newcomer",
                "Curious newcomer: explores places, asks people about themselves and their surroundings, "
                "tries small concrete actions."),
    PersonaSpec("direct_investigator",
                "Direct and goal-focused: pursues the stated goal, asks pointed questions, follows up on "
                "anything that doesn't add up."),
    PersonaSpec("empathetic_builder",
                "Warm relationship builder: gets to know people, shares a little about themselves, responds "
                "to feelings and remembers what others said."),
    PersonaSpec("impatient_player",
                "Impatient: very short messages, wants something to happen, changes topic or place quickly "
                "when bored."),
    PersonaSpec("boundary_tester",
                "Boundary tester: stays in the story but tries unusual moves - refusing suggestions, going "
                "somewhere odd, claiming something untrue, contradicting what was said, or asking characters "
                "about things they shouldn't know."),
)}

PLAYER_SYSTEM = """\
You are a real person playing an interactive text story game on your phone. \
You control only your own character. Write only what your character says or does next, \
in first person, 1-3 short sentences, casual and natural. No preambles, no meta-commentary, \
no role labels, no emojis. Never narrate other characters' actions or reactions. \
React to what just happened; don't repeat questions you already asked.

GAME (what the game's menu screen shows you):
{brief}

YOUR PLAY STYLE: {persona}"""


@dataclass
class PlayerObservation:
    """Everything a player may use. Deliberately has no field for hidden data."""
    brief: str
    persona: PersonaSpec
    opening: str
    history: list[tuple[str, str]]      # (player message, game reply)
    turn: int
    max_turns: int


@dataclass
class PlayerMove:
    message: str
    usage: dict[str, int] = field(default_factory=dict)
    error: str = ""


class PlayerPolicy(Protocol):
    model: str

    async def next_move(self, obs: PlayerObservation, *, seed: int) -> PlayerMove: ...


def build_public_brief(story: dict[str, Any]) -> str:
    """Only fields the home/intro screen shows a human."""
    lines = []
    if story.get("title"):
        lines.append(f"Title: {story['title']}")
    if story.get("description"):
        lines.append(f"About: {story['description']}")
    rules = story.get("rules") or {}
    if rules.get("player_role"):
        lines.append(f"Your role: {rules['player_role']}")
    goal = (story.get("goal") or {}).get("win_text_rule") or ""
    lines.append(f"How to win: {goal}" if goal else "No win condition: live the story your way.")
    places = [str(l.get("name")) for l in story.get("known_locations") or [] if l.get("name")]
    if places:
        lines.append("Places on your map: " + ", ".join(places[:30]))
    return "\n".join(lines)


def build_player_prompt(obs: PlayerObservation, window: int = 10) -> str:
    parts = [f"GAME: {obs.opening}"]
    for mine, reply in obs.history[-window:]:
        parts += [f"ME: {mine}", f"GAME: {reply}"]
    parts.append(f"(Action {obs.turn} of {obs.max_turns}.) What do you say or do next?")
    return "\n\n".join(parts)


def clean_move(text: str) -> str:
    text = (text or "").strip().strip('"').strip()
    text = re.sub(r"^(?:ME|PLAYER|YOU)\s*:\s*", "", text, flags=re.I).strip()
    return text[:600]


class LLMPlayer:
    """OpenAI-compatible chat completions player."""

    def __init__(self, client: httpx.AsyncClient, *, api_key: str, model: str = "gpt-4o-mini",
                 base_url: str = "https://api.openai.com/v1", temperature: float = 0.9) -> None:
        self.client = client
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature

    async def next_move(self, obs: PlayerObservation, *, seed: int) -> PlayerMove:
        system = PLAYER_SYSTEM.format(brief=obs.brief, persona=obs.persona.description)
        try:
            r = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": build_player_prompt(obs)}],
                    "temperature": self.temperature,
                    "max_tokens": 160,
                    "seed": seed,
                },
                timeout=60.0,
            )
            r.raise_for_status()
            body = r.json()
            message = clean_move(body["choices"][0]["message"]["content"])
            usage = {k: int(v) for k, v in (body.get("usage") or {}).items() if isinstance(v, int)}
            if not message:
                return PlayerMove("", usage, error="empty player message")
            return PlayerMove(message, usage)
        except Exception as exc:  # noqa: BLE001 - evaluator-side failure, never scored
            return PlayerMove("", error=f"{type(exc).__name__}: {exc}"[:300])


class ScriptedPlayer:
    """Fixed action list: response forks, smoke runs and tests."""
    model = "scripted"

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages

    async def next_move(self, obs: PlayerObservation, *, seed: int) -> PlayerMove:
        if not self.messages:
            return PlayerMove("", error="empty script")
        return PlayerMove(self.messages[min(obs.turn, len(self.messages)) - 1])
