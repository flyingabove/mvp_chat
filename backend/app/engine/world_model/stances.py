"""Stances: what one character thinks of another, derived from their own view and never written by the LLM (P-08, BL-85).

A `Stance` is "Ann has a crush on Ben", "Cat is Ann's rival for Ben", "Ann distrusts Dan": a typed, explainable
attitude with a strength and the causes behind it. Stances are recomputed from scratch every turn from rules
(`rules/stance_defaults.json`, a generic pack a story may override under `stances.rules`). A rule is a weighted sum
of conditions from the closed language in `rules/conditions.py`, judged from the HOLDER's viewpoint, so a hidden
feeling of somebody else never moves an opinion, while something the holder witnessed does. The sum is the strength;
the stance exists when it reaches the rule's `min_strength`.

Rules run in listed order and later rules see the stances earlier ones just produced (`has_stance`), which is how a
rival ("my crush is also your crush") falls out of two crushes. A `triple` rule names the stance (`about_has`) that
supplies its third party, so the cost stays small: it only looks at the holder's existing targets.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.app.engine.rules.conditions import Condition, Viewpoint, parse

DEFAULTS_PATH = Path(__file__).resolve().parents[1] / "rules" / "stance_defaults.json"
SCOPES = ("pair", "triple")
FAMILIES = ("", "romance", "rivalry")
PLAYER = "player"


@dataclass(frozen=True)
class Stance:
    kind: str
    holder: str
    target: str
    strength: float
    about: str = ""                      # the third party of a triple stance (a rival *for* someone)
    cause_ids: tuple[str, ...] = ()      # "rule#term" labels of the terms that held, then the world events they rest on
    since_day: int = 0

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.holder, self.kind, self.target, self.about)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "holder": self.holder, "target": self.target, "strength": self.strength,
                "about": self.about, "cause_ids": list(self.cause_ids), "since_day": self.since_day}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Stance":
        return cls(str(data["kind"]), str(data["holder"]), str(data["target"]), float(data.get("strength") or 0.0),
                   str(data.get("about") or ""), tuple(str(c) for c in data.get("cause_ids") or ()),
                   int(data.get("since_day") or 0))


@dataclass
class StanceBook:
    """Every stance currently held, replaced wholesale by `refresh_stances` each turn."""
    items: dict[tuple[str, str, str, str], Stance] = field(default_factory=dict)

    def add(self, stance: Stance) -> None:
        self.items[stance.key] = stance

    def has(self, holder: Optional[str], kind: str, target: Optional[str], about: str = "", minimum: float = 0.0) -> bool:
        stance = self.items.get((holder or "", kind, target or "", about or ""))
        return stance is not None and stance.strength >= minimum - 1e-9

    def strength(self, holder: str, kind: str, target: str, about: str = "") -> float:
        stance = self.items.get((holder, kind, target, about))
        return stance.strength if stance is not None else 0.0

    def of(self, holder: str, kind: str = "") -> list[Stance]:
        """The holder's stances, strongest first (ties by target)."""
        return sorted((s for s in self.items.values() if s.holder == holder and (not kind or s.kind == kind)),
                      key=lambda s: (-s.strength, s.target, s.about))

    def toward(self, target: str, kind: str = "") -> list[Stance]:
        return sorted((s for s in self.items.values() if s.target == target and (not kind or s.kind == kind)),
                      key=lambda s: (-s.strength, s.holder, s.about))

    def to_dict(self) -> dict[str, Any]:
        return {"stances": [s.to_dict() for _, s in sorted(self.items.items())]}

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "StanceBook":
        book = cls()
        for row in (data or {}).get("stances") or ():
            book.add(Stance.from_dict(row))
        return book


@dataclass(frozen=True)
class Term:
    weight: float
    condition: Condition


@dataclass(frozen=True)
class StanceRule:
    id: str
    kind: str
    scope: str
    min_strength: float
    terms: tuple[Term, ...]
    about_has: str = ""
    family: str = ""        # "romance" | "rivalry" | "": which story intensity knob scales this stance's strength


class MissingVariable(ValueError):
    """A rule names a `$variable` the story does not declare (a default rule then simply does not apply)."""


def _fill(value: Any, variables: dict[str, str]) -> Any:
    """Replace `$name` strings (a whole string only) with the story's own value, recursively."""
    if isinstance(value, str) and value.startswith("$"):
        if value[1:] not in variables:
            raise MissingVariable(f"stance rule uses {value} but the story does not declare it")
        return variables[value[1:]]
    if isinstance(value, dict):
        return {k: _fill(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, variables) for v in value]
    return value


def parse_rules(raw_rules: Iterable[dict[str, Any]], variables: dict[str, str]) -> tuple[StanceRule, ...]:
    """Validate and build rules; bad content raises ValueError naming the rule."""
    rules: list[StanceRule] = []
    for raw in raw_rules:
        rid = str((raw or {}).get("id") or "").strip()
        if not rid:
            raise ValueError(f"stance rule needs an id: {raw!r}")
        if any(r.id == rid for r in rules):
            raise ValueError(f"duplicate stance rule id {rid!r}")
        where = f"stance rule {rid!r}"
        kind = str(raw.get("kind") or "").strip()
        if not kind:
            raise ValueError(f"{where} needs a kind")
        scope = str(raw.get("scope") or "pair")
        if scope not in SCOPES:
            raise ValueError(f"{where}: scope must be one of {list(SCOPES)}")
        about_has = str(raw.get("about_has") or "")
        if scope == "triple" and not about_has:
            raise ValueError(f"{where}: a triple rule needs about_has (the stance that supplies the third party)")
        try:
            minimum = float(raw.get("min_strength"))
        except (TypeError, ValueError):
            raise ValueError(f"{where} needs a numeric min_strength") from None
        terms = []
        for index, item in enumerate(raw.get("when") or ()):
            try:
                weight = float(item.get("weight"))
            except (TypeError, ValueError, AttributeError):
                raise ValueError(f"{where}: term {index} needs a numeric weight") from None
            try:
                terms.append(Term(weight, parse(_fill(item.get("if"), variables))))
            except MissingVariable as exc:
                raise MissingVariable(f"{where}: term {index}: {exc}") from None
            except ValueError as exc:
                raise ValueError(f"{where}: term {index}: {exc}") from None
        if not terms:
            raise ValueError(f"{where} needs at least one term in 'when'")
        family = str(raw.get("family") or "")
        if family not in FAMILIES:
            raise ValueError(f"{where}: family must be one of {list(FAMILIES)}")
        rules.append(StanceRule(rid, kind, scope, minimum, tuple(terms), about_has, family))
    return tuple(rules)


def stance_rules(story_cfg: dict[str, Any], variables: dict[str, str]) -> tuple[StanceRule, ...]:
    """The generic pack with the story's overrides: a rule with the same id replaces the default, a new id is added,
    `"disabled": true` removes one."""
    defaults = {r["id"]: r for r in json.loads(DEFAULTS_PATH.read_text("utf-8"))["rules"]}
    own = {str((r or {}).get("id") or ""): r for r in ((story_cfg or {}).get("stances") or {}).get("rules") or ()}
    rules: list[StanceRule] = []
    for rid, raw in {**defaults, **own}.items():
        if raw.get("disabled"):
            continue
        try:
            rules.extend(parse_rules([raw], variables))
        except MissingVariable:
            if rid in own:
                raise              # the author's own rule must be complete; a default just does not apply to this story
    return tuple(rules)


def refresh_stances(model: Any, rules: Iterable[StanceRule], *, graph: Any, people: Any, eligible: Any,
                    levels: Any, day: int, intensity: Any = None) -> StanceBook:
    """Recompute every stance from the holders' own views and store it on the model. Pure: same model, same book."""
    previous, book = model.stances, StanceBook()
    model.stances = book                     # rules read the book as it fills, so later rules build on earlier ones
    try:
        holders = sorted(model.characters)
        subjects = [*holders, PLAYER]
        for rule in rules:
            for holder in holders:
                if rule.scope == "pair":
                    pairs = [(subject, None) for subject in subjects if subject != holder]
                else:
                    pairs = [(subject, s.target) for s in book.of(holder, rule.about_has) for subject in holders
                             if subject not in (holder, s.target)]
                for subject, third in pairs:
                    vp = Viewpoint(model=model, holder=holder, subject=subject, graph=graph, standings=model.standing,
                                   third=third, people=people, eligible=eligible, levels=levels)
                    _judge(book, previous, rule, vp, third or "", day, _scale(rule, intensity))
    except Exception:
        model.stances = previous
        raise
    return book


def _scale(rule: StanceRule, intensity: Any) -> float:
    """The story's intensity for this rule's family (1.0 when the rule has none or no intensity was given)."""
    return float(getattr(intensity, rule.family, 1.0)) if intensity is not None and rule.family else 1.0


def _judge(book: StanceBook, previous: StanceBook, rule: StanceRule, vp: Viewpoint, about: str, day: int,
           scale: float = 1.0) -> None:
    strength, causes = 0.0, []
    for index, term in enumerate(rule.terms):
        if term.condition.evaluate(vp) is True:
            strength += term.weight
            causes.append(f"{rule.id}#{index}")
            causes.extend(term.condition.causes(vp))
    if strength <= 0 or strength < rule.min_strength - 1e-9 or scale <= 0:
        return                              # the stance forms on the unscaled sum; intensity then sets how strong it is
    strength *= scale
    key = (vp.holder, rule.kind, vp.subject, about)
    before = previous.items.get(key)
    book.add(Stance(rule.kind, vp.holder, vp.subject, round(strength, 3), about, tuple(dict.fromkeys(causes)),
                    before.since_day if before is not None else day))


def refresh_stances_for_state(state: Any, model: Any, ctx: Any, now: int) -> None:
    """Recompute the model's stances for a game state; a story with no social tracks has none."""
    if ctx is None:
        return
    from backend.app.engine.rules.acquaintance import acquaintance_levels
    from backend.app.engine.rules.personality import personalities
    cfg = getattr(state, "story_cfg", None) or {}
    variables = {"track": ctx.rules.appraisal.track}
    if ctx.rules.couples is not None:
        variables.update(interested=ctx.rules.couples.interested_tier, dating=ctx.rules.couples.dating_tier)
    model.standing.bind(ctx.rules.tracks)
    refresh_stances(model, stance_rules(cfg, variables), graph=getattr(state, "character_graph", None),
                    people=personalities(cfg), eligible=ctx.eligible, levels=acquaintance_levels(cfg),
                    day=model.world.day_index(now), intensity=ctx.rules.intensity)
