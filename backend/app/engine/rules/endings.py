"""Typed endings: which one fired, once, from committed decisions.

A story declares `endings` in JSON; stories that do not get defaults derived
from the decisions the engine already records (mutual/solo departure) or, for
legacy mystery content, an explicit reply-regex condition. Scores never end a
game on their own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

KINDS = frozenset({"win", "loss", "neutral"})
KIND_LABELS = {"win": "You won", "loss": "Game over", "neutral": "Story ended"}


@dataclass(frozen=True)
class EndingFacts:
    """What the engine has committed this turn, read once per evaluation."""
    world_outcome: str = ""
    partner_id: str = ""
    reply: str = ""
    counters: dict[str, int] = field(default_factory=dict)


def _check_condition(condition: dict[str, Any]) -> None:
    kind = condition.get("kind")
    if kind == "world_outcome":
        if not str(condition.get("equals") or ""):
            raise ValueError("world_outcome condition needs 'equals'")
    elif kind == "legacy_reply_regex":
        patterns = condition.get("patterns")
        if not isinstance(patterns, list) or not patterns:
            raise ValueError("legacy_reply_regex condition needs non-empty 'patterns'")
        for pattern in patterns:
            re.compile(pattern)
    elif kind == "counter_at_least":
        if not str(condition.get("counter") or "") or int(condition.get("value") or 0) < 1:
            raise ValueError("counter_at_least condition needs 'counter' and 'value' >= 1")
    else:
        raise ValueError(f"unknown ending condition kind {kind!r}")


@dataclass(frozen=True)
class Ending:
    id: str
    kind: str
    title: str
    summary: str
    condition: dict[str, Any]
    ends_run: bool = True

    def __post_init__(self) -> None:
        if not self.id or self.kind not in KINDS:
            raise ValueError(f"ending needs an id and kind in {sorted(KINDS)}: {self.id!r}/{self.kind!r}")
        _check_condition(self.condition)

    def holds(self, facts: EndingFacts) -> bool:
        kind = self.condition["kind"]
        if kind == "world_outcome":
            return facts.world_outcome == self.condition["equals"]
        if kind == "counter_at_least":
            return facts.counters.get(self.condition["counter"], 0) >= int(self.condition["value"])
        return any(re.search(p, facts.reply or "", re.I) for p in self.condition["patterns"])

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Ending":
        return cls(str(raw.get("id") or ""), str(raw.get("kind") or ""), str(raw.get("title") or ""),
                   str(raw.get("summary") or ""), dict(raw.get("when") or {}), bool(raw.get("ends_run", True)))


@dataclass
class Outcome:
    ending_id: str
    kind: str
    title: str
    summary: str
    turn: int
    minute: int
    ends_run: bool = True
    partner_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ending_id": self.ending_id, "kind": self.kind, "title": self.title, "summary": self.summary,
                "turn": self.turn, "minute": self.minute, "ends_run": self.ends_run, "partner_id": self.partner_id}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Outcome":
        return cls(str(raw["ending_id"]), str(raw["kind"]), str(raw.get("title") or ""),
                   str(raw.get("summary") or ""), int(raw.get("turn") or 0), int(raw.get("minute") or 0),
                   bool(raw.get("ends_run", True)), str(raw.get("partner_id") or ""))

    def payload(self) -> dict[str, Any]:
        """Player-facing ending card data (no internal ids beyond the ending id)."""
        return {"id": self.ending_id, "kind": self.kind, "label": KIND_LABELS[self.kind], "title": self.title,
                "summary": self.summary, "turns": self.turn, "ends_run": self.ends_run}


def endings_for(story_cfg: dict[str, Any]) -> list[Ending]:
    """Declared endings in order, else defaults derived from the story's goal mechanics."""
    cfg = story_cfg or {}
    declared = cfg.get("endings")
    if declared:
        endings = [Ending.from_dict(item) for item in declared]
        ids = [e.id for e in endings]
        if len(ids) != len(set(ids)):
            raise ValueError("ending ids must be unique")
        return endings
    endings: list[Ending] = []
    if ((cfg.get("mode") or {}).get("romance_goal") or {}).get("enabled"):
        endings.append(Ending("left_together", "win", "You left together",
                              "You and {partner} both chose to leave the house together.",
                              {"kind": "world_outcome", "equals": "mutual_departure"}))
    patterns = (cfg.get("win_detection") or {}).get("regex") or []
    if patterns:
        endings.append(Ending("confession", "win", "Case closed",
                              "The one behind it all admitted what they did.",
                              {"kind": "legacy_reply_regex", "patterns": list(patterns)}))
    return endings


def evaluate(endings: list[Ending], facts: EndingFacts) -> Optional[Ending]:
    return next((e for e in endings if e.holds(facts)), None)


def resolve_outcome(state: Any, reply: str) -> Optional[Outcome]:
    """The ending this turn reached, or None. Fires at most once per game."""
    if getattr(state, "outcome", None):
        return None
    model = getattr(state, "world_model", None)
    facts = EndingFacts(
        world_outcome=str(getattr(model, "romance_outcome", "") or ""),
        partner_id=str(getattr(model, "romance_relationship_partner", "") or ""),
        reply=reply,
        counters=dict(getattr(model, "counters", {}) or {}) if model is not None else {},
    )
    ending = evaluate(endings_for(getattr(state, "story_cfg", {}) or {}), facts)
    if ending is None:
        return None
    partner_name = _name(state, facts.partner_id) if facts.partner_id else "your partner"
    return Outcome(ending.id, ending.kind, ending.title, ending.summary.replace("{partner}", partner_name),
                   int(getattr(state, "turns", 0) or 0), int(getattr(state, "minute", 0) or 0),
                   ending.ends_run, facts.partner_id if ending.kind == "win" else "")


def goal_payload(state: Any) -> Optional[dict[str, Any]]:
    """Player-facing goal card: the authored goal plus progress the player has actually seen."""
    cfg = getattr(state, "story_cfg", {}) or {}
    text = str((cfg.get("goal") or {}).get("win_text_rule") or "").strip()
    if not text:
        return None
    card: dict[str, Any] = {"text": text}
    if ((cfg.get("mode") or {}).get("romance_goal") or {}).get("enabled"):
        model = getattr(state, "world_model", None)
        partner = str(getattr(model, "romance_relationship_partner", "") or "") if model is not None else ""
        card["status"] = (f"You and {_name(state, partner)} are together. Now you both need to choose to leave."
                          if partner else "No mutual relationship yet.")
    return card


def _name(state: Any, cid: str) -> str:
    character = (getattr(state, "characters", {}) or {}).get(cid)
    return str(getattr(character, "name", "") or cid.replace("_", " ").title())
