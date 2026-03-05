# backend/app/engine/invariant_validator.py
"""
Post-generation invariant validator.

Checks model output for canon violations (anchor contradictions, identity drift).
This is a best-effort heuristic — it catches common patterns but cannot
guarantee perfect detection (pronoun coreference is inherently fuzzy).

Each check is unit-testable in isolation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Lightweight standalone types (no v2 schema dependency)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnchorFact:
    """An identity or fact anchor used for invariant checking."""
    id: str
    text: str
    entities: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    is_identity: bool = False


@dataclass(frozen=True)
class InvariantCheck:
    """Specifies what to check."""
    type: str           # "ANCHOR_CONTRADICTION" or "SPEAKER_IDENTITY_DRIFT"
    description: str = ""
    anchor_id: str = ""


@dataclass
class InvariantContract:
    """Lightweight contract for validation (replaces v2 TurnContract)."""
    speaker_id: str = ""
    anchors: List[AnchorFact] = field(default_factory=list)
    checks: List[InvariantCheck] = field(default_factory=list)


@dataclass(frozen=True)
class Violation:
    invariant_type: str
    description: str
    matched_text: str = ""
    chunk_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_response(contract: InvariantContract, text: str) -> List[Violation]:
    """Check model output against the contract's invariant checks.

    Returns a list of Violation objects (empty = clean).
    """
    violations: List[Violation] = []

    for check in contract.checks:
        if check.type == "ANCHOR_CONTRADICTION":
            violations.extend(_check_anchor_contradiction(check, contract, text))
        elif check.type == "SPEAKER_IDENTITY_DRIFT":
            violations.extend(_check_identity_drift(contract, text))

    return violations


def build_contract_from_story(
    story_cfg: dict,
    main_character_key: str = "",
) -> InvariantContract:
    """Build an InvariantContract from v1 story config data.

    Extracts identity anchors from character_self_knowledge and characters list.
    """
    anchors: List[AnchorFact] = []
    checks: List[InvariantCheck] = []

    # Extract character info for the main character
    characters = story_cfg.get("characters") or []
    char_name = ""
    char_tags: List[str] = []
    for ch in characters:
        if ch.get("is_main") or ch.get("key") == main_character_key:
            char_name = ch.get("name", "")
            char_tags = list(ch.get("tags") or [])
            break

    # Build identity anchor from character_self_knowledge
    self_knowledge = story_cfg.get("character_self_knowledge") or []
    if self_knowledge and char_name:
        combined_text = " ".join(self_knowledge)
        anchor = AnchorFact(
            id="anchor_identity",
            text=combined_text,
            entities=[char_name] if char_name else [],
            tags=char_tags,
            is_identity=True,
        )
        anchors.append(anchor)
        checks.append(InvariantCheck(
            type="ANCHOR_CONTRADICTION",
            description=f"Must not contradict identity: {char_name}",
            anchor_id="anchor_identity",
        ))
        checks.append(InvariantCheck(
            type="SPEAKER_IDENTITY_DRIFT",
            description="Must not refer to self in third person",
        ))

    return InvariantContract(
        speaker_id=main_character_key,
        anchors=anchors,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# ANCHOR_CONTRADICTION: speaker directly denies an anchor fact
# ---------------------------------------------------------------------------

_DENIAL_PATTERNS = [
    # "I'm not X", "I am not X"
    r"I(?:'m| am)\s+not\s+{name}",
    # "I was never X"
    r"I\s+was\s+never\s+{name}",
    # "I'm not a ghost", "I am not a ghost"
    r"I(?:'m| am)\s+not\s+a\s+{name}",
]


def _check_anchor_contradiction(
    check: InvariantCheck,
    contract: InvariantContract,
    text: str,
) -> List[Violation]:
    """Check if the text directly denies an anchor's content."""
    violations: List[Violation] = []

    anchor_id = check.anchor_id
    if not anchor_id:
        return violations

    # Find the anchor
    anchor: Optional[AnchorFact] = None
    for a in contract.anchors:
        if a.id == anchor_id:
            anchor = a
            break
    if anchor is None:
        return violations

    # Extract key entities/names from the anchor for denial checking
    names_to_check: List[str] = list(anchor.entities)
    names_to_check.extend(anchor.aliases)

    # Also extract names from the text itself
    identity_match = re.search(r"you are\s+(\w+)", anchor.text, re.IGNORECASE)
    if identity_match:
        names_to_check.append(identity_match.group(1))

    descriptor_match = re.search(r"you are\s+a\s+(\w+)", anchor.text, re.IGNORECASE)
    if descriptor_match:
        names_to_check.append(descriptor_match.group(1))

    for name in names_to_check:
        if not name.strip():
            continue
        for pattern_template in _DENIAL_PATTERNS:
            pattern = pattern_template.format(name=re.escape(name.strip()))
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                violations.append(Violation(
                    invariant_type="ANCHOR_CONTRADICTION",
                    description=f"Denies anchor '{anchor_id}': {match.group()}",
                    matched_text=match.group(),
                    chunk_id=anchor_id,
                ))
                break  # one match per name is enough

    return violations


# ---------------------------------------------------------------------------
# SPEAKER_IDENTITY_DRIFT: third-person self-reference
# ---------------------------------------------------------------------------

_THIRD_PERSON_FEMALE = [
    r"\bshe\s+was\b",
    r"\bshe\s+is\b",
    r"\bshe\s+had\b",
    r"\bshe\s+has\b",
    r"\bshe\s+didn'?t\b",
    r"\bshe\s+doesn'?t\b",
    r"\bshe\s+would\b",
    r"\bshe\s+could\b",
    r"\bshe\s+can\b",
    r"\bher\s+(?:name|life|death|story|memory|soul|spirit|presence)\b",
]

_THIRD_PERSON_MALE = [
    r"\bhe\s+was\b",
    r"\bhe\s+is\b",
    r"\bhe\s+had\b",
    r"\bhe\s+has\b",
    r"\bhe\s+didn'?t\b",
    r"\bhe\s+doesn'?t\b",
    r"\bhe\s+would\b",
    r"\bhe\s+could\b",
    r"\bhe\s+can\b",
    r"\bhis\s+(?:name|life|death|story|memory|soul|spirit|presence)\b",
]


def _check_identity_drift(
    contract: InvariantContract,
    text: str,
) -> List[Violation]:
    """Check if the speaker refers to themselves in third person."""
    violations: List[Violation] = []

    # Collect identity anchor names
    identity_names: List[str] = []
    for anchor in contract.anchors:
        if anchor.is_identity:
            identity_names.extend(anchor.entities)
            identity_names.extend(anchor.aliases)
            m = re.search(r"you are\s+(\w+)", anchor.text, re.IGNORECASE)
            if m:
                identity_names.append(m.group(1))

    if not identity_names:
        return violations

    # Determine gender hint from anchor tags
    all_tags: List[str] = []
    for anchor in contract.anchors:
        all_tags.extend(anchor.tags)

    pronoun_patterns = _THIRD_PERSON_FEMALE + _THIRD_PERSON_MALE
    if "female" in all_tags:
        pronoun_patterns = _THIRD_PERSON_FEMALE
    elif "male" in all_tags:
        pronoun_patterns = _THIRD_PERSON_MALE

    for name in identity_names:
        if not name.strip():
            continue
        name_pattern = re.escape(name.strip())
        for pp in pronoun_patterns:
            combined = rf"(?:{name_pattern}\b.{{0,100}}?{pp}|{pp}.{{0,100}}?\b{name_pattern}\b)"
            match = re.search(combined, text, re.IGNORECASE | re.DOTALL)
            if match:
                violations.append(Violation(
                    invariant_type="SPEAKER_IDENTITY_DRIFT",
                    description=f"Third-person self-reference detected near '{name}': {match.group()[:80]}",
                    matched_text=match.group()[:120],
                ))
                return violations  # one drift violation is enough

    return violations
