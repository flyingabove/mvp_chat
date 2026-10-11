"""Jev decides whether an open promise has been carried out.

Live beta (2026-09-29): the player made the tea they promised ("Here you go, Riko") and the
old word-overlap check never noticed, so the promise kept coming back. The owner's rule:
forgetting is fine, failing to register something that happened is not. So:

* Only Jev's meaning-based judgment can close a promise as kept; there is no regex fallback.
* Every uncertain outcome closes the promise quietly. A promise stays open only on a
  confident `pending` (or when Jev could not be reached, where reminders are already
  once-only and a lapse is silent, so leaving it open cannot nag or accuse anyone).
* `done` is never inferred from silence. It is asked two differently shaped ways in ONE Jev request
  (a four-way choice and a yes/no "was it carried out?") and registered if EITHER says so: the two
  fail on different phrasings, and a false "kept" only forgets a promise, so the doubt goes that way.

Jev is a bounded classifier here, not a language model call (see npc_decision).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Optional

from backend.app.engine.world_model.agreements import resolve as resolve_agreement
from backend.app.engine.world_model.memory import Memory, render
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.llm.decisions.types import Criticality, Decision, DecisionBatch, FallbackReason, Provider

TASK = "promise_status"
OPTIONS = ("done", "cancelled", "pending", "unclear")
# Asymmetric on purpose (owner rule): a false "kept" only forgets a promise, a missed "kept" is the bug.
# So `done` wins from a modest probability, while staying open needs a confident `pending`.
DONE_AT = 0.30          # probability of done (choice odds, or the yes/no answer) that registers it
PENDING_AT = 0.60
MAX_CASES = 4
EXCERPT = 500
TRUST_FOR_KEPT_PROMISE = 0.05
# Transport failures leave the promise untouched; anything else Jev could not settle drops it.
UNREACHABLE = frozenset({FallbackReason.FLAG_DISABLED, FallbackReason.CIRCUIT_OPEN, FallbackReason.SHADOW_MODE,
                         FallbackReason.TIMEOUT, FallbackReason.HTTP_ERROR})

CRITERIA = {
    "done": "the promised thing has now actually happened in this exchange, even if it is described in different "
            "words, with a nickname, or only in the narration",
    "cancelled": "someone withdrew, refused, or replaced the promise, so it no longer stands",
    "pending": "it has not happened yet and the promise still stands",
    "unclear": "you cannot tell from the exchange",
}


@dataclass(frozen=True)
class Case:
    memory_id: str
    promiser: str
    counterpart: str
    text: str


@dataclass(frozen=True)
class Ruling:
    memory_id: str
    action: str          # kept | dropped | keep | skip
    choice: Optional[str] = None
    confidence: Optional[float] = None
    reason: str = ""


_PROMISED = re.compile(r"^(?:I promised @\w+ to |@\w+ promised to |I agreed with @\w+ to |@\w+ agreed to )", re.I)


def promised_activity(model: WorldModel, memory: Memory) -> str:
    """The thing promised, in plain words: the agreement's activity, else the memory text minus its framing."""
    agreement = next((a for a in model.agreements.items if a.id == memory.agreement_id), None)         if memory.agreement_id else None
    return agreement.activity if agreement is not None else _PROMISED.sub("", memory.text).strip()


def open_cases(model: WorldModel) -> list[Case]:
    """Open promises whose two parties are both here, newest first. One case per promise."""
    here = set(model.present_with_player()) | {PLAYER}
    cases = []
    for memory in sorted(model.memories.open_promises(), key=lambda m: m.minute, reverse=True):
        if memory.source != "promised" or memory.counterpart not in here or memory.owner not in here:
            continue
        cases.append(Case(memory.id, memory.owner, memory.counterpart, promised_activity(model, memory)))
    return cases[:MAX_CASES]


def _clip(text: str) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= EXCERPT else text[:EXCERPT].rstrip() + "…"


def view_text(case: Case, names: dict[str, str], model: WorldModel, prior_user: str, prior_reply: str,
              message: str) -> str:
    who, other = names.get(case.promiser, case.promiser), names.get(case.counterpart, case.counterpart)
    what = render(case.text, names)     # @ids become names
    lines = [f"{who} promised {other}: {what}", "", "The most recent exchange:"]
    if prior_user.strip():
        lines.append(f"{names.get(PLAYER, 'The player')} said: {_clip(prior_user)}")
    if prior_reply.strip():
        lines.append(f"Then the scene continued: {_clip(prior_reply)}")
    lines.append(f"{names.get(PLAYER, 'The player')} now says: {_clip(message)}")
    return "\n".join(lines)


def done_decision_for(case: Case) -> Decision:
    """The second, independently shaped question: a plain yes/no on whether it was carried out."""
    return Decision(
        id=f"promise_done_{case.memory_id}",
        task=TASK,
        kind="noul",
        instructions=("Read the promise and the most recent exchange. Has the promised thing actually been carried "
                      "out by now, according to what was said or narrated? A plan, offer or intention to do it later "
                      "is not carrying it out. Nicknames and different wording refer to the same people and things."),
        criteria={"carried_out": "the promised thing has already happened"},
        criticality=Criticality.DEGRADABLE,
        true_threshold=DONE_AT,
    )


def decision_for(case: Case) -> Decision:
    return Decision(
        id=f"promise_status_{case.memory_id}",
        task=TASK,
        kind="choice",
        instructions=("Read the promise and the most recent exchange. Decide whether the promised thing has now "
                      "happened. Count it as done when the exchange shows it happening or finished: a handover "
                      "('here you go'), or either person saying or narrating that they did it, in any wording, with "
                      "nicknames standing for the same people. What the player says they do or did counts as happening. "
                      "A plan, offer or intention to do it later is pending, "
                      "and a promise that was withdrawn or replaced is cancelled. If you cannot tell, say unclear."),
        criteria=dict(CRITERIA),
        criticality=Criticality.DEGRADABLE,
        allowed=frozenset(OPTIONS),
        none_option=None,
    )


_resolver: Any = None


def default_resolver() -> Any:
    global _resolver
    if _resolver is None:
        from backend.app.engine.world_model.npc_decision import build_resolver
        _resolver = build_resolver(TASK)
    return _resolver


def reset_resolver_for_tests() -> None:
    global _resolver
    _resolver = None


async def ask(case: Case, state_text: str, resolver: Any = None) -> Ruling:
    """One Jev request with two questions; never raises. Maps the answers to what the engine should do."""
    from backend.app.llm.protocols import LegacyExtractionRequest
    resolver = resolver or default_resolver()
    choice_q, done_q = decision_for(case), done_decision_for(case)
    batch = DecisionBatch(name=TASK, state=state_text, decisions=(choice_q, done_q))
    try:
        outcome = await resolver.resolve([batch], LegacyExtractionRequest(
            user_msg="", world_locations={}, character_key_to_name={}))
    except Exception as exc:
        return Ruling(case.memory_id, "skip", reason=f"error:{type(exc).__name__}")
    answer, yes_no = outcome.answers.get(choice_q.id), outcome.answers.get(done_q.id)
    p_done = yes_no.probability if yes_no is not None and yes_no.provider is Provider.JEV and yes_no.usable else None
    choice_ok = answer is not None and answer.provider is Provider.JEV and answer.usable and answer.choice in OPTIONS
    if choice_ok:
        return ruling_for(case.memory_id, answer.choice, answer.confidence, dict(answer.probabilities or {}), p_done)
    if p_done is not None and p_done >= DONE_AT:
        return Ruling(case.memory_id, "kept", "done", p_done)
    reason = outcome.fallback_reasons.get(choice_q.id) or outcome.fallback_reasons.get(done_q.id)
    if reason in UNREACHABLE or answer is None:
        return Ruling(case.memory_id, "skip", reason=reason.value if reason is not None else "unavailable")
    return Ruling(case.memory_id, "dropped", reason=reason.value if reason is not None else "unsettled")


def ruling_for(memory_id: str, choice: str, confidence: Optional[float], odds: Optional[dict] = None,
               p_done: Optional[float] = None) -> Ruling:
    """`done` from a modest probability on either question, `pending` only when confident, all else closes quietly."""
    odds = odds or {}
    if odds.get("done", 0.0) >= DONE_AT or choice == "done" or (p_done is not None and p_done >= DONE_AT):
        return Ruling(memory_id, "kept", "done", max(odds.get("done", 0.0), p_done or 0.0) or confidence)
    if choice == "pending" and odds.get("pending", confidence or 0.0) >= PENDING_AT:
        return Ruling(memory_id, "keep", "pending", odds.get("pending", confidence))
    return Ruling(memory_id, "dropped", choice, confidence)


def _copies(model: WorldModel, memory: Memory) -> list[Memory]:
    if not memory.agreement_id:
        return [memory]
    return [m for m in model.memories.memories if m.kind == "promise" and m.agreement_id == memory.agreement_id]


def apply(model: WorldModel, ruling: Ruling, now: int, relationships: Any = None) -> bool:
    """Carry out a ruling. Returns True when the promise was closed."""
    memory = next((m for m in model.memories.open_promises() if m.id == ruling.memory_id), None)
    if memory is None:
        return False
    if ruling.action not in ("kept", "dropped"):
        return False
    kept = ruling.action == "kept"
    agreement = next((a for a in model.agreements.items if a.id == memory.agreement_id), None) \
        if memory.agreement_id else None
    actor = memory.owner
    if agreement is not None and agreement.status == "accepted":
        if kept:
            other = agreement.counterpart if actor == agreement.proposer else agreement.proposer
            event = model.world.add_event(now, model.player_place(), tuple(sorted({agreement.proposer,
                                                                                   agreement.counterpart})),
                                          f"@{actor} carried out the agreed activity: {agreement.activity}",
                                          kind="agreement_completed",
                                          operation_id=f"agreement:{agreement.id}:completed",
                                          payload={"agreement_id": agreement.id, "actor": actor})
            resolve_agreement(model.agreements, agreement.id, "completed", now, event.id)
            if relationships is not None:
                relationships.adjust(other, actor, trust_delta=TRUST_FOR_KEPT_PROMISE,
                                     narrative=f"Kept agreement {agreement.id}: {agreement.activity}")
        else:
            resolve_agreement(model.agreements, agreement.id, "cancelled", now)
    elif kept and relationships is not None and memory.counterpart:
        relationships.adjust(memory.counterpart, actor, trust_delta=TRUST_FOR_KEPT_PROMISE,
                             narrative=f"Kept a promise: {render(memory.text, model.names())}")
    for copy in _copies(model, memory):
        if copy.status == "open":
            copy.status = "kept" if kept else "dropped"
    return True


async def review(model: WorldModel, prior_user: str, prior_reply: str, message: str, now: int,
                 relationships: Any = None, resolver: Any = None) -> list[Ruling]:
    """Judge every open promise between people who are here, then apply the rulings."""
    cases = open_cases(model)
    if not cases:
        return []
    names = model.names()
    rulings = await asyncio.gather(*[
        ask(case, view_text(case, names, model, prior_user, prior_reply, message), resolver) for case in cases])
    for ruling in rulings:
        apply(model, ruling, now, relationships)
    return list(rulings)
