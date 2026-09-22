"""Pure runtime domain for stories with a rotating authored cast.

This module deliberately does not mutate world locations, prompt markers, or
character graphs.  Callers apply those integration effects from the returned
transition record after the lifecycle operation succeeds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import secrets
from typing import Any, Iterable, Mapping, Optional


class CastStatus(str, Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPARTED = "departed"


_ALLOWED_DEPARTURE_POLICIES = {"committed_intent"}
_ALLOWED_REPLACEMENT_TIMINGS = {"immediate", "next_day"}


@dataclass
class CastMemberState:
    status: CastStatus
    slot_group: str
    sequence: int
    activated_minute: Optional[int] = None
    departed_minute: Optional[int] = None
    departure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "slot_group": self.slot_group,
            "sequence": self.sequence,
            "activated_minute": self.activated_minute,
            "departed_minute": self.departed_minute,
            "departure_reason": self.departure_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CastMemberState":
        try:
            status = CastStatus(str(data.get("status", "")))
        except ValueError as exc:
            raise ValueError(f"unknown cast status: {data.get('status')!r}") from exc
        slot_group = str(data.get("slot_group") or "").strip()
        if not slot_group:
            raise ValueError("cast member slot_group must be non-empty")
        sequence = _non_negative_int(data.get("sequence"), "cast member sequence")
        return cls(
            status=status,
            slot_group=slot_group,
            sequence=sequence,
            activated_minute=_optional_non_negative_int(data.get("activated_minute"), "activated_minute"),
            departed_minute=_optional_non_negative_int(data.get("departed_minute"), "departed_minute"),
            departure_reason=str(data.get("departure_reason") or ""),
        )


@dataclass
class CastTransition:
    event_id: str
    event_type: str
    minute: int
    slot_group: str
    departing_id: Optional[str] = None
    arriving_id: Optional[str] = None
    reason: str = ""
    resulting_statuses: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "minute": self.minute,
            "slot_group": self.slot_group,
            "departing_id": self.departing_id,
            "arriving_id": self.arriving_id,
            "reason": self.reason,
            "resulting_statuses": dict(self.resulting_statuses),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CastTransition":
        event_id = str(data.get("event_id") or "").strip()
        event_type = str(data.get("event_type") or "").strip()
        if not event_id or not event_type:
            raise ValueError("cast transition requires event_id and event_type")
        return cls(
            event_id=event_id,
            event_type=event_type,
            minute=_non_negative_int(data.get("minute"), "transition minute"),
            slot_group=str(data.get("slot_group") or "").strip(),
            departing_id=_optional_id(data.get("departing_id")),
            arriving_id=_optional_id(data.get("arriving_id")),
            reason=str(data.get("reason") or ""),
            resulting_statuses={
                str(k): str(v) for k, v in (data.get("resulting_statuses") or {}).items()
            },
        )


@dataclass
class CastLifecycleState:
    enabled: bool
    arrival_location_id: str
    replacement_policy: str
    departure_policy: str
    slot_capacities: dict[str, int]
    slot_labels: dict[str, str]
    members: dict[str, CastMemberState]
    history: list[CastTransition] = field(default_factory=list)
    # How long after a confirmed departure the replacement actually arrives.
    # "immediate" preserves pre-Phase-2 behavior (default for any story/test
    # that omits this field); "next_day" defers execution to a day boundary
    # via the pending-events scheduler (see world_calendar.py).
    replacement_timing: str = "immediate"
    player_slot_group: str = ""
    require_replacement: bool = False

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        character_ids: Optional[Iterable[str]] = None,
        location_ids: Optional[Iterable[str]] = None,
    ) -> "CastLifecycleState":
        if not isinstance(config, Mapping):
            raise ValueError("cast_lifecycle must be an object")
        enabled = bool(config.get("enabled", False))
        arrival_location_id = str(config.get("arrival_location_id") or "").strip()
        replacement_policy = str(config.get("replacement_policy") or "same_slot_next").strip()
        departure_policy = str(config.get("departure_policy") or "committed_intent").strip()
        replacement_timing = str(config.get("replacement_timing") or "immediate").strip()
        if enabled and not arrival_location_id:
            raise ValueError("enabled cast_lifecycle requires arrival_location_id")
        if replacement_policy != "same_slot_next":
            raise ValueError(f"unsupported replacement_policy: {replacement_policy!r}")
        if departure_policy not in _ALLOWED_DEPARTURE_POLICIES:
            raise ValueError(f"unsupported departure_policy: {departure_policy!r}")
        if replacement_timing not in _ALLOWED_REPLACEMENT_TIMINGS:
            raise ValueError(f"unsupported replacement_timing: {replacement_timing!r}")

        raw_groups = config.get("slot_groups") or {}
        if not isinstance(raw_groups, Mapping) or (enabled and not raw_groups):
            raise ValueError("enabled cast_lifecycle requires slot_groups")
        capacities: dict[str, int] = {}
        labels: dict[str, str] = {}
        for raw_key, raw_value in raw_groups.items():
            key = str(raw_key).strip()
            if not key or not isinstance(raw_value, Mapping):
                raise ValueError("each slot group must have a non-empty id and object value")
            capacity = _positive_int(raw_value.get("capacity"), f"capacity for slot group {key!r}")
            capacities[key] = capacity
            labels[key] = str(raw_value.get("label") or key)

        allowed_characters = set(character_ids) if character_ids is not None else None
        raw_members = config.get("members") or {}
        if not isinstance(raw_members, Mapping):
            raise ValueError("cast_lifecycle members must be an object")
        members: dict[str, CastMemberState] = {}
        seen_sequences: set[tuple[str, int]] = set()
        for raw_id, raw_member in raw_members.items():
            character_id = str(raw_id).strip()
            if not character_id or not isinstance(raw_member, Mapping):
                raise ValueError("each lifecycle member must have a non-empty id and object value")
            if allowed_characters is not None and character_id not in allowed_characters:
                raise ValueError(f"lifecycle member {character_id!r} is not an authored character")
            slot_group = str(raw_member.get("slot_group") or "").strip()
            if slot_group not in capacities:
                raise ValueError(f"member {character_id!r} references unknown slot group {slot_group!r}")
            sequence = _non_negative_int(raw_member.get("sequence"), f"sequence for member {character_id!r}")
            sequence_key = (slot_group, sequence)
            if sequence_key in seen_sequences:
                raise ValueError(f"duplicate sequence {sequence} in slot group {slot_group!r}")
            seen_sequences.add(sequence_key)
            try:
                status = CastStatus(str(raw_member.get("initial_status") or "upcoming"))
            except ValueError as exc:
                raise ValueError(
                    f"member {character_id!r} has unknown initial_status {raw_member.get('initial_status')!r}"
                ) from exc
            members[character_id] = CastMemberState(
                status=status,
                slot_group=slot_group,
                sequence=sequence,
                activated_minute=0 if status is CastStatus.ACTIVE else None,
                departed_minute=0 if status is CastStatus.DEPARTED else None,
            )

        state = cls(
            enabled=enabled,
            arrival_location_id=arrival_location_id,
            replacement_policy=replacement_policy,
            departure_policy=departure_policy,
            slot_capacities=capacities,
            slot_labels=labels,
            members=members,
            replacement_timing=replacement_timing,
            require_replacement=bool(config.get("require_replacement", False)),
        )
        state._validate(location_ids=location_ids)
        return state

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CastLifecycleState":
        if not isinstance(data, Mapping):
            raise ValueError("cast lifecycle snapshot must be an object")
        raw_members = data.get("members") or {}
        raw_history = data.get("history") or []
        state = cls(
            enabled=bool(data.get("enabled", False)),
            arrival_location_id=str(data.get("arrival_location_id") or "").strip(),
            replacement_policy=str(data.get("replacement_policy") or "same_slot_next"),
            departure_policy=str(data.get("departure_policy") or "committed_intent"),
            slot_capacities={str(k): _positive_int(v, f"capacity for {k!r}") for k, v in (data.get("slot_capacities") or {}).items()},
            slot_labels={str(k): str(v) for k, v in (data.get("slot_labels") or {}).items()},
            members={str(k): CastMemberState.from_dict(v) for k, v in raw_members.items()},
            history=[CastTransition.from_dict(item) for item in raw_history],
            replacement_timing=str(data.get("replacement_timing") or "immediate"),
            player_slot_group=str(data.get("player_slot_group") or ""),
            require_replacement=bool(data.get("require_replacement", False)),
        )
        state._validate()
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "arrival_location_id": self.arrival_location_id,
            "replacement_policy": self.replacement_policy,
            "departure_policy": self.departure_policy,
            "slot_capacities": dict(self.slot_capacities),
            "slot_labels": dict(self.slot_labels),
            "members": {key: member.to_dict() for key, member in self.members.items()},
            "history": [transition.to_dict() for transition in self.history],
            "replacement_timing": self.replacement_timing,
            "player_slot_group": self.player_slot_group,
            "require_replacement": self.require_replacement,
        }

    def reserve_player_slot(self, slot_group: str) -> None:
        """Count the player as a resident, returning one NPC to the entry queue.

        Keep the player separate from NPC IDs so routines and dialogue never
        control them. Reapplying this on save restoration is idempotent.
        """
        self._require_slot(slot_group)
        if self.player_slot_group:
            if self.player_slot_group != slot_group:
                raise ValueError("player slot cannot change during a game")
            return
        active = self.active_ids(slot_group)
        if len(active) >= self.slot_capacities[slot_group]:
            displaced = self.members[active[-1]]
            displaced.status = CastStatus.UPCOMING
            displaced.activated_minute = None
        self.player_slot_group = slot_group
        self._validate()

    def choose_initial_roster(self, player_slot_group: str) -> None:
        """Randomly select a capacity-valid opening roster for a resident player.

        This is a reusable lifecycle primitive: each configured slot group is
        filled to capacity, except the player's group which reserves one of
        those spaces for the player. All non-selected authored members remain
        in the same-slot replacement queue.
        """
        self._require_slot(player_slot_group)
        if self.player_slot_group:
            raise ValueError("cannot choose an opening roster after reserving the player slot")
        chooser = secrets.SystemRandom()
        selected: set[str] = set()
        for group, capacity in self.slot_capacities.items():
            target = capacity - int(group == player_slot_group)
            candidates = sorted(
                key for key, member in self.members.items()
                if member.slot_group == group and member.status is not CastStatus.DEPARTED
            )
            if len(candidates) < target:
                raise ValueError(f"slot group {group!r} lacks enough members for its opening roster")
            selected.update(chooser.sample(candidates, target))

        for key, member in self.members.items():
            if member.status is CastStatus.DEPARTED:
                continue
            member.status = CastStatus.ACTIVE if key in selected else CastStatus.UPCOMING
            member.activated_minute = 0 if key in selected else None
            member.departed_minute = None
            member.departure_reason = ""
        self._validate()

    def active_ids(self, slot_group: Optional[str] = None) -> list[str]:
        if slot_group is not None:
            self._require_slot(slot_group)
        return sorted(
            (
                character_id for character_id, member in self.members.items()
                if member.status is CastStatus.ACTIVE
                and (slot_group is None or member.slot_group == slot_group)
            ),
            key=lambda character_id: (
                self.members[character_id].slot_group,
                self.members[character_id].sequence,
                character_id,
            ),
        )

    def is_scene_eligible(self, character_id: str) -> bool:
        member = self.members.get(character_id)
        return bool(self.enabled and member and member.status is CastStatus.ACTIVE)

    def vacancies(self, slot_group: str) -> int:
        self._require_slot(slot_group)
        return self.slot_capacities[slot_group] - len(self.active_ids(slot_group)) - int(self.player_slot_group == slot_group)

    def next_up(self, slot_group: str) -> Optional[str]:
        self._require_slot(slot_group)
        eligible = [
            character_id for character_id, member in self.members.items()
            if member.slot_group == slot_group and member.status is CastStatus.UPCOMING
        ]
        if not eligible:
            return None
        return min(eligible, key=lambda character_id: (self.members[character_id].sequence, character_id))

    def activate(self, character_id: str, minute: int) -> CastTransition:
        minute = _non_negative_int(minute, "activation minute")
        member = self._require_member(character_id)
        if member.status is CastStatus.ACTIVE:
            return self._record("activate", minute, member.slot_group, arriving_id=character_id)
        if member.status is CastStatus.DEPARTED:
            raise ValueError(f"departed member {character_id!r} cannot be reactivated")
        if self.vacancies(member.slot_group) <= 0:
            raise ValueError(f"slot group {member.slot_group!r} is at capacity")
        member.status = CastStatus.ACTIVE
        member.activated_minute = minute
        member.departed_minute = None
        member.departure_reason = ""
        return self._record("activate", minute, member.slot_group, arriving_id=character_id)

    def deactivate(self, character_id: str, minute: int, reason: str = "") -> CastTransition:
        if self.require_replacement:
            raise ValueError("a resident must leave through an atomic replacement")
        minute = _non_negative_int(minute, "deactivation minute")
        member = self._require_member(character_id)
        if member.status is not CastStatus.ACTIVE:
            raise ValueError(f"only an active member can be deactivated: {character_id!r}")
        member.status = CastStatus.INACTIVE
        return self._record("deactivate", minute, member.slot_group, departing_id=character_id, reason=reason)

    def propose_departure(self, character_id: str, *, minute: int, reason: str, event_id: str) -> CastTransition:
        """Record a DECLARED INTENTION to depart, without changing status.

        This is the "decision to leave next week is not immediate removal"
        state: the member stays ACTIVE (and scene-eligible) until the
        scheduler later calls ``replace()`` at the authored availability
        window. Idempotent by event_id (replaying returns the prior
        transition unchanged), matching ``replace()``'s own idempotency
        design so a retried turn cannot record the same proposal twice.
        """
        event_id = str(event_id or "").strip()
        if not event_id:
            raise ValueError("departure proposal event_id must be non-empty")
        prior = next((item for item in self.history if item.event_id == event_id), None)
        if prior is not None:
            return prior
        if not self.enabled:
            raise ValueError("cast lifecycle is disabled")
        minute = _non_negative_int(minute, "departure proposal minute")
        member = self._require_member(character_id)
        if member.status is not CastStatus.ACTIVE:
            raise ValueError(f"only an active member can propose departure: {character_id!r}")
        return self._record(
            "departure_proposed",
            minute,
            member.slot_group,
            departing_id=character_id,
            reason=reason,
            event_id=event_id,
        )

    def depart(self, character_id: str, minute: int, reason: str = "") -> CastTransition:
        if self.require_replacement:
            raise ValueError("a resident must leave through an atomic replacement")
        minute = _non_negative_int(minute, "departure minute")
        member = self._require_member(character_id)
        if member.status is not CastStatus.ACTIVE:
            raise ValueError(f"only an active member can depart: {character_id!r}")
        member.status = CastStatus.DEPARTED
        member.departed_minute = minute
        member.departure_reason = str(reason or "")
        return self._record("depart", minute, member.slot_group, departing_id=character_id, reason=reason)

    def replace(
        self,
        departing_id: str,
        *,
        minute: int,
        reason: str = "",
        event_id: str,
        arriving_id: Optional[str] = None,
    ) -> CastTransition:
        """Atomically depart one member and activate a same-slot successor.

        Replaying a previously applied ``event_id`` returns the original record
        without applying the transition again.
        """
        event_id = str(event_id or "").strip()
        if not event_id:
            raise ValueError("replacement event_id must be non-empty")
        prior = next((item for item in self.history if item.event_id == event_id), None)
        if prior is not None:
            return prior
        if not self.enabled:
            raise ValueError("cast lifecycle is disabled")
        minute = _non_negative_int(minute, "replacement minute")
        departing = self._require_member(departing_id)
        if departing.status is not CastStatus.ACTIVE:
            raise ValueError(f"replacement requires an active departing member: {departing_id!r}")
        slot_group = departing.slot_group
        self._require_slot(slot_group)

        chosen_id = str(arriving_id).strip() if arriving_id is not None else self.next_up(slot_group)
        if not chosen_id and self.require_replacement:
            raise ValueError("no same-slot replacement remains; resident stays in the house")
        chosen: Optional[CastMemberState] = None
        if chosen_id:
            chosen = self._require_member(chosen_id)
            if chosen.slot_group != slot_group:
                raise ValueError(
                    f"replacement member {chosen_id!r} belongs to {chosen.slot_group!r}, not {slot_group!r}"
                )
            if chosen.status is not CastStatus.UPCOMING:
                raise ValueError(f"replacement member {chosen_id!r} must be upcoming")
            if not self.arrival_location_id:
                raise ValueError("replacement arrival_location_id is missing")

        # All validation is complete. The two status mutations below form the
        # domain transaction; integrations run only after this method returns.
        departing.status = CastStatus.DEPARTED
        departing.departed_minute = minute
        departing.departure_reason = str(reason or "")
        if chosen is not None:
            chosen.status = CastStatus.ACTIVE
            chosen.activated_minute = minute
            chosen.departed_minute = None
            chosen.departure_reason = ""
        return self._record(
            "replace",
            minute,
            slot_group,
            departing_id=departing_id,
            arriving_id=chosen_id or None,
            reason=reason,
            event_id=event_id,
        )

    def _validate(self, location_ids: Optional[Iterable[str]] = None) -> None:
        if self.player_slot_group:
            self._require_slot(self.player_slot_group)
        if self.enabled and not self.arrival_location_id:
            raise ValueError("enabled cast lifecycle requires arrival_location_id")
        if self.replacement_policy != "same_slot_next":
            raise ValueError(f"unsupported replacement_policy: {self.replacement_policy!r}")
        if self.enabled and location_ids is not None and self.arrival_location_id not in set(location_ids):
            raise ValueError(f"arrival location {self.arrival_location_id!r} does not exist in the story world")
        seen_sequences: set[tuple[str, int]] = set()
        for character_id, member in self.members.items():
            self._require_slot(member.slot_group)
            key = (member.slot_group, member.sequence)
            if key in seen_sequences:
                raise ValueError(f"duplicate sequence {member.sequence} in slot group {member.slot_group!r}")
            seen_sequences.add(key)
            if member.status is CastStatus.DEPARTED and member.departed_minute is None:
                raise ValueError(f"departed member {character_id!r} requires departed_minute")
        for slot_group, capacity in self.slot_capacities.items():
            if capacity <= 0:
                raise ValueError(f"capacity for slot group {slot_group!r} must be positive")
            active_count = sum(
                member.status is CastStatus.ACTIVE and member.slot_group == slot_group
                for member in self.members.values()
            )
            active_count += int(self.player_slot_group == slot_group)
            if active_count > capacity:
                raise ValueError(
                    f"slot group {slot_group!r} has {active_count} active members but capacity {capacity}"
                )
        event_ids: set[str] = set()
        for transition in self.history:
            if transition.event_id in event_ids:
                raise ValueError(f"duplicate transition event_id: {transition.event_id!r}")
            event_ids.add(transition.event_id)

    def _require_member(self, character_id: str) -> CastMemberState:
        try:
            return self.members[character_id]
        except KeyError as exc:
            raise ValueError(f"unknown lifecycle member: {character_id!r}") from exc

    def _require_slot(self, slot_group: str) -> None:
        if slot_group not in self.slot_capacities:
            raise ValueError(f"unknown slot group: {slot_group!r}")

    def _record(
        self,
        event_type: str,
        minute: int,
        slot_group: str,
        *,
        departing_id: Optional[str] = None,
        arriving_id: Optional[str] = None,
        reason: str = "",
        event_id: Optional[str] = None,
    ) -> CastTransition:
        if event_id is None:
            event_id = f"{event_type}:{minute}:{departing_id or ''}:{arriving_id or ''}:{len(self.history)}"
        transition = CastTransition(
            event_id=event_id,
            event_type=event_type,
            minute=minute,
            slot_group=slot_group,
            departing_id=departing_id,
            arriving_id=arriving_id,
            reason=str(reason or ""),
            resulting_statuses={
                key: self.members[key].status.value
                for key in (departing_id, arriving_id)
                if key is not None
            },
        )
        self.history.append(transition)
        return transition


def _optional_id(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _positive_int(value: Any, label: str) -> int:
    result = _non_negative_int(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _optional_non_negative_int(value: Any, label: str) -> Optional[int]:
    if value is None:
        return None
    return _non_negative_int(value, label)
