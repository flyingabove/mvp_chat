"""Motivated testimony: people with a stake in someone speak about them in their own interest (generic, any story).

Nobody is a neutral narrator. A rival who wants Cat may play down Cat's interest in the player, play up a flaw, or
leave things out; a person pursuing the player has a stake in how the player sees everyone else. The engine's truth
is never changed: only the speaker's private motive reaches the storyteller, framed so they never admit to it and
never state what someone privately feels as fact. Candor (type) and strategy shape how far they go.

A stake exists when the speaker holds a live `pursue` or `compete_for` intention toward the person mentioned, or a
live `pursue` toward the player while the player asks about someone else.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from backend.app.engine.world_model.agenda import intentions
from backend.app.engine.world_model.model import PLAYER, WorldModel

MAX_NOTES = 2
HIGH_CANDOR = 0.7


def stake_notes(model: WorldModel, present: Iterable[str], mentioned: Iterable[str], people: Mapping[str, Any],
                names: Mapping[str, str], day: int) -> list[str]:
    """One note per person with a stake in someone just mentioned, strongest stake first, at most MAX_NOTES."""
    topics = sorted(set(mentioned) - {PLAYER})
    found: list[tuple[float, str, str, str]] = []
    for speaker in sorted(set(present)):
        best = None
        for topic in topics:
            if topic == speaker:
                continue
            for item in intentions(model, speaker, day):
                if item.kind in ("pursue", "compete_for") and item.target == topic:
                    why = "wants them" if item.kind == "pursue" else "is competing for them"
                elif item.kind == "pursue" and item.target == PLAYER:
                    why = "is trying to win the player's interest"
                else:
                    continue
                if best is None or item.priority > best[0]:
                    best = (item.priority, speaker, topic, why)
        if best is not None:
            found.append(best)
    notes = []
    for _, speaker, topic, why in sorted(found, key=lambda row: (-row[0], row[1]))[:MAX_NOTES]:
        person = people.get(speaker)
        who, about = names.get(speaker, speaker), names.get(topic, topic)
        text = (f"{who} has a personal stake in {about} ({why}). If the talk turns to {about}, {who} speaks in their "
                f"own interest: they may play things down, play things up or leave things out, but never admits to "
                f"doing so, and never state what {about} privately feels as certain fact.")
        if person is not None and person.strategy == "scheming":
            text += f" {who} steers the conversation on purpose."
        elif person is not None and person.temperament.candor >= HIGH_CANDOR:
            text += f" {who} would rather withhold than say something false."
        notes.append(text)
    return notes
