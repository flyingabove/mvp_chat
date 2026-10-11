"""Observable tells: a hint, never a verdict.

A character's authored tells are cue material. Under pressure a cue may show,
less often for skilled, composed people. The draw is seeded by the turn so
replay reproduces it. What reaches the scene is visible (or audible)
behavior; the engine never tells the storyteller "this person is lying",
and honest nervous people can show the same cues.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Optional

_AUDIBLE = re.compile(r"\b(voice|tone|tremor|pause|repeats|words?|language|says|stammer|laugh|deflects|redirects)\b",
                      re.I)
_WORD = re.compile(r"[^\W_]{4,}", re.UNICODE)


@dataclass(frozen=True)
class DeceptionProfile:
    skill: float = 0.5
    composure: float = 0.5


def audible(cue: str) -> bool:
    return bool(_AUDIBLE.search(cue))


def pressure(message: str, cue: str, questioned: bool) -> float:
    """How hard the moment presses on this cue: its topic raised, or a question put to them."""
    words = {w.lower() for w in _WORD.findall(message or "")}
    on_topic = bool(words & {w.lower() for w in _WORD.findall(cue)})
    return min(1.0, (0.7 if on_topic else 0.0) + (0.3 if questioned else 0.1))


def show_probability(profile: DeceptionProfile, level: float) -> float:
    return max(0.0, min(0.95, level * (1.0 - 0.6 * profile.skill) - 0.2 * profile.composure))


def choose_cue(profile: DeceptionProfile, cues: list[str], message: str, questioned: bool, seed: str,
               voice_only: bool = False) -> Optional[str]:
    """The one tell (if any) this moment shows; deterministic for a given seed."""
    options = [c for c in cues if c.strip() and (audible(c) or not voice_only)]
    if not options:
        return None
    ranked = sorted(options, key=lambda c: -pressure(message, c, questioned))
    cue = ranked[0]
    rng = random.Random(seed)
    return cue if rng.random() < show_probability(profile, pressure(message, cue, questioned)) else None
