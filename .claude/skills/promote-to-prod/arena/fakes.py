# .claude/skills/promote-to-prod/arena/fakes.py
"""Deterministic fakes for arena tests and offline smoke runs.

Kept in a backend module (not in test files) per
PYTHON_CODING_STYLE_GUIDE.md: fixture classes live outside tests.

FakeJevClient sits BELOW JevPairwiseJudge (same `ask(batch, timeout_ms)`
contract as JevClient), so tests exercise the real judge validation,
retry and remapping code paths rather than a stubbed judge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from arena.contracts import ObservedState, TargetIdentity
from arena.targets import ArmSession, TurnResult
from backend.app.llm.decisions.types import Decision, DecisionBatch
from backend.app.llm.providers.base import ProviderTimeoutError
from backend.app.llm.providers.jev import JevRawAnswer, JevRawResult

AnswerPolicy = Callable[[Decision, str], JevRawAnswer | None]


def transcript_sections(state: str) -> dict[str, str]:
    """Split a packet state into its A and B transcript sections."""
    a = state.find("=== TRANSCRIPT A")
    b = state.find("=== TRANSCRIPT B")
    if a < 0 or b < 0:
        return {"A": "", "B": ""}
    return {"A": state[a:b], "B": state[b:]}


def choice(option: str, options: list[str]) -> JevRawAnswer:
    probs = {o: (0.97 if o == option else 0.03 / max(1, len(options) - 1)) for o in options}
    return JevRawAnswer(kind="choice", choice=option, confidence=0.97, probabilities=probs)


def marker_policy(bad_marker: str = "BAD") -> AnswerPolicy:
    """Prefers the transcript that does NOT contain `bad_marker`; ties when
    both or neither do. Scores 1.0 for the marked side, 3.0 otherwise; the
    critical probes fire on the marked side."""
    def policy(decision: Decision, state: str) -> JevRawAnswer | None:
        sections = transcript_sections(state)
        bad = {side for side, text in sections.items() if bad_marker in text}
        if decision.kind == "choice" and decision.id.startswith("cmp_"):
            pick = "tie" if len(bad) != 1 else ("B" if "A" in bad else "A")
            return choice(pick, ["A", "B", "tie", "insufficient_evidence"])
        if decision.kind == "choice":
            opts = sorted(decision.allowed or [])
            return choice("none" if "none" in opts else opts[0], opts)
        if decision.kind == "score":
            side = decision.id.split("_")[1]
            return JevRawAnswer(kind="score", score=1.0 if side in bad else 3.0, confidence=0.9,
                                probabilities={"0": 0.1, "1": 0.2, "2": 0.2, "3": 0.3, "4": 0.2})
        if decision.kind == "noul":
            side = decision.id.split("_")[1]
            return JevRawAnswer(kind="noul", probability=0.97 if side in bad else 0.02)
        return None
    return policy


@dataclass
class FakeJevClient:
    policy: AnswerPolicy = field(default_factory=marker_policy)
    model: str = "jev-1.13.0"
    fail_times: int = 0                     # raise a timeout this many times first
    calls: list[DecisionBatch] = field(default_factory=list)

    async def ask(self, batch: DecisionBatch, *, timeout_ms: int) -> JevRawResult:
        self.calls.append(batch)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ProviderTimeoutError("fake timeout")
        answers = {}
        for d in batch.decisions:
            ans = self.policy(d, batch.state)
            if ans is not None:
                answers[d.id] = ans
        return JevRawResult(answers=answers, model=self.model,
                            usage={"input_tokens": len(batch.state) // 4, "output_tokens": 0}, latency_ms=5.0)


@dataclass
class FakeTarget:
    """Scripted release. `reply_fn(message, turn)` makes each reply; set
    `fail_at_turn` for a target failure or `drift_after_identify` to change
    the reported commit after N health checks."""
    label: str
    commit: str = "c0ffee"
    reply_fn: Callable[[str, int], str] = lambda m, t: f"Reply {t} to: {m}"
    fail_at_turn: int = 0
    end_at_turn: int = 0
    drift_after_identify: int = 0
    locations: list[str] = field(default_factory=list)
    identify_calls: int = 0
    turns: dict[str, int] = field(default_factory=dict)
    request_ids: list[str] = field(default_factory=list)

    async def identify(self) -> TargetIdentity:
        self.identify_calls += 1
        commit = self.commit
        if self.drift_after_identify and self.identify_calls > self.drift_after_identify:
            commit = self.commit + "-drift"
        return TargetIdentity(label=self.label, base_url=f"fake://{self.label}", commit=commit,
                              environment=self.label, content_schema_version=1)

    async def capabilities(self) -> dict[str, Any]:
        return {}

    async def public_story(self, story_id: str) -> dict[str, Any]:
        return {"title": f"Story {story_id}", "goal": {"win_text_rule": ""}, "rules": {}}

    async def start(self, session: ArmSession, story_id: str, gender: str, player_name: str) -> TurnResult:
        self.turns[session.session_id] = 0
        return TurnResult(reply=f"Opening of {story_id} for {player_name}.",
                          observed=ObservedState(timestamp="2015-09-01 08:00 PM"))

    async def send(self, session: ArmSession, message: str, request_id: str) -> TurnResult:
        self.request_ids.append(request_id)
        t = self.turns.get(session.session_id, 0) + 1
        self.turns[session.session_id] = t
        if self.fail_at_turn and t >= self.fail_at_turn:
            return TurnResult(reply="", error="HTTP 500")
        reply = self.reply_fn(message, t)
        if self.end_at_turn and t >= self.end_at_turn:
            reply += "\n\nEND GAME YOU WIN -- turns: %d" % t
        loc = self.locations[min(t, len(self.locations)) - 1] if self.locations else ""
        return TurnResult(reply=reply, latency_ms=10,
                          observed=ObservedState(timestamp=f"2015-09-01 08:{t:02d} PM", location=loc))



def make_arm(side: str, replies: list[str], *, pair_id: str = "p", players: list[str] | None = None,
             status=None, observed: list[ObservedState] | None = None, opening: str = "The story begins.",
             commit: str = "c0ffee") -> "ArmTranscript":
    """Build a recorded arm directly (no target) for judge/check/report tests."""
    from arena.contracts import ArmStatus, ArmTranscript, TurnRecord

    turns = [
        TurnRecord(index=i, player_message=(players[i - 1] if players else f"player action {i}"),
                   reply=r, request_id=f"{pair_id}.{side}.t{i}", latency_ms=100 * i,
                   observed=(observed[i - 1] if observed else ObservedState()))
        for i, r in enumerate(replies, 1)
    ]
    ident = TargetIdentity(label=side, base_url=f"fake://{side}", commit=commit, environment=side)
    return ArmTranscript(arm_id=f"{pair_id}.{side}", pair_id=pair_id, side=side, identity_before=ident,
                         identity_after=ident, opening=opening, opening_observed=ObservedState(),
                         turns=turns, status=status or ArmStatus.COMPLETE)


def tiny_bundle():
    """Small authored world: hall -> kitchen -> garden (one-way), plus a
    protected fact known only by Mina."""
    from arena.knowledge import build_bundle

    story = {
        "id": "tiny", "title": "Tiny House", "genre": "Test",
        "characters": [{"key": "mina", "name": "Mina Park", "role": "housemate"},
                       {"key": "jun", "name": "Jun Seo", "role": "landlord"}],
        "epistemic_seed": {"canonical_facts": [
            {"id": "house_public", "text": "The house has a garden.", "known_by": ["player", "mina", "jun"]},
            {"id": "mina_secret", "text": "Mina hid the spare key under the stone frog.",
             "known_by": ["mina"], "not_known_by": ["player", "jun"]},
        ]},
        "goal": {"win_text_rule": "Find the spare key."},
    }
    world = {
        "locations": {"hall": {"name": "Hall", "uuid": "u-tiny-1-hall"},
                      "kitchen": {"name": "Kitchen", "uuid": "u-tiny-1-kitchen"},
                      "garden": {"name": "Garden", "uuid": "u-tiny-1-garden"},
                      "attic": {"name": "Attic", "uuid": "u-tiny-1-attic"}},
        "edges": [{"from": "hall", "to": "kitchen", "minutes": 1},
                  {"from": "kitchen", "to": "hall", "minutes": 1},
                  {"from": "kitchen", "to": "garden", "minutes": 2}],
    }
    return build_bundle(story, world)
