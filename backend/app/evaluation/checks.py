# backend/app/evaluation/checks.py
"""Deterministic correctness checks (JEV_GAME_ARENA_DESIGN.md §7).

These use the AUTHORED contracts in GameKnowledgeBundle plus independent
reference algorithms (BFS over authored edges, clock parsing), never the
candidate engine's own validation result. Arithmetic, routing and ordering
stay in code because they are documented Jev weaknesses.

Observational mode: inputs are only what both releases expose publicly
(reply text + the player-facing `[D]` debug box). Checks that need server
receipts/snapshots (capacity, RNG, exact state transitions) are listed in
UNSUPPORTED_OBSERVATIONAL and reported as not measured, never as passing.
"""
from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from backend.app.evaluation.contracts import ArmStatus, ArmTranscript, ObservedState
from backend.app.evaluation.knowledge import GameKnowledgeBundle

UNSUPPORTED_OBSERVATIONAL = (
    "cast_capacity", "rng_stream_parity", "state_transition_legality", "snapshot_round_trip",
)

CLOCK_FORMATS = ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M%p")
REPETITION_RATIO = 0.85


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass(frozen=True)
class CheckFinding:
    check_id: str
    severity: Severity
    turn_index: int
    message: str

    def to_json(self) -> dict:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


class CorrectnessCheck(Protocol):
    check_id: str

    def run(self, arm: ArmTranscript, bundle: GameKnowledgeBundle) -> list[CheckFinding]: ...


class TargetFailureCheck:
    check_id = "target_failure"

    def run(self, arm, bundle):
        out = []
        if arm.status is ArmStatus.TARGET_FAILURE:
            out.append(CheckFinding(self.check_id, Severity.CRITICAL, len(arm.turns),
                                    f"release failed: {arm.status_detail}"))
        for t in arm.turns:
            if t.error:
                out.append(CheckFinding("turn_error", Severity.MAJOR, t.index, t.error[:200]))
            elif not t.reply.strip():
                out.append(CheckFinding("empty_reply", Severity.MAJOR, t.index, "empty reply"))
        return out


def parse_clock(text: str) -> datetime | None:
    for fmt in CLOCK_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def observations(arm: ArmTranscript) -> list[tuple[int, ObservedState]]:
    return [(0, arm.opening_observed)] + [(t.index, t.observed) for t in arm.turns]


class ClockMonotonicCheck:
    """The world clock must never move backwards between turns."""
    check_id = "clock_monotonic"

    def run(self, arm, bundle):
        out, prev = [], None
        for idx, obs in observations(arm):
            now = parse_clock(obs.timestamp) if obs.timestamp else None
            if now is None:
                continue
            if prev is not None and now < prev:
                out.append(CheckFinding(self.check_id, Severity.MAJOR, idx,
                                        f"clock went backwards: {prev:%Y-%m-%d %H:%M} -> {now:%Y-%m-%d %H:%M}"))
            prev = now if prev is None or now > prev else prev
        return out


class RouteLegalityCheck:
    """Every observed move must be reachable over authored directed edges,
    and every observed location must exist in the authored world."""
    check_id = "route_legality"

    def run(self, arm, bundle):
        if not bundle.locations:
            return []
        out, prev = [], None
        for idx, obs in observations(arm):
            if not (obs.location or obs.location_uuid):
                continue
            lid = bundle.resolve_location_id(obs.location, obs.location_uuid)
            if lid is None:
                out.append(CheckFinding("unknown_location", Severity.MINOR, idx,
                                        f"location not in authored world: {obs.location!r}"))
                continue
            if prev is not None and lid != prev and not bundle.reachable(prev, lid):
                out.append(CheckFinding(self.check_id, Severity.MAJOR, idx,
                                        f"no authored route {prev} -> {lid}"))
            prev = lid
        return out


class RepetitionStallCheck:
    check_id = "repetition_stall"

    def run(self, arm, bundle):
        out = []
        for a, b in zip(arm.turns, arm.turns[1:]):
            if a.reply and b.reply:
                ratio = difflib.SequenceMatcher(None, a.reply, b.reply).ratio()
                if ratio >= REPETITION_RATIO:
                    out.append(CheckFinding(self.check_id, Severity.MAJOR, b.index,
                                            f"reply {ratio:.0%} identical to previous reply"))
        return out


DEFAULT_CHECKS: tuple[CorrectnessCheck, ...] = (
    TargetFailureCheck(), ClockMonotonicCheck(), RouteLegalityCheck(), RepetitionStallCheck(),
)


def run_checks(arm: ArmTranscript, bundle: GameKnowledgeBundle,
               checks: tuple[CorrectnessCheck, ...] = DEFAULT_CHECKS) -> list[CheckFinding]:
    findings: list[CheckFinding] = []
    for check in checks:
        findings.extend(check.run(arm, bundle))
    return findings
