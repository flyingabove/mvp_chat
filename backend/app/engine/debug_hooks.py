# backend/app/engine/debug_hooks.py
"""Registry of player-safe debug providers for the `debug_box` (visible after `[D]`).

A subsystem that keeps state a reply does not reveal registers one function here instead of editing the chat
handler. The provider receives the GameState and returns a small JSON-safe dict (or None for "nothing to show").
Player-safe only: anything that would spoil the story belongs in the operator-only `turn_trace`/`prompt_debug`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

DebugProvider = Callable[[Any], "dict | None"]

_PROVIDERS: dict[str, DebugProvider] = {}


def register_debug_provider(name: str, provider: DebugProvider) -> None:
    """Add (or replace) the provider shown under `debug_box["mechanics"][name]`."""
    _PROVIDERS[name] = provider


def collect_debug_mechanics(state: Any) -> dict[str, dict]:
    """Run every provider; a failing provider is reported, never allowed to break the turn."""
    out: dict[str, dict] = {}
    for name, provider in _PROVIDERS.items():
        try:
            value = provider(state)
        except Exception as exc:  # debug output must never fail a player's turn
            logger.warning("debug provider %s failed: %s", name, exc)
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        if value:
            out[name] = value
    return out


def _world_clock(state: Any) -> dict | None:
    model = getattr(state, "world_model", None)
    if model is None:
        return None
    return {"player_availability": model.player_availability, "player_place": model.player_place() or None,
            "world_turn": model.turn}


register_debug_provider("world", _world_clock)
