# app/engine/story_loader.py
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.engine.character_graph import CharacterGraph
from backend.app.utils.logging_utils import jlog


@dataclass
class StoryCharacter:
    key: str
    name: str
    role: str = ""
    is_main: bool = False
    is_suspect: bool = False
    knowledge_character_id: str = ""
    uuid: str = ""
    tags: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryCharacter":
        data = data or {}
        key = str(data.get("key") or data.get("id") or data.get("name") or "character").strip() or "character"
        name = str(data.get("name") or key).strip() or key
        role = str(data.get("role") or "").strip()
        is_main = bool(data.get("is_main"))
        is_suspect = bool(data.get("is_suspect") or data.get("suspect"))
        knowledge_character_id = str(data.get("knowledge_character_id") or "").strip()
        uuid = str(data.get("uuid") or "").strip()
        tags = list(data.get("tags") or [])

        # Preserve any extra attributes for forward-compatibility.
        known_keys = {
            "key",
            "id",
            "name",
            "role",
            "is_main",
            "is_suspect",
            "suspect",
            "knowledge_character_id",
            "uuid",
            "tags",
        }
        meta = {k: v for k, v in data.items() if k not in known_keys}

        return cls(
            key=key,
            name=name,
            role=role,
            is_main=is_main,
            is_suspect=is_suspect,
            knowledge_character_id=knowledge_character_id,
            uuid=uuid,
            tags=tags,
            meta=meta,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "role": self.role,
            "is_main": self.is_main,
            "is_suspect": self.is_suspect,
            "knowledge_character_id": self.knowledge_character_id,
            "uuid": self.uuid,
            "tags": self.tags,
            **(self.meta or {}),
        }


@dataclass
class StoryDefinition:
    id: str
    raw: Dict[str, Any] = field(default_factory=dict)
    title: str = ""
    theme: str = ""
    instance: int = 1
    characters: List[StoryCharacter] = field(default_factory=list)
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

        characters: List[StoryCharacter] = []
        for c in data.get("characters") or []:
            try:
                characters.append(StoryCharacter.from_dict(c))
            except Exception:
                continue

        # Backfill legacy schema (main_character + suspects) if no characters present.
        if not characters:
            main_cfg = data.get("main_character") or {}
            if main_cfg:
                main_cfg = dict(main_cfg)
                main_cfg.setdefault("is_main", True)
                try:
                    characters.append(StoryCharacter.from_dict(main_cfg))
                except Exception:
                    pass

            for sus in data.get("suspects") or []:
                sus_cfg = dict(sus)
                sus_cfg.setdefault("is_suspect", True)
                try:
                    characters.append(StoryCharacter.from_dict(sus_cfg))
                except Exception:
                    continue

        # Ensure exactly one main flag if characters exist.
        if characters and not any(c.is_main for c in characters):
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
    def main_character(self) -> Optional[StoryCharacter]:
        for c in self.characters:
            if c.is_main:
                return c
        return self.characters[0] if self.characters else None

    @property
    def suspects(self) -> List[StoryCharacter]:
        return [c for c in self.characters if c.is_suspect]

    @property
    def main_character_role(self) -> str:
        mc = self.main_character
        return mc.role if mc else ""


def _story_json_candidates(story_id: str) -> list[str]:
    """Filenames to try when resolving a story (handles _story suffix convention)."""
    return [f"{story_id}.json", f"{story_id}_story.json"]


def find_story_dir(story_id: str) -> str | None:
    """
    Return the subdirectory name that contains
    the story JSON for story_id, or None if it lives at root / not found.
    """
    base = os.path.dirname(os.path.dirname(__file__))  # app/
    stories_dir = os.path.join(base, "stories")

    # Direct path (root level)
    for fname in _story_json_candidates(story_id):
        if os.path.isfile(os.path.join(stories_dir, fname)):
            return None

    try:
        for d in os.listdir(stories_dir):
            if os.path.isdir(os.path.join(stories_dir, d)) and not d.startswith("__"):
                for fname in _story_json_candidates(story_id):
                    if os.path.isfile(os.path.join(stories_dir, d, fname)):
                        return d
    except Exception:
        pass
    return None


def load_story(story_id: str) -> Optional[StoryDefinition]:
    """
    Load a story JSON file by id, trying both {story_id}.json and
    {story_id}_story.json in root and subdirectories.

    Returns a StoryDefinition or None if not found/failed to parse.
    """
    base = os.path.dirname(os.path.dirname(__file__))  # app/
    stories_dir = os.path.join(base, "stories")

    story_path = None

    # Try root level first
    for fname in _story_json_candidates(story_id):
        candidate = os.path.join(stories_dir, fname)
        if os.path.isfile(candidate):
            story_path = candidate
            break

    jlog({"kind": "story_load_attempt", "story_id": story_id,
          "path": story_path or os.path.join(stories_dir, f"{story_id}.json"),
          "exists": story_path is not None})

    # If not found at root, try subdirectories
    if not story_path:
        try:
            subdirs = [d for d in os.listdir(stories_dir)
                      if os.path.isdir(os.path.join(stories_dir, d)) and not d.startswith("__")]
            for subdir in subdirs:
                for fname in _story_json_candidates(story_id):
                    alt_path = os.path.join(stories_dir, subdir, fname)
                    if os.path.isfile(alt_path):
                        story_path = alt_path
                        jlog({"kind": "story_found_in_subdir", "story_id": story_id, "subdir": subdir})
                        break
                if story_path:
                    break
        except Exception as e:
            jlog({"kind": "story_subdir_scan_error", "story_id": story_id, "error": str(e)})

    if not story_path:
        jlog({"kind": "story_not_found", "story_id": story_id})
        return None

    try:
        # Read raw text first so we can strip BOM
        with open(story_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # Strip Byte Order Mark (common cause of silent JSON failure)
        if raw.startswith("\ufeff"):
            jlog({"kind": "story_bom_stripped", "story_id": story_id})
            raw = raw.lstrip("\ufeff")

        return StoryDefinition.from_dict(json.loads(raw))

    except json.JSONDecodeError as e:
        jlog({"kind": "story_json_error", "story_id": story_id, "error": str(e), "path": story_path})
        return None

    except Exception as e:
        jlog({"kind": "story_load_error", "story_id": story_id, "error": str(e)})
        return None
