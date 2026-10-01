"""The `Writer` protocol a `SeasonRunner` scene asks for narration and its extracted consequences.

The real LLM writer (P-06) implements this against a live model and Jev-assisted extraction. For offline
tests and the unit-gate integration proof, `FakeWriter` is fully deterministic -- scripted text, and an
extraction grounded only in the prompt it was given -- so a season run on it is byte-for-byte repeatable
and never calls a network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

PRESENT_PREFIX = "Present: "


@dataclass(frozen=True)
class RelationshipDelta:
    """A feeling change between two people who were actually in the scene."""
    a: str
    b: str
    trust_delta: float = 0.0
    affection_delta: float = 0.0
    suspicion_delta: float = 0.0
    fear_delta: float = 0.0


@dataclass(frozen=True)
class SceneUpdate:
    """What a written scene changes in the world.

    Grounding is enforced by the runner, not here: `relationship_deltas` must name only people who were
    present in the scene, and `movements` may only relocate a participant. A writer (fake or real) that
    reports anything else has invented a fact the world never perceived; the runner rejects it rather than
    letting it enter state as true.
    """
    summary: str
    relationship_deltas: tuple[RelationshipDelta, ...] = ()
    movements: tuple[tuple[str, str], ...] = ()   # (character_id, destination place)


class Writer(Protocol):
    def write_scene(self, prompt: str) -> str: ...
    def extract(self, text: str) -> SceneUpdate: ...


@dataclass
class FakeWriter:
    """Deterministic writer for tests: no randomness, no model call.

    `write_scene` turns the prompt into scripted prose that still carries the prompt's own "Present: a, b"
    line, so `extract` can recover the real participants instead of guessing or inventing them.
    """
    calls: list[str] = field(default_factory=list)

    def write_scene(self, prompt: str) -> str:
        self.calls.append(prompt)
        return f"[scripted scene]\n{prompt}\nThey spent time together and the moment passed quietly."

    def extract(self, text: str) -> SceneUpdate:
        participants = participants_from(text)
        deltas = tuple(RelationshipDelta(a, b, trust_delta=0.02, affection_delta=0.02)
                       for a, b in zip(participants, participants[1:]))
        names = " and ".join(participants) if participants else "they"
        return SceneUpdate(summary=f"{names} spent time together", relationship_deltas=deltas)


def participants_from(text: str) -> list[str]:
    """Recover the "Present: a, b" line a `SeasonRunner` prompt always carries."""
    for line in text.splitlines():
        if line.startswith(PRESENT_PREFIX):
            return [p.strip() for p in line[len(PRESENT_PREFIX):].split(",") if p.strip()]
    return []
