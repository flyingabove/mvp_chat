# tests/backend/app/engine/test_story_loader_v2.py
"""Obsolete v2 tests disabled after production simplification."""

import pytest

pytest.skip("v2 story loader path removed from active product design", allow_module_level=True)
import json
import os
import tempfile

from backend.app.engine.story_loader_v2 import (
    StoryLoadError,
    ValidationError,
    load_v2,
    load_v2_from_dict,
    validate,
)
from backend.app.engine.story_schema_v2 import StoryPackageV2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_pkg_dict():
    return {
        "story_id": "test",
        "version": 2,
        "knowledge": {
            "chunks": {
                "anchor_id": {
                    "type": "IDENTITY",
                    "canon_tier": "ANCHOR",
                    "access": {"inject_every_turn": True},
                    "content": {"text": "You are IU.", "entities": ["IU"]},
                },
                "fact_1": {
                    "type": "FACT",
                    "canon_tier": "CANON",
                    "content": {"text": "The closet binds you."},
                },
                "secret_1": {
                    "type": "FACT",
                    "canon_tier": "SECRET_CANON",
                    "content": {"text": "Manager did it."},
                },
            },
        },
        "characters": {
            "iu": {
                "identity": {"display_name": "IU"},
                "anchors": {"anchor_chunk_ids": ["anchor_id"]},
                "epistemic": {
                    "known_chunk_ids": ["fact_1"],
                    "believed_chunk_ids": [],
                    "forgotten_chunk_ids": [],
                },
            },
        },
        "relationships": {
            "edges": {
                "e1": {"from": "iu", "to": "iu", "type": "OTHER"},
            },
        },
        "win_conditions": {
            "objectives": [
                {"id": "o1", "title": "Find truth", "required_chunk_ids": ["fact_1"]},
            ],
        },
    }


def _write_temp_json(data: dict) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------

def test_load_v2_valid_file():
    path = _write_temp_json(_valid_pkg_dict())
    try:
        pkg = load_v2(path)
        assert pkg.story_id == "test"
        assert "iu" in pkg.characters
    finally:
        os.unlink(path)


def test_load_v2_file_not_found():
    with pytest.raises(StoryLoadError, match="not found"):
        load_v2("/nonexistent/path.json")


def test_load_v2_invalid_json():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write("{not valid json")
    try:
        with pytest.raises(StoryLoadError, match="failed to parse"):
            load_v2(path)
    finally:
        os.unlink(path)


def test_load_v2_version_too_low():
    data = _valid_pkg_dict()
    data["version"] = 1
    path = _write_temp_json(data)
    try:
        with pytest.raises(StoryLoadError, match="version"):
            load_v2(path)
    finally:
        os.unlink(path)


def test_load_v2_from_dict_valid():
    pkg = load_v2_from_dict(_valid_pkg_dict())
    assert pkg.story_id == "test"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

def test_validate_valid_package():
    pkg = StoryPackageV2.from_dict(_valid_pkg_dict())
    violations = validate(pkg)
    assert violations == []


def test_validate_anchor_ref_missing():
    data = _valid_pkg_dict()
    data["characters"]["iu"]["anchors"]["anchor_chunk_ids"] = ["nonexistent"]
    pkg = StoryPackageV2.from_dict(data)
    violations = validate(pkg)
    assert any("nonexistent" in v and "does not exist" in v for v in violations)


def test_validate_anchor_ref_wrong_tier():
    data = _valid_pkg_dict()
    # Point anchor at a CANON chunk (not ANCHOR tier)
    data["characters"]["iu"]["anchors"]["anchor_chunk_ids"] = ["fact_1"]
    pkg = StoryPackageV2.from_dict(data)
    violations = validate(pkg)
    assert any("expected ANCHOR" in v for v in violations)


def test_validate_known_chunk_missing():
    data = _valid_pkg_dict()
    data["characters"]["iu"]["epistemic"]["known_chunk_ids"] = ["bogus"]
    pkg = StoryPackageV2.from_dict(data)
    violations = validate(pkg)
    assert any("bogus" in v for v in violations)


def test_validate_relationship_endpoint_missing():
    data = _valid_pkg_dict()
    data["relationships"]["edges"]["e1"]["from"] = "nonexistent_char"
    pkg = StoryPackageV2.from_dict(data)
    violations = validate(pkg)
    assert any("nonexistent_char" in v for v in violations)


def test_validate_objective_chunk_ref_missing():
    data = _valid_pkg_dict()
    data["win_conditions"]["objectives"][0]["required_chunk_ids"] = ["bogus"]
    pkg = StoryPackageV2.from_dict(data)
    violations = validate(pkg)
    assert any("bogus" in v for v in violations)


def test_validate_trigger_unlock_chunk_missing():
    data = _valid_pkg_dict()
    data["characters"]["iu"]["epistemic"]["memory_rules"] = {
        "triggers": [
            {"id": "t1", "condition": "mentions:closet", "unlock_chunk_ids": ["nonexistent"]},
        ],
    }
    pkg = StoryPackageV2.from_dict(data)
    violations = validate(pkg)
    assert any("nonexistent" in v for v in violations)


def test_validation_error_raises_on_load():
    data = _valid_pkg_dict()
    data["characters"]["iu"]["anchors"]["anchor_chunk_ids"] = ["bogus"]
    with pytest.raises(ValidationError) as exc_info:
        load_v2_from_dict(data)
    assert len(exc_info.value.violations) > 0
