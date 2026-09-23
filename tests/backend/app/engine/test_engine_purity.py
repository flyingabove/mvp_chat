"""Import-direction enforcement for backend/app/engine/.

Per the engineering plan's stated constraint ("the engine stays pure...
enforced by a test, not convention") and
JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §2: this test did not exist before
step 3 of the Jev implementation order — verified by search at design time.
It ships now, alongside the refactor that made turn_extractor.py compliant.

Two files remain on the allowlist below, explicitly, not silently:
  - location_extractor.py: legacy but still referenced by playback/tests,
    out of this refactor's scope.
  - knowledge_resolution_extractor.py: flagged by the audit as possibly
    unused on the live path; resolving that is separate follow-up work.
Shrinking this allowlist to empty is real future work, not a silent
expansion of it — a new engine/ file importing httpx/fastapi/backend.app.db
must be added here deliberately, with a reason, not accidentally pass by
omission.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[4] / "backend" / "app" / "engine"

FORBIDDEN_MODULES = ("httpx", "fastapi", "backend.app.db")

# Relative to ENGINE_ROOT. Every entry here is a KNOWN, documented violation
# — see module docstring. New entries require a reason, not just adding a
# path to make a failing test pass.
ALLOWLIST = {
    "extractors/location_extractor.py",
    "extractors/knowledge_resolution_extractor.py",
}


def _iter_engine_python_files():
    return sorted(ENGINE_ROOT.rglob("*.py"))


def _imported_module_names(file_path: Path) -> set[str]:
    """Returns the set of top-level module names this file imports (e.g.
    "httpx" from `import httpx`, "backend.app.db" from
    `from backend.app.db import repos` or `import backend.app.db.repos`)."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except SyntaxError:
        pytest.fail(f"{file_path} has a syntax error and could not be checked")

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def _violates(imported: set[str]) -> set[str]:
    violations = set()
    for forbidden in FORBIDDEN_MODULES:
        for name in imported:
            if name == forbidden or name.startswith(forbidden + "."):
                violations.add(forbidden)
    return violations


def test_engine_root_actually_exists_and_has_python_files():
    """Guards against a path typo silently making every other test in this
    file vacuously pass over zero files."""
    assert ENGINE_ROOT.is_dir(), f"expected engine root at {ENGINE_ROOT}"
    files = _iter_engine_python_files()
    assert len(files) > 10, f"expected many .py files under engine/, found {len(files)}"


def test_no_new_engine_file_imports_forbidden_modules():
    """The actual enforcement: any file under backend/app/engine/ NOT on the
    documented allowlist must import none of httpx, fastapi, or
    backend.app.db."""
    offenders: dict[str, set[str]] = {}
    for file_path in _iter_engine_python_files():
        rel = file_path.relative_to(ENGINE_ROOT).as_posix()
        if rel in ALLOWLIST:
            continue
        imported = _imported_module_names(file_path)
        violations = _violates(imported)
        if violations:
            offenders[rel] = violations

    assert not offenders, (
        "Files under backend/app/engine/ importing forbidden modules "
        "(httpx/fastapi/backend.app.db) and NOT on the documented allowlist "
        f"in tests/backend/app/engine/test_engine_purity.py: {offenders}. "
        "Either fix the import (preferred) or add the file to ALLOWLIST "
        "with a documented reason."
    )


def test_turn_extractor_specifically_no_longer_imports_httpx():
    """The concrete, named regression guard for step 3's own change —
    narrower and more direct than the general sweep above, so a failure
    here points immediately at the file the refactor touched."""
    path = ENGINE_ROOT / "extractors" / "turn_extractor.py"
    imported = _imported_module_names(path)
    assert "httpx" not in imported, (
        "turn_extractor.py must not import httpx directly - the legacy LLM "
        "call goes through backend.app.llm.providers.openai_chat.OpenAIChatClient now"
    )


def test_allowlist_entries_are_still_real_files():
    """An allowlist entry for a file that no longer exists is stale and
    should be removed, not left to silently mask nothing."""
    for rel in ALLOWLIST:
        assert (ENGINE_ROOT / rel).is_file(), (
            f"ALLOWLIST entry {rel!r} does not correspond to a real file - remove it"
        )


def test_allowlist_entries_still_actually_violate():
    """The inverse check: an allowlist entry for a file that's since been
    fixed should be REMOVED (shrinking the allowlist, per the module
    docstring's stated intent), not left stale forever."""
    for rel in ALLOWLIST:
        imported = _imported_module_names(ENGINE_ROOT / rel)
        violations = _violates(imported)
        assert violations, (
            f"ALLOWLIST entry {rel!r} no longer imports any forbidden module - "
            "remove it from ALLOWLIST to shrink the allowlist as intended"
        )


def _top_level_imported_module_names(file_path: Path) -> set[str]:
    """Like _imported_module_names, but ONLY statements at the file's top
    level (module load time) — deliberately does NOT recurse into function
    or class bodies, since a deferred (function-local) import is exactly
    the documented, intentional pattern TurnExtractor.__init__ uses to
    obtain the default resolver without coupling engine/ to llm/ at module
    IMPORT time (see turn_extractor.py's __init__ docstring)."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


# Pure-data llm/ submodules engine/ MAY import at module level: they contain
# dataclasses/Protocol/Enum only, no I/O, no httpx, no network construction
# (verified by their own module docstrings and by test_llm's own suite).
_PURE_DATA_LLM_MODULES = ("backend.app.llm.decisions.types", "backend.app.llm.protocols")

# llm/ submodules that DO perform or set up I/O — these must never appear as
# a MODULE-LEVEL (top-of-file) import under engine/, only as a deferred,
# function-local import (the pattern TurnExtractor.__init__ uses).
_IO_TOUCHING_LLM_MODULES = ("backend.app.llm.factory", "backend.app.llm.providers")


def test_engine_does_not_import_io_touching_llm_modules_at_module_level():
    """The real dependency-direction rule this project can actually keep:
    engine/ may reference llm/'s PURE-DATA types (Decision, DecisionBatch,
    DecisionOutcome, Provider, the DecisionProvider/TextProvider protocols)
    at module level, since building a DecisionBatch or reading a
    DecisionAnswer is data manipulation, not I/O. What engine/ must NEVER do
    is import an I/O-CONSTRUCTING module (llm/factory.py, llm/providers/*)
    at module load time — those imports must be deferred into a function
    body (TurnExtractor.__init__ does this: `from backend.app.llm.factory
    import build_default_resolver` is inside __init__, not at the top of
    turn_extractor.py), so importing the engine module itself never
    constructs a network client or reads settings.py as a side effect."""
    offenders: dict[str, set[str]] = {}
    for file_path in _iter_engine_python_files():
        rel = file_path.relative_to(ENGINE_ROOT).as_posix()
        top_level = _top_level_imported_module_names(file_path)
        io_touching = {
            n for n in top_level
            if any(n == m or n.startswith(m + ".") for m in _IO_TOUCHING_LLM_MODULES)
        }
        if io_touching:
            offenders[rel] = io_touching

    assert not offenders, (
        f"Files under engine/ importing I/O-touching llm/ modules AT MODULE "
        f"LEVEL (not deferred into a function body): {offenders}. Move these "
        "imports inside the function/method that needs them, matching "
        "TurnExtractor.__init__'s pattern."
    )


def test_turn_extractor_defers_io_touching_llm_imports_into_init():
    """The concrete, named case this rule exists for: turn_extractor.py
    DOES reference llm.factory and llm.providers.openai_chat (it has to, to
    construct its default resolver and legacy client) — but only inside
    __init__'s body, never at the top of the file."""
    path = ENGINE_ROOT / "extractors" / "turn_extractor.py"
    top_level = _top_level_imported_module_names(path)
    all_imports = _imported_module_names(path)

    assert not any(n.startswith("backend.app.llm.factory") for n in top_level), (
        "backend.app.llm.factory must not be imported at module level in turn_extractor.py"
    )
    assert not any(n.startswith("backend.app.llm.providers") for n in top_level), (
        "backend.app.llm.providers.* must not be imported at module level in turn_extractor.py"
    )
    # But it MUST appear somewhere in the file (deferred) - otherwise the
    # default resolver could never be constructed at all, which would be a
    # different, worse bug than a purity violation.
    assert any(n.startswith("backend.app.llm.factory") for n in all_imports), (
        "expected a deferred backend.app.llm.factory import somewhere in turn_extractor.py "
        "(inside __init__) - if this legitimately changed, update this test's expectation"
    )


def test_engine_pure_data_llm_imports_are_only_the_documented_ones():
    """Guards against the pure-data allowance silently growing to cover an
    I/O module by accident - if a NEW backend.app.llm.* submodule shows up
    as a module-level import under engine/ and it isn't one of the two
    documented pure-data modules, this test forces a deliberate decision
    (add it to _PURE_DATA_LLM_MODULES with justification, or fix the
    import), rather than silently passing because it wasn't yet in
    _IO_TOUCHING_LLM_MODULES's explicit list either."""
    unexpected: dict[str, set[str]] = {}
    for file_path in _iter_engine_python_files():
        rel = file_path.relative_to(ENGINE_ROOT).as_posix()
        top_level = _top_level_imported_module_names(file_path)
        llm_imports = {n for n in top_level if n == "backend.app.llm" or n.startswith("backend.app.llm.")}
        unrecognized = {
            n for n in llm_imports
            if not any(n == m or n.startswith(m + ".") for m in _PURE_DATA_LLM_MODULES)
        }
        if unrecognized:
            unexpected[rel] = unrecognized

    assert not unexpected, (
        f"Module-level backend.app.llm.* imports under engine/ that are neither "
        f"a documented pure-data module nor a known I/O-touching one (would have "
        f"been caught by the other test if truly I/O-touching - this means a NEW, "
        f"unclassified llm/ submodule was imported): {unexpected}. Classify it "
        "explicitly in this test file."
    )
