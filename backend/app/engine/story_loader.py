# app/engine/story_loader.py
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.engine.character_graph import CharacterGraph
from backend.app.engine.state import Character
from backend.app.utils.logging_utils import jlog


# Backward-compat alias — external code that imports StoryCharacter still works.
StoryCharacter = Character

# Canonical stories directory — single source of truth for all modules.
STORIES_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stories")

# Reusable active-story allowlist for the product catalog.
# Keep this small and explicit so the app is easy to reason about while still
# staying generic for future expansion via env override.
DEFAULT_ACTIVE_STORY_IDS = ("iu_murder_mystery", "six_strangers")


def get_active_story_ids() -> list[str]:
    raw = (os.getenv("ACTIVE_STORY_IDS") or "").strip()
    if raw:
        parsed = [p.strip() for p in raw.split(",") if p.strip()]
        if parsed:
            return parsed
    return list(DEFAULT_ACTIVE_STORY_IDS)


@dataclass
class StoryDefinition:
    id: str
    raw: Dict[str, Any] = field(default_factory=dict)
    title: str = ""
    theme: str = ""
    instance: int = 1
    characters: List[Character] = field(default_factory=list)
    relationships: Optional[CharacterGraph] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryDefinition":
        data = data or {}
        story_id = str(data.get("id") or "").strip()
        title = str(data.get("title") or "").strip()
        theme = str(data.get("theme") or "").strip()
        try:
            instance = int(data.get("instance", 1))
        except Exception:
            instance = 1

        characters: List[Character] = []
        for c in data.get("characters") or []:
            try:
                characters.append(Character.from_dict(c))
            except Exception:
                continue

        # Backfill legacy schema (main_character + suspects) if no characters present.
        if not characters:
            main_cfg = data.get("main_character") or {}
            if main_cfg:
                main_cfg = dict(main_cfg)
                main_cfg.setdefault("is_main", True)
                try:
                    characters.append(Character.from_dict(main_cfg))
                except Exception:
                    pass

            for sus in data.get("suspects") or []:
                sus_cfg = dict(sus)
                sus_cfg.setdefault("is_suspect", True)
                try:
                    characters.append(Character.from_dict(sus_cfg))
                except Exception:
                    continue

        # Ensure exactly one main flag if characters exist.
        if characters and not any(c.is_main for c in characters):
            jlog({
                "kind": "story_warning",
                "msg": "No is_main character found in story JSON; defaulting to first character",
                "character": characters[0].key,
            })
            characters[0].is_main = True

        normalized = dict(data)
        normalized["characters"] = [c.to_dict() for c in characters]

        # Backfill legacy main_character block for compatibility
        if "main_character" not in normalized:
            main = None
            for c in characters:
                if c.is_main:
                    main = c
                    break
            if not main and characters:
                main = characters[0]
            if main:
                normalized["main_character"] = {
                    "key": main.key,
                    "name": main.name,
                    "role": main.role,
                    "knowledge_character_id": main.knowledge_character_id,
                    "uuid": main.uuid,
                }

        # Parse character relationship graph
        rel_data = data.get("relationships")
        relationships = CharacterGraph.from_dict(rel_data) if rel_data else None

        return cls(
            id=story_id,
            raw=normalized,
            title=title,
            theme=theme,
            instance=instance,
            characters=characters,
            relationships=relationships,
        )

    # Dict-like helpers for backwards compatibility
    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        return self.raw

    def __bool__(self):
        return bool(self.raw)

    @property
    def main_character(self) -> Optional[Character]:
        for c in self.characters:
            if c.is_main:
                return c
        return self.characters[0] if self.characters else None

    @property
    def suspects(self) -> List[Character]:
        return [c for c in self.characters if c.is_suspect]

    @property
    def main_character_role(self) -> str:
        mc = self.main_character
        return mc.role if mc else ""


# ---------------------------------------------------------------------------
# Story content registry (A05)
# ---------------------------------------------------------------------------
# Single source of truth for resolving a story by its *declared* `id` field
# inside the JSON \u2014 never by filename-guessing. Filenames are an authoring
# convenience and are allowed to disagree with the declared id (this is
# exactly what happened for blackout_manor/neon_district/the_last_session,
# whose files are named 3_story.json/4_story.json/5_story.json). Both the
# runtime loader (load_story/find_story_dir below) and the catalogue
# endpoint (backend/app/api/stories.py) must build their view of "what
# stories exist" from this same registry so they can never disagree.
def _iter_story_files():
    """Yield (path, subdir_or_None) for every candidate story JSON file
    (root level and one level of subdirectories), skipping world sidecars."""
    if not os.path.isdir(STORIES_DIR):
        return
    for fname in sorted(os.listdir(STORIES_DIR)):
        full = os.path.join(STORIES_DIR, fname)
        if os.path.isfile(full) and fname.endswith(".json") and not fname.endswith("_world.json"):
            yield full, None
    for d in sorted(os.listdir(STORIES_DIR)):
        sub = os.path.join(STORIES_DIR, d)
        if os.path.isdir(sub) and not d.startswith("__"):
            for fname in sorted(os.listdir(sub)):
                full = os.path.join(sub, fname)
                if os.path.isfile(full) and fname.endswith(".json") and not fname.endswith("_world.json"):
                    yield full, d


def build_story_registry() -> Dict[str, Dict[str, Any]]:
    """Scan STORIES_DIR once and build {declared_id: {"path", "subdir", "raw"}}.

    Falls back to the filename stem only when a file has no `id` field.
    Re-scanned on every call (the catalogue is small and
    POST /stories/draft writes new files at runtime that must show up
    immediately), so do not cache this without also invalidating on draft
    creation.
    """
    registry: Dict[str, Dict[str, Any]] = {}
    active_story_ids = set(get_active_story_ids())
    for path, subdir in _iter_story_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            raw_text = raw_text.lstrip("\ufeff")
            cfg = json.loads(raw_text)
        except Exception as e:
            jlog({"kind": "story_registry_parse_error", "path": path, "error": str(e)})
            continue
        story_id = str(cfg.get("id") or os.path.splitext(os.path.basename(path))[0]).strip()
        if not story_id or story_id not in active_story_ids:
            continue
        registry[story_id] = {"path": path, "subdir": subdir, "raw": cfg}
    return registry


def find_story_dir(story_id: str) -> str | None:
    """
    Return the subdirectory name that contains the story JSON for
    story_id (matched by declared id), or None if it lives at root / not found.
    """
    entry = build_story_registry().get(story_id)
    return entry["subdir"] if entry else None


def load_story(story_id: str) -> Optional[StoryDefinition]:
    """
    Load a story by its declared `id` field via the content registry
    (build_story_registry), not by filename-guessing (A05).

    Returns a StoryDefinition or None if not found/failed to parse.
    """
    entry = build_story_registry().get(story_id)
    if not entry:
        jlog({"kind": "story_not_found", "story_id": story_id})
        return None

    jlog({"kind": "story_load_attempt", "story_id": story_id, "path": entry["path"], "exists": True})

    try:
        return StoryDefinition.from_dict(entry["raw"])
    except Exception as e:
        jlog({"kind": "story_load_error", "story_id": story_id, "error": str(e)})
        return None
