"""Single source of truth for "who is relevant to this turn's prompt."

Consolidates the scene-membership/knowledge-visibility logic that used to be
scattered across module-level functions in `prompt_builder.py`
(`_cast_scene_eligible`, `_get_active_character_keys`, `_get_people_present_keys`,
`_get_scene_speaker_keys`, `_scene_cast_keys`, `_scene_presence_keys`,
`_fact_owner_only_upcoming`, `_main_character_scene_eligible`,
`_scene_presence_has_been_computed`) into one object, per the Six Strangers
audit's recommendation (documentation/SIX_STRANGERS_AUDIT_PROPOSAL_2026_09_19.md,
"one reusable context-selection policy separating membership, physical
presence, known public history, and private knowledge").

This is a behavior-preserving consolidation: every method below reproduces
the exact prior logic of its corresponding free function, just computed once
per instance (memoized) instead of rescanning `state.transient_entries` on
every call. `prompt_builder.py`'s free functions become thin wrappers that
build (or reuse) a `SceneContext` and delegate to it, so existing callers and
tests that call the free functions directly keep working unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.engine.state import GameState


class SceneContext:
    """Lazily-computed, memoized view of scene membership/presence for one
    `GameState` snapshot. Build once per prompt assembly (or per turn) and
    pass it around rather than re-deriving these sets repeatedly."""

    def __init__(self, state: "GameState") -> None:
        self._state = state
        self._eligible_cache: dict[str, bool] = {}
        self._active_keys: set[str] | None = None
        self._people_present_keys: set[str] | None = None
        self._scene_speaker_keys: set[str] | None = None
        self._scene_presence_keys: set[str] | None = None
        self._scene_cast_keys: list[str] | None = None
        self._presence_computed: bool | None = None

    @classmethod
    def build(cls, state: "GameState") -> "SceneContext":
        return cls(state)

    # -- Membership (cast-lifecycle eligibility) ---------------------------

    def is_eligible(self, key: str) -> bool:
        """True if `key` is allowed to appear in the current scene at all
        (not retired/not-yet-arrived per cast lifecycle). Mirrors
        `_cast_scene_eligible` exactly."""
        key = str(key or "")
        cached = self._eligible_cache.get(key)
        if cached is not None:
            return cached
        lifecycle = getattr(self._state, "cast_lifecycle", None)
        if lifecycle is None or not getattr(lifecycle, "enabled", False):
            result = True
        else:
            result = key == "player" or lifecycle.is_scene_eligible(key)
        self._eligible_cache[key] = result
        return result

    # -- Physical presence / speaking ---------------------------------------

    def active_keys(self) -> set[str]:
        """Mirrors `_get_active_character_keys`: mention/on-call/speaker
        markers plus main + player, filtered by eligibility."""
        if self._active_keys is not None:
            return self._active_keys
        state = self._state
        keys: set[str] = set()
        main_id = getattr(state, "main_character_id", "") or ""
        if main_id and self.is_eligible(main_id):
            keys.add(main_id)
        keys.add("player")

        marker_prefixes = (
            "__active_character_marker__:",
            "__scene_speaker_marker__:",
            "__on_call_character_marker__:",
        )
        for e in getattr(state, "transient_entries", []) or []:
            txt = (getattr(e, "text", "") or "").strip()
            for prefix in marker_prefixes:
                if txt.startswith(prefix):
                    ch_key = txt.split(":", 1)[1].strip().lower()
                    if ch_key and self.is_eligible(ch_key):
                        keys.add(ch_key)
                    break

        self._active_keys = keys
        return keys

    def present_keys(self) -> set[str]:
        """Mirrors `_get_people_present_keys`: explicit presence markers,
        falling back to the latest scene-knowledge entry's people_present."""
        if self._people_present_keys is not None:
            return self._people_present_keys
        state = self._state
        keys: set[str] = set()
        for e in getattr(state, "transient_entries", []) or []:
            txt = (getattr(e, "text", "") or "").strip()
            if txt.startswith("__people_present_marker__:"):
                ch_key = txt.split(":", 1)[1].strip().lower()
                if ch_key and self.is_eligible(ch_key):
                    keys.add(ch_key)
        if keys:
            self._people_present_keys = keys
            return keys

        latest_scene = getattr(state, "latest_scene_knowledge", None)
        if callable(latest_scene):
            item = latest_scene()
            if item is not None:
                keys = {
                    str(k or "").strip().lower()
                    for k in (getattr(item, "people_present", []) or [])
                    if str(k or "").strip() and self.is_eligible(str(k or "").strip().lower())
                }
        self._people_present_keys = keys
        return keys

    def speaker_keys(self) -> set[str]:
        """Mirrors `_get_scene_speaker_keys`: explicit speaker markers,
        falling back to the latest scene-knowledge entry's speakers."""
        if self._scene_speaker_keys is not None:
            return self._scene_speaker_keys
        state = self._state
        keys: set[str] = set()
        for e in getattr(state, "transient_entries", []) or []:
            txt = (getattr(e, "text", "") or "").strip()
            if txt.startswith("__scene_speaker_marker__:"):
                ch_key = txt.split(":", 1)[1].strip().lower()
                if ch_key and self.is_eligible(ch_key):
                    keys.add(ch_key)
        if keys:
            self._scene_speaker_keys = keys
            return keys

        latest_scene = getattr(state, "latest_scene_knowledge", None)
        if callable(latest_scene):
            item = latest_scene()
            if item is not None:
                keys = {
                    str(k or "").strip().lower()
                    for k in (getattr(item, "speakers", []) or [])
                    if str(k or "").strip() and self.is_eligible(str(k or "").strip().lower())
                }
        self._scene_speaker_keys = keys
        return keys

    def presence_computed(self) -> bool:
        """Mirrors `_scene_presence_has_been_computed`: true once any turn
        has recorded scene knowledge for the current location, distinguishing
        "genuinely empty room" from "no signal yet"."""
        if self._presence_computed is not None:
            return self._presence_computed
        state = self._state
        result = False
        for e in getattr(state, "transient_entries", []) or []:
            txt = (getattr(e, "text", "") or "").strip()
            if txt.startswith("__people_present_marker__:"):
                result = True
                break
        if not result:
            latest_scene = getattr(state, "latest_scene_knowledge", None)
            if callable(latest_scene):
                item = latest_scene()
                if item is not None:
                    loc_id = str(getattr(state, "location_id", "") or "")
                    item_loc_id = str(getattr(item, "location_id", "") or "")
                    if not loc_id or item_loc_id == loc_id:
                        result = True
        self._presence_computed = result
        return result

    def main_present(self) -> bool:
        """Mirrors `_main_character_scene_eligible`: non-lifecycle stories
        are always True (legacy behavior preserved byte-for-byte); lifecycle
        stories require eligibility, and (once presence has been computed)
        actual presence in the current scene."""
        state = self._state
        lifecycle = getattr(state, "cast_lifecycle", None)
        if lifecycle is None or not getattr(lifecycle, "enabled", False):
            return True
        main_char = getattr(state, "main_character", None)
        main_key = (getattr(main_char, "key", "") or "").strip().lower()
        if not self.is_eligible(main_key):
            return False
        if not self.presence_computed():
            return True
        return main_key in self.present_keys()

    def fact_owner_only_upcoming(self, known_by: list[str]) -> bool:
        """Mirrors `_fact_owner_only_upcoming`: true only when every named
        owner of a fact is an upcoming (never-yet-active) lifecycle
        character."""
        state = self._state
        lifecycle = getattr(state, "cast_lifecycle", None)
        if lifecycle is None or not getattr(lifecycle, "enabled", False):
            return False
        from backend.app.engine.cast_lifecycle import CastStatus  # local import: avoid cycles

        named = [k for k in known_by if k not in ("all", "all_characters")]
        if not named:
            return False
        return all(
            not self.is_eligible(key) and key in lifecycle.members
            and lifecycle.members[key].status is CastStatus.UPCOMING
            for key in named
        )
