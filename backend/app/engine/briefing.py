"""The canonical per-game briefing (BL-49): what every player is told before the first scene.

Every story declares a `briefing` block: a player-facing `goal` (a good amount of the win condition, never
scores, tiers or spoilers) and optional extra `controls` cards. The engine adds the default controls that are
the same in every game (plain text, `(...)` to the game master, the map, the menu). The map itself is not
duplicated here: the story's existing map image and places are used.

One resolved payload feeds the briefing screen, the "How to play" chat card and the player agent's brief, so a
bot knows exactly what a real player was shown, and nothing more.
"""
from __future__ import annotations

from typing import Any

GOAL_MIN, GOAL_MAX = 20, 700
CARD_TITLE_MAX, CARD_TEXT_MAX = 60, 400

DEFAULT_CONTROLS: tuple[dict[str, str], ...] = (
    {"title": "Talk and act",
     "text": "Type plain text to speak or act as your character."},
    {"title": "Talk to the game master",
     "text": "Put a message in (parentheses) or [brackets] to talk to the game master instead of the characters. "
             "Ask a question, like (who is that?), or give a command, like (I walk out onto the street)."},
    {"title": "Map",
     "text": "Type [map] or /map, or open the ⋮ menu, to see the map."},
    {"title": "Menu",
     "text": "The ⋮ menu also has the cast, the journal, time skip and this How to play guide."},
)


def validate(story_cfg: dict[str, Any]) -> list[str]:
    """Problems with a story's `briefing` block (empty list when it is fine)."""
    block = (story_cfg or {}).get("briefing")
    if not isinstance(block, dict):
        return ["missing `briefing` block"]
    problems: list[str] = []
    goal = block.get("goal")
    if not isinstance(goal, str) or not GOAL_MIN <= len(goal.strip()) <= GOAL_MAX:
        problems.append(f"`briefing.goal` must be {GOAL_MIN}-{GOAL_MAX} characters of player-facing text")
    controls = block.get("controls", [])
    if not isinstance(controls, list):
        problems.append("`briefing.controls` must be a list of {title, text}")
    else:
        for i, card in enumerate(controls):
            if not (isinstance(card, dict) and isinstance(card.get("title"), str) and isinstance(card.get("text"), str)
                    and 0 < len(card["title"].strip()) <= CARD_TITLE_MAX
                    and 0 < len(card["text"].strip()) <= CARD_TEXT_MAX):
                problems.append(f"`briefing.controls[{i}]` needs a short `title` and `text`")
    return problems


def resolved(story_cfg: dict[str, Any]) -> dict[str, Any]:
    """The player-facing briefing: goal, all control cards (defaults first), and the possible endings."""
    block = (story_cfg or {}).get("briefing") or {}
    extras = [{"title": str(c["title"]).strip(), "text": str(c["text"]).strip()}
              for c in block.get("controls") or [] if isinstance(c, dict) and c.get("title") and c.get("text")]
    endings = [{"title": str(e.get("title") or ""), "kind": str(e.get("kind") or "")}
               for e in (story_cfg or {}).get("endings") or [] if isinstance(e, dict) and e.get("title")]
    return {"goal": str(block.get("goal") or "").strip(),
            "controls": [dict(c) for c in DEFAULT_CONTROLS] + extras,
            "endings": endings}


def brief_lines(briefing: dict[str, Any]) -> list[str]:
    """The briefing as plain lines (the player agent's brief and the in-chat "How to play" card)."""
    lines = []
    if briefing.get("goal"):
        lines.append(f"GOAL: {briefing['goal']}")
    for card in briefing.get("controls") or []:
        lines.append(f"{card['title'].upper()}: {card['text']}")
    return lines
