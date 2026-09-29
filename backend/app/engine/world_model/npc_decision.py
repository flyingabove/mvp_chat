"""Who decides a character's answer to a social act: the rules, Jev, or both side by side.

`rules`   the local policy alone (standing + standards); no Jev call.
`jev`     Jev judges the nuanced choice (accept / not yet / reject) from the
          target's own first-person view. Bounded by the rules: hard blocks
          (cooldown, closed track, "must be together first") stay with the
          rules, and Jev can never say yes below the required tier, so it can
          only be stricter than the rules, never looser. If Jev is unavailable
          the rules verdict applies and the reason is recorded.
`compare` the rules verdict applies (gameplay is unchanged); Jev is asked as
          well and both answers are logged for side-by-side review.

Jev is a bounded classifier, not a model call: this uses the shared Jev
resolver with a fallback that never reaches a language model, so the
two-LLM-calls-per-turn budget is untouched.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Optional

from backend.app.engine.character_graph import describe_relationship_state
from backend.app.engine.rules.personality import DIALS, personalities
from backend.app.engine.rules.tracks import social_rules
from backend.app.engine.world_model.model import PLAYER, WorldModel
from backend.app.engine.world_model.social_acts import Assessment, SocialAct, ActSpec, Verdict
from backend.app.llm.decisions.types import Criticality, Decision, DecisionBatch, Provider

MODES = ("rules", "jev", "compare")
TASK = "npc_verdict"
OPTIONS = ("accept", "not_yet", "reject")
MIN_CONFIDENCE = 0.5
LOG_LIMIT = 60

ACT_DESCRIPTIONS = {
    "confess": "has just told you they have romantic feelings for you and asked whether you would date them.",
    "ask_leave_together": "has just asked you, as their partner, to leave the house together as a couple.",
}
HINTS = {
    "reject": "they are kind but clear this is not what they want",
    "not_yet": "they are not ready to say yes yet, even though things have gone well",
}
CRITERIA = {
    "accept": "yes: you want this, and nothing you have seen or been told gives you a real reason to hold back",
    "not_yet": "not yet: one specific thing holds you back (too soon, something they did or said, something unresolved)",
    "reject": "no: this is not what you want, and you would say so kindly but clearly",
}


def decision_mode(raw: Optional[str]) -> str:
    """Parse a mode name; anything unknown fails safe to the rules."""
    value = str(raw or "").strip().lower()
    return value if value in MODES else "rules"


def configured_mode() -> str:
    from backend.app.config import settings
    return decision_mode(getattr(settings, "NPC_DECISION_MODE", "rules"))


@dataclass(frozen=True)
class JevJudgment:
    """Jev's answer, or why there is no usable one (`reason` non-empty)."""
    choice: Optional[str]
    confidence: Optional[float] = None
    reason: str = ""
    probabilities: tuple[tuple[str, float], ...] = ()   # (option, probability), for calibration review


@dataclass(frozen=True)
class DecisionRecord:
    turn: int
    mode: str
    act: str
    target: str
    rules: str
    jev: Optional[str]
    final: str
    confidence: Optional[float] = None
    clamped: bool = False
    note: str = ""
    p_accept: Optional[float] = None

    @property
    def agrees(self) -> Optional[bool]:
        return None if self.jev is None else self.jev == self.rules

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "agrees": self.agrees}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DecisionRecord":
        return cls(int(raw.get("turn") or 0), str(raw["mode"]), str(raw["act"]), str(raw["target"]),
                   str(raw["rules"]), raw.get("jev"), str(raw["final"]), raw.get("confidence"),
                   bool(raw.get("clamped")), str(raw.get("note") or ""), raw.get("p_accept"))


def merge(assessment: Assessment, mode: str, judgment: Optional[JevJudgment],
          turn: int = 0) -> tuple[Verdict, DecisionRecord]:
    """Combine the rules' assessment with Jev's judgment under the mode's contract."""
    rules_verdict = assessment.verdict
    act = rules_verdict.act
    if mode == "rules":
        judgment = None   # rules mode never consults or records Jev
    raw_choice = judgment.choice if judgment is not None and judgment.choice in OPTIONS else None
    confidence = judgment.confidence if judgment is not None else None

    def record(final: str, note: str, clamped: bool = False) -> DecisionRecord:
        p_accept = dict(judgment.probabilities).get("accept") if judgment is not None else None
        return DecisionRecord(turn, mode, act.kind, act.target, rules_verdict.answer, raw_choice, final,
                              confidence, clamped, note, p_accept)

    if mode == "rules":
        return rules_verdict, record(rules_verdict.answer, "")
    if assessment.hard:
        return rules_verdict, record(rules_verdict.answer, "hard rule")
    if mode == "compare":
        if judgment is None:
            detail = "; jev not consulted"
        elif judgment.reason:
            detail = f"; jev unavailable: {judgment.reason}"
        else:
            detail = ""
        return rules_verdict, record(rules_verdict.answer, "compare: rules applied" + detail)
    if judgment is None:
        return rules_verdict, record(rules_verdict.answer, "jev not consulted")
    if judgment.reason or raw_choice is None:
        return rules_verdict, record(rules_verdict.answer, f"jev unavailable: {judgment.reason or 'invalid_option'}")

    choice, clamped, note = raw_choice, False, ""
    if choice == "accept" and not assessment.can_accept:
        choice, clamped, note = "not_yet", True, "jev said yes below the required tier"
    hint = "" if choice == "accept" else (
        rules_verdict.hint if choice == "not_yet" and rules_verdict.answer != "accept" and rules_verdict.hint
        else HINTS[choice])
    return Verdict(act, choice, hint), record(choice, note, clamped)


_TRAIT_WORDS = {  # dial -> (high, low)
    "patience": ("patient", "impatient"), "jealousy": ("jealous by nature", "not jealous by nature"),
    "forgiveness": ("forgiving", "slow to forgive"), "skepticism": ("skeptical", "trusting"),
    "openness": ("open and outgoing", "reserved"), "pride": ("proud", "humble"),
}


def _dial_words(person: Any) -> list[str]:
    words = []
    for dial in DIALS:
        value = getattr(person.temperament, dial)
        high, low = _TRAIT_WORDS[dial]
        if value >= 0.7:
            words.append(f"very {high}" if not high.endswith("nature") else high)
        elif value <= 0.3:
            words.append(low)
    return words


def target_view(model: WorldModel, spec: ActSpec, act: SocialAct, story_cfg: dict[str, Any],
                names: dict[str, str], graph: Any = None, ready: Optional[bool] = None) -> str:
    """The target's own view: their character, what the player did to them, what they were told.

    `ready`: whether the rules say they have reached the point where a yes is possible; stated in plain
    words so Jev weighs the evidence instead of guessing what a stage name implies.
    """
    target = act.target
    name = names.get(target, target)
    lines = [f"You are {name}, a housemate on a reality show, in the middle of a private moment."]
    person = personalities(story_cfg).get(target)
    if person is not None:
        traits = _dial_words(person)
        liked = sorted((w, t) for t, w in person.tastes.items() if w >= 1.0)[::-1][:3]
        disliked = sorted((w, t) for t, w in person.tastes.items() if w <= -1.0)[:3]
        if traits:
            lines.append("Your nature: " + ", ".join(traits) + ".")
        if liked:
            lines.append("You warm to: " + ", ".join(t.replace("_", " ") for _, t in liked) + ".")
        if disliked:
            lines.append("You dislike: " + ", ".join(t.replace("_", " ") for _, t in disliked) + ".")
    lines.append(f"The player {ACT_DESCRIPTIONS[act.kind]}")

    rules = social_rules(story_cfg)
    track = rules.tracks.get(spec.track) if rules is not None else None
    standing = model.standing.get(target, PLAYER, spec.track)
    if track is not None:
        tier = track.tier_of(standing.value if standing else 0.0)
        span = max(1e-6, tier.ceiling - tier.floor)
        pct = int(max(0.0, min(1.0, ((standing.value if standing else 0.0) - tier.floor) / span)) * 100)
        lines.append(f"Where you stand with them: {tier.id} (about {pct}% of the way through that stage).")
    if ready is True:
        lines.append("You have gotten to know them well enough that you could say yes to this, if it feels right.")
    elif ready is False:
        lines.append("It is still early: you would normally want to know them better before saying yes to this.")
    day = model.world.day_index(model.world.minute)
    met = model.first_met_day.get(target)
    if met is not None:
        lines.append(f"You have known the player for {max(0, day - met)} days.")
    if model.romance_relationship_partner == target:
        lines.append("You and the player are already a couple.")
    declined = sum(1 for e in model.world.events if e.kind == f"{act.kind}_declined" and target in e.participants)
    if declined:
        lines.append(f"You have already turned this down {declined} time(s) before.")

    edge = graph.get_edge(target, PLAYER) if graph is not None else None
    if edge is not None:
        words = describe_relationship_state(edge.state)
        lines.append(f"How you feel about them: trust is {words['trust_word']}, affection is "
                     f"{words['affection_word']}, suspicion is {words['suspicion_word']}.")

    claims = []
    for key in dict.fromkeys(c.key for c in model.persona.claims if c.speaker == PLAYER and target in c.audience):
        belief = model.persona.belief(target, PLAYER, key)
        if belief.status == "accepted":
            claims.append(f"- {key.replace('_', ' ')}: {belief.value}"
                          + (" (they corrected themselves)" if belief.corrected else ""))
        elif belief.status == "disputed":
            claims.append(f"- {key.replace('_', ' ')}: unsure (they told you different things)")
    if claims:
        lines.append("What the player told you about themselves:")
        lines.extend(claims)

    seen = []
    for effect in model.standing.journal:
        if effect.owner != target or effect.target != PLAYER or effect.track != spec.track \
                or effect.kind not in ("gain", "loss") or str(effect.tag).startswith(("offscreen_", "neglect")):
            continue
        sign = getattr(effect, "proposed", 0) or effect.applied
        seen.append(f"- {str(effect.tag).replace('_', ' ')} ({'you liked it' if sign > 0 else 'you disliked it'})")
    lines.append("What you noticed the player do lately:")
    lines.extend(seen[-6:] or ["- nothing much"])
    return "\n".join(lines)


def jev_decision(target: str, act: SocialAct) -> Decision:
    return Decision(
        id=f"npc_verdict_{target}",
        task=TASK,
        kind="choice",
        instructions=("Answer as the person described in the state, in the first person. Judge only from what "
                      "the state says about you and the player: your nature, how you feel, what they did and "
                      "told you. Would you say yes, not yet, or no to what they just asked?"),
        criteria=dict(CRITERIA),
        criticality=Criticality.DEGRADABLE,
        allowed=frozenset(OPTIONS),
        none_option=None,
        min_confidence=MIN_CONFIDENCE,
    )


async def _no_language_model(_request: Any) -> None:
    """The resolver's fallback for this task: never a language model."""
    return None


_resolver: Any = None


def build_resolver(task: str) -> Any:
    """A Jev-only resolver for one bounded task (TYPESAFE_ENABLED is the master switch).

    The fallback never reaches a language model, so the per-turn LLM budget is untouched.
    """
    from backend.app.config import settings
    from backend.app.llm.decisions.resolver import DecisionResolver, JevConfig
    from backend.app.llm.factory import get_shared_breaker, get_shared_httpx_client
    from backend.app.llm.providers.jev import JevClient
    return DecisionResolver(
        jev=JevClient(get_shared_httpx_client()), legacy=_no_language_model, health=get_shared_breaker(),
        config=JevConfig(enabled=settings.TYPESAFE_ENABLED, enabled_tasks=frozenset({task}),
                         shadow_tasks=frozenset(), shadow_sample_rate=0.0, timeout_ms=settings.JEV_TIMEOUT_MS,
                         max_questions_per_batch=settings.JEV_MAX_QUESTIONS_PER_BATCH))


def default_resolver() -> Any:
    """Shared Jev resolver for NPC verdicts."""
    global _resolver
    if _resolver is None:
        _resolver = build_resolver(TASK)
    return _resolver


def reset_resolver_for_tests() -> None:
    global _resolver
    _resolver = None


async def judge(decision: Decision, view_text: str, resolver: Any = None) -> JevJudgment:
    """Ask Jev; never raises. No usable answer comes back as a reason, not an exception."""
    from backend.app.llm.protocols import LegacyExtractionRequest
    resolver = resolver or default_resolver()
    batch = DecisionBatch(name=TASK, state=view_text, decisions=(decision,))
    try:
        outcome = await resolver.resolve([batch], LegacyExtractionRequest(
            user_msg="", world_locations={}, character_key_to_name={}))
    except Exception as exc:  # the resolver promises not to raise; a bug here must not fail the turn
        return JevJudgment(None, None, f"error:{type(exc).__name__}")
    answer = outcome.answers.get(decision.id)
    odds = tuple(sorted((str(k), float(v)) for k, v in (answer.probabilities if answer is not None else {}).items()))
    if answer is not None and answer.provider is Provider.JEV and answer.usable and answer.choice in OPTIONS:
        return JevJudgment(answer.choice, answer.confidence, "", odds)
    reason = outcome.fallback_reasons.get(decision.id)
    choice = answer.choice if answer is not None and answer.provider is Provider.JEV else None
    return JevJudgment(choice, answer.confidence if answer is not None else None,
                       reason.value if reason is not None else "unavailable", odds)


def append_record(model: WorldModel, record: DecisionRecord) -> None:
    model.decision_log = (model.decision_log + [record.to_dict()])[-LOG_LIMIT:]


def with_turn(record: DecisionRecord, turn: int) -> DecisionRecord:
    return replace(record, turn=turn)
