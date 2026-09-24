# backend/app/evaluation/contracts.py
"""Data contracts shared by every arena stage.

JEV_GAME_ARENA_DESIGN.md §4 (experiment identity), §6 (turn evidence) and §8
(rating units). Everything here is plain data that round-trips through JSON
so experiments are resumable and auditable from disk alone.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any, Mapping

ARENA_SCHEMA_VERSION = "arena-1"

# Release labels. The judge never sees these; they exist only on the
# evaluator side for remapping blinded A/B answers back to releases.
BETA = "beta"
PROD = "prod"
SIDES = (BETA, PROD)


class ExperimentMode(str, Enum):
    CONTROLLED_ENGINE = "controlled_engine"
    AS_DEPLOYED_PRODUCT = "as_deployed_product"
    RESPONSE_FORK = "response_fork"


class ArmStatus(str, Enum):
    COMPLETE = "complete"              # reached the fixed player-action horizon
    ENDED = "ended"                    # valid early game end observed
    TARGET_FAILURE = "target_failure"  # the game release failed (counts against it)
    PLAYER_FAILURE = "player_failure"  # evaluator-side failure (never scored)
    DRIFT = "drift"                    # target release changed mid-arm (invalid)
    CANCELLED = "cancelled"            # budget/cancel stop (partial, never scored)


SCORABLE_STATUSES = frozenset({ArmStatus.COMPLETE, ArmStatus.ENDED})


class Outcome(str, Enum):
    BETA_WIN = "beta_win"
    PROD_WIN = "prod_win"
    TIE = "tie"
    UNRESOLVED = "unresolved"
    BOTH_FAILED = "both_failed"
    INVALID = "invalid"                # drift/cancel/player failure: rerun, not scored


def stable_hash(payload: Any) -> str:
    """sha256 over canonical JSON; the identity used for manifests, rubrics
    and knowledge bundles."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def from_dict(cls, data: Mapping[str, Any]):
    """Build a flat dataclass from a dict, ignoring unknown keys so older
    artifacts stay readable after additive schema changes."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass(frozen=True)
class TargetIdentity:
    """What a deployed release says it is. `pin_key` is what must stay
    constant for a whole arm; any change invalidates that arm (§4)."""
    label: str
    base_url: str
    commit: str
    environment: str
    deployment_id: str = ""
    content_schema_version: int | None = None
    extractor_model: str = ""

    @property
    def pin_key(self) -> tuple:
        return (self.commit, self.deployment_id, self.content_schema_version)

    @property
    def is_pinnable(self) -> bool:
        """A release that reports neither a commit nor a deployment id cannot
        be pinned; results against it are labeled unpinned in the report."""
        return (self.commit not in ("", "unknown")) or bool(self.deployment_id)


@dataclass(frozen=True)
class PersonaSpec:
    id: str
    description: str


@dataclass(frozen=True)
class ScenarioSpec:
    """One authored starting condition. Both arms of a pair start here."""
    scenario_id: str
    story_id: str
    gender: str = "M"
    player_name: str = "Alex"
    max_player_turns: int = 8


@dataclass(frozen=True)
class PairSpec:
    """One independent statistical unit (§8): a paired scenario replicate."""
    pair_id: str
    scenario: ScenarioSpec
    persona: PersonaSpec
    replicate: int
    seed: int
    first_side: str

    def arm_id(self, side: str) -> str:
        return f"{self.pair_id}.{side}"

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "PairSpec":
        return cls(
            pair_id=data["pair_id"],
            scenario=from_dict(ScenarioSpec, data["scenario"]),
            persona=from_dict(PersonaSpec, data["persona"]),
            replicate=int(data["replicate"]),
            seed=int(data["seed"]),
            first_side=data["first_side"],
        )


@dataclass(frozen=True)
class ObservedState:
    """The subset of the player-facing `[D]` debug box the arena records.
    Available on both releases without operator credentials. Never shown to
    the player agent."""
    timestamp: str = ""
    location: str = ""
    location_uuid: str = ""
    speakers: tuple[str, ...] = ()


@dataclass
class TurnRecord:
    """One player action and the release's public answer (§6 TurnReceipt,
    observational subset: the server does not yet emit receipts)."""
    index: int
    player_message: str
    reply: str
    request_id: str
    latency_ms: int = 0
    speaker_ids: list[str] = field(default_factory=list)
    observed: ObservedState = field(default_factory=ObservedState)
    usage: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "TurnRecord":
        obs = data.get("observed") or {}
        return cls(
            index=int(data["index"]),
            player_message=data.get("player_message", ""),
            reply=data.get("reply", ""),
            request_id=data.get("request_id", ""),
            latency_ms=int(data.get("latency_ms") or 0),
            speaker_ids=list(data.get("speaker_ids") or []),
            observed=ObservedState(
                timestamp=obs.get("timestamp", ""),
                location=obs.get("location", ""),
                location_uuid=obs.get("location_uuid", ""),
                speakers=tuple(obs.get("speakers") or ()),
            ),
            usage=dict(data.get("usage") or {}),
            error=data.get("error", ""),
        )


@dataclass
class ArmTranscript:
    """Everything one side of a pair produced."""
    arm_id: str
    pair_id: str
    side: str
    identity_before: TargetIdentity
    identity_after: TargetIdentity | None
    opening: str
    opening_observed: ObservedState
    turns: list[TurnRecord]
    status: ArmStatus
    status_detail: str = ""
    player_usage: dict[str, int] = field(default_factory=dict)
    wall_ms: int = 0

    @property
    def scorable(self) -> bool:
        return self.status in SCORABLE_STATUSES

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ArmTranscript":
        after = data.get("identity_after")
        obs = data.get("opening_observed") or {}
        return cls(
            arm_id=data["arm_id"],
            pair_id=data["pair_id"],
            side=data["side"],
            identity_before=from_dict(TargetIdentity, data["identity_before"]),
            identity_after=from_dict(TargetIdentity, after) if after else None,
            opening=data.get("opening", ""),
            opening_observed=ObservedState(
                timestamp=obs.get("timestamp", ""),
                location=obs.get("location", ""),
                location_uuid=obs.get("location_uuid", ""),
                speakers=tuple(obs.get("speakers") or ()),
            ),
            turns=[TurnRecord.from_json(t) for t in data.get("turns") or []],
            status=ArmStatus(data["status"]),
            status_detail=data.get("status_detail", ""),
            player_usage=dict(data.get("player_usage") or {}),
            wall_ms=int(data.get("wall_ms") or 0),
        )


@dataclass(frozen=True)
class Budget:
    """Hard ceilings (§10). A stopped batch is partial, never complete."""
    max_game_turns: int = 400
    max_wall_seconds: int = 3600
    max_judge_input_tokens: int = 5_000_000
    max_player_tokens: int = 2_000_000


@dataclass(frozen=True)
class ExperimentManifest:
    """Immutable identity of one experiment, written before execution (§4)."""
    experiment_id: str
    created_at: str
    mode: str
    targets: dict[str, dict[str, Any]]
    judge_model: str
    rubric_version: str
    rubric_hash: str
    evaluator_commit: str
    player_model: str
    player_prompt_version: str
    knowledge_bundles: dict[str, str]          # story_id -> bundle hash
    pairs: list[dict[str, Any]]
    seed: int
    window_turns: int
    budget: dict[str, int]
    capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)  # side -> /api/eval/capabilities
    judges: dict[str, dict[str, Any]] = field(default_factory=dict)        # name -> {kind, model, window_turns}
    calibration_version: str = "uncalibrated"
    observational: bool = True                 # no server receipts/snapshots yet
    schema_version: str = ARENA_SCHEMA_VERSION
    notes: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["notes"] = list(self.notes)
        return data

    @property
    def manifest_hash(self) -> str:
        return stable_hash(self.to_json())

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ExperimentManifest":
        return from_dict(cls, {**data, "notes": tuple(data.get("notes") or ())})

    def pair_specs(self) -> list[PairSpec]:
        return [PairSpec.from_json(p) for p in self.pairs]
