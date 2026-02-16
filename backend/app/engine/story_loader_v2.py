# backend/app/engine/story_loader_v2.py
"""
Loader + validator for StoryPackageV2 JSON.

Validates referential integrity:
- Anchor chunk IDs exist in KnowledgeBase and have canon_tier=ANCHOR
- Relationship edge endpoints reference existing characters
- Objective required_chunk_ids reference existing chunks
- No duplicate IDs across chunks, characters, objectives
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from backend.app.engine.story_schema_v2 import (
    CanonTier,
    KnowledgeChunk,
    StoryPackageV2,
)
from backend.app.utils.logging_utils import jlog


class StoryLoadError(Exception):
    """Raised when a v2 story fails loading or validation."""


class ValidationError(StoryLoadError):
    """Raised when a loaded story fails referential integrity checks."""

    def __init__(self, violations: List[str]) -> None:
        self.violations = violations
        super().__init__(f"{len(violations)} validation error(s): {'; '.join(violations)}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(pkg: StoryPackageV2) -> List[str]:
    """Return a list of validation violation strings (empty = valid)."""
    violations: List[str] = []
    chunk_ids = set(pkg.knowledge.chunks.keys())
    char_ids = set(pkg.characters.keys())

    # 1. Anchor refs must exist and be ANCHOR tier
    for cid, char in pkg.characters.items():
        for aid in char.anchors.anchor_chunk_ids:
            if aid not in chunk_ids:
                violations.append(f"character '{cid}' references anchor chunk '{aid}' which does not exist")
            else:
                chunk = pkg.knowledge.chunks[aid]
                if chunk.canon_tier != CanonTier.ANCHOR:
                    violations.append(
                        f"character '{cid}' anchor '{aid}' has canon_tier={chunk.canon_tier.value}, expected ANCHOR"
                    )

    # 2. Epistemic chunk refs must exist
    for cid, char in pkg.characters.items():
        for kid in char.epistemic.known_chunk_ids:
            if kid not in chunk_ids:
                violations.append(f"character '{cid}' known_chunk_id '{kid}' does not exist")
        for bid in char.epistemic.believed_chunk_ids:
            if bid not in chunk_ids:
                violations.append(f"character '{cid}' believed_chunk_id '{bid}' does not exist")
        for fid in char.epistemic.forgotten_chunk_ids:
            if fid not in chunk_ids:
                violations.append(f"character '{cid}' forgotten_chunk_id '{fid}' does not exist")

    # 3. Relationship endpoints must exist
    for eid, edge in pkg.relationships.edges.items():
        if edge.from_character_id not in char_ids:
            violations.append(f"relationship '{eid}' from_character_id '{edge.from_character_id}' does not exist")
        if edge.to_character_id not in char_ids:
            violations.append(f"relationship '{eid}' to_character_id '{edge.to_character_id}' does not exist")
        for sid in edge.supporting_chunk_ids:
            if sid not in chunk_ids:
                violations.append(f"relationship '{eid}' supporting_chunk_id '{sid}' does not exist")

    # 4. Objective chunk refs must exist
    for obj in pkg.win_conditions.objectives:
        for rid in obj.required_chunk_ids:
            if rid not in chunk_ids:
                violations.append(f"objective '{obj.id}' required_chunk_id '{rid}' does not exist")

    # 5. Memory trigger unlock_chunk_ids must exist
    for cid, char in pkg.characters.items():
        for trigger in char.epistemic.memory_rules.triggers:
            for uid in trigger.unlock_chunk_ids:
                if uid not in chunk_ids:
                    violations.append(
                        f"character '{cid}' trigger '{trigger.id}' unlock_chunk_id '{uid}' does not exist"
                    )

    return violations


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_v2(path: str) -> StoryPackageV2:
    """Load a v2 story JSON from disk, parse, and validate.

    Raises StoryLoadError on I/O or parse failure.
    Raises ValidationError on referential integrity failure.
    """
    if not os.path.isfile(path):
        raise StoryLoadError(f"story file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise StoryLoadError(f"failed to parse {path}: {e}") from e

    if not isinstance(raw, dict):
        raise StoryLoadError(f"expected top-level JSON object in {path}")

    version = raw.get("version")
    if version is not None and int(version) < 2:
        raise StoryLoadError(f"expected version >= 2, got {version} in {path}")

    pkg = StoryPackageV2.from_dict(raw)
    violations = validate(pkg)
    if violations:
        jlog({"kind": "story_v2_validation_failed", "path": path, "violations": violations})
        raise ValidationError(violations)

    jlog({"kind": "story_v2_loaded", "story_id": pkg.story_id, "path": path})
    return pkg


def load_v2_from_dict(data: Dict[str, Any]) -> StoryPackageV2:
    """Load from an already-parsed dict (useful for tests)."""
    pkg = StoryPackageV2.from_dict(data)
    violations = validate(pkg)
    if violations:
        raise ValidationError(violations)
    return pkg
