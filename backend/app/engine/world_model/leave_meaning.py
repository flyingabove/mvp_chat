"""What did "leave together" mean? (BL-46)

"Do you want to leave with me?" can be an outing (a walk, a date, back by dinner) or the show's win: leave the
house for good as a couple. Only the second is the typed `ask_leave_together` act. Jev (a bounded classifier, never
a language model call) reads the player's line plus whether the two are already a couple and answers
`couple`, `outing` or `unclear`. The rules stay in charge of the outcome: a `couple` reading still needs the
relationship, standing and NPC verdict in `social_acts` / `npc_decision`.

No usable answer: a pair who already are a couple is read as `couple` (the pre-BL-46 behaviour); anyone else is
`unclear`, so the target asks what the player means instead of the engine guessing.
"""
from __future__ import annotations

from typing import Any

from backend.app.engine.world_model import npc_decision
from backend.app.llm.decisions.types import Criticality, Decision

TASK = "leave_meaning"
COUPLE, OUTING, UNCLEAR = "couple", "outing", "unclear"
OPTIONS = (COUPLE, OUTING, UNCLEAR)
MIN_CONFIDENCE = 0.6
CRITERIA = {
    COUPLE: "couple: they ask to leave the house or the show for good together as partners (a life together)",
    OUTING: "outing: they ask to go somewhere together for a while (a walk, a date, an errand) and come back",
    UNCLEAR: "unclear: it could be either, or the words do not say which",
}


def decision() -> Decision:
    return Decision(
        id=TASK, task=TASK, kind="choice",
        instructions=("Read the player's line. Does it ask the other person to leave the house for good together "
                      "as a couple, to go out somewhere together for a while, or is it unclear which?"),
        criteria=dict(CRITERIA), criticality=Criticality.DEGRADABLE, allowed=frozenset(OPTIONS),
        none_option=None, min_confidence=MIN_CONFIDENCE)


def view_text(message: str, target_name: str, already_a_couple: bool) -> str:
    status = (f"The player and {target_name} are already a romantic couple." if already_a_couple
              else f"The player and {target_name} are not a couple yet.")
    return f"{status}\nThe player said to {target_name}:\n{message.strip()[:600]}"


_resolver: Any = None


def default_resolver() -> Any:
    global _resolver
    if _resolver is None:
        _resolver = npc_decision.build_resolver(TASK)
    return _resolver


def reset_resolver_for_tests() -> None:
    global _resolver
    _resolver = None


async def classify(message: str, target_name: str, already_a_couple: bool, resolver: Any = None) -> str:
    """`couple` | `outing` | `unclear`. Never raises; no usable Jev answer falls back as described above."""
    from backend.app.llm.decisions.types import DecisionBatch, Provider
    from backend.app.llm.protocols import LegacyExtractionRequest
    fallback = COUPLE if already_a_couple else UNCLEAR
    batch = DecisionBatch(name=TASK, state=view_text(message, target_name, already_a_couple),
                          decisions=(decision(),))
    try:
        outcome = await (resolver or default_resolver()).resolve(
            [batch], LegacyExtractionRequest(user_msg="", world_locations={}, character_key_to_name={}))
    except Exception:
        return fallback
    answer = outcome.answers.get(TASK)
    if answer is not None and answer.provider is Provider.JEV and answer.usable and answer.choice in OPTIONS:
        return answer.choice
    return fallback
