# backend/app/api/eval_capabilities.py
"""GET /api/eval/capabilities — versioned contract telling the Jev game
arena what this release can support (JEV_GAME_ARENA_DESIGN.md §10).

Read-only, no secrets, no state: it only states which evaluation features
exist so the arena can label results (observational vs controlled) and
report unsupported metrics as "not measured" instead of silently passing.
Releases without this route (e.g. older prod) are treated as capabilities
unknown = observational only.
"""
from fastapi import APIRouter

from backend.app.config.build_info import get_build_info

router = APIRouter()

EVAL_CAPABILITIES_CONTRACT = "arena-capabilities-1"


def eval_capabilities() -> dict:
    return {
        "contract_version": EVAL_CAPABILITIES_CONTRACT,
        "features": {
            "public_chat": True,                 # /api/chat, same path as the browser
            "request_id_idempotency": True,      # BL-02 replay of a retried turn
            "debug_box_observation": True,       # player-facing [D]: clock, location, speakers
            "build_identity": True,              # commit + deployment_id in /api/health
            "turn_receipts": False,              # server-side per-turn receipts (planned)
            "controlled_initialization": False,  # seeded roster/RNG fixtures (planned)
            "snapshot_export": False,
            "snapshot_restore": False,
        },
        "build": get_build_info(),
    }


@router.get("/eval/capabilities")
async def capabilities():
    return eval_capabilities()
