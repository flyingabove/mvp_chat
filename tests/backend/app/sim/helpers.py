"""A small, story-free six-resident Terrace-shaped fixture for SeasonRunner tests.

Re-exports `backend/app/sim/fixtures.py`, which moved there (P-13 debug viewer work) so the operator-only
season-runner debug endpoint can build the same fixture without production code importing from `tests/`.
Kept as a thin shim here so these tests' imports did not need to change.
"""
from __future__ import annotations

from backend.app.sim.fixtures import (  # noqa: F401
    BEDROOM,
    LIVING_ROOM,
    NPC_IDS,
    START,
    build_lifecycle,
    build_model,
    build_story,
)
