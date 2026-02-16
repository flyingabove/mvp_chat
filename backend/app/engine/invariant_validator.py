# backend/app/engine/invariant_validator.py
"""
Post-generation invariant validator.

Checks model output for canon violations defined by the TurnContract.
This is a best-effort heuristic — it catches common patterns but cannot
guarantee perfect detection (pronoun coreference is inherently fuzzy).

Each check is unit-testable in isolation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from backend.app.engine.story_schema_v2 import ChunkType, KnowledgeChunk
from backend.app.engine.turn_contract import Invariant, TurnContract


@dataclass(frozen=True)
class Violation:
    invariant_type: str
    description: str
    matched_text: str = ""
    chunk_id: Optional[str] = None


def validate_response(contract: TurnContract, text: str) -> List[Violation]:
    """Check model output against the contract's invariants.

    Returns a list of Violation objects (empty = clean).
    """
    violations: List[Violation] = []

    for inv in contract.invariants:
        if inv.type == "ANCHOR_CONTRADICTION":
            violations.extend(_check_anchor_contradiction(inv, contract, text))
        elif inv.type == "SPEAKER_IDENTITY_DRIFT":
            violations.extend(_check_identity_drift(contract, text))

    return violations


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
    inv: Invariant,
    contract: TurnContract,
    text: str,
) -> List[Violation]:
    """Check if the text directly denies an anchor's content."""
    violations: List[Violation] = []

    chunk_id = inv.chunk_id
    if not chunk_id:
        return violations

    # Find the anchor chunk
    anchor: Optional[KnowledgeChunk] = None
    for a in contract.injected_anchors:
        if a.id == chunk_id:
            anchor = a
            break
    if anchor is None:
        return violations

    # Extract key entities/names from the anchor for denial checking
    names_to_check: List[str] = list(anchor.content.entities)
    names_to_check.extend(anchor.content.aliases)

    # Also extract names from the text itself
    # For identity anchors like "You are IU", extract the name
    identity_match = re.search(r"you are\s+(\w+)", anchor.content.text, re.IGNORECASE)
    if identity_match:
        names_to_check.append(identity_match.group(1))

    # For anchors like "You are a ghost", extract the descriptor
    descriptor_match = re.search(r"you are\s+a\s+(\w+)", anchor.content.text, re.IGNORECASE)
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
                    description=f"Denies anchor '{chunk_id}': {match.group()}",
                    matched_text=match.group(),
                    chunk_id=chunk_id,
                ))
                break  # one match per name is enough

    return violations


# ---------------------------------------------------------------------------
# SPEAKER_IDENTITY_DRIFT: third-person self-reference
# ---------------------------------------------------------------------------

# Pronouns that indicate third-person reference to a female character
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

# Male equivalents
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
    contract: TurnContract,
    text: str,
) -> List[Violation]:
    """Check if the speaker refers to themselves in third person.

    This is heuristic — it looks for third-person pronouns near identity
    anchor names. False positives are possible when discussing other characters.
    """
    violations: List[Violation] = []

    # Collect identity anchor names
    identity_names: List[str] = []
    for anchor in contract.injected_anchors:
        if anchor.type == ChunkType.IDENTITY:
            identity_names.extend(anchor.content.entities)
            identity_names.extend(anchor.content.aliases)
            m = re.search(r"you are\s+(\w+)", anchor.content.text, re.IGNORECASE)
            if m:
                identity_names.append(m.group(1))

    if not identity_names:
        return violations

    # Determine gender hint from anchor tags
    all_tags: List[str] = []
    for anchor in contract.injected_anchors:
        all_tags.extend(anchor.tags)

    # Default to checking both pronoun sets; narrow if gender tag exists
    pronoun_patterns = _THIRD_PERSON_FEMALE + _THIRD_PERSON_MALE
    if "female" in all_tags:
        pronoun_patterns = _THIRD_PERSON_FEMALE
    elif "male" in all_tags:
        pronoun_patterns = _THIRD_PERSON_MALE

    for name in identity_names:
        if not name.strip():
            continue
        # Check: "she was trapped" style (pronoun near identity name)
        # Look for name + pronoun pattern within 100 chars
        name_pattern = re.escape(name.strip())
        for pp in pronoun_patterns:
            # Name followed by pronoun context (within ~100 chars)
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
