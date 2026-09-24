# backend/app/evaluation/knowledge.py
"""GameKnowledgeBundle: the judge-side world oracle (JEV_GAME_ARENA_DESIGN.md §6).

Built directly from the AUTHORED story and world JSON, never from the
candidate engine's runtime state or its own retrieval choices, so the judge
and the deterministic checks do not inherit an engine bug. Hashed so every
report names the exact content it judged against.

Player-side code must never receive a bundle: it holds protected canon.
"""
from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from backend.app.evaluation.contracts import stable_hash


@dataclass(frozen=True)
class CanonFact:
    id: str
    text: str
    known_by: tuple[str, ...]
    protected: bool          # the player does not start knowing it


@dataclass(frozen=True)
class CharacterCard:
    key: str
    name: str
    role: str
    motive: str = ""


@dataclass(frozen=True)
class LocationNode:
    id: str
    name: str
    area_id: str = ""


@dataclass(frozen=True)
class GameKnowledgeBundle:
    story_id: str
    title: str
    genre: str
    setting: str
    goal: str
    open_ended: bool
    characters: tuple[CharacterCard, ...]
    facts: tuple[CanonFact, ...]
    locations: tuple[LocationNode, ...]
    edges: tuple[tuple[str, str, int], ...]     # directed (from, to, minutes)
    win_patterns: tuple[str, ...] = ()
    source_hash: str = ""
    adjacency: dict[str, tuple[str, ...]] = field(default_factory=dict, compare=False, hash=False)

    @property
    def bundle_hash(self) -> str:
        return self.source_hash

    # ---- locations / routes (independent reference algorithm, §7) -------
    def location(self, location_id: str) -> LocationNode | None:
        return next((l for l in self.locations if l.id == location_id), None)

    def resolve_location_id(self, name: str = "", uuid: str = "") -> str | None:
        """Map an observed location (debug-box name or uuid) to an authored id."""
        ids = sorted((l.id for l in self.locations), key=len, reverse=True)
        if uuid:
            for lid in ids:
                if uuid == lid or uuid.endswith("-" + lid):
                    return lid
        wanted = normalize(name)
        if wanted:
            for loc in self.locations:
                if normalize(loc.name) == wanted:
                    return loc.id
        return None

    def reachable(self, start: str, goal: str) -> bool:
        """BFS over authored directed edges."""
        if start == goal:
            return True
        seen, queue = {start}, deque([start])
        while queue:
            node = queue.popleft()
            for nxt in self.adjacency.get(node, ()):
                if nxt == goal:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return False

    def neighbors(self, location_id: str) -> tuple[str, ...]:
        return self.adjacency.get(location_id, ())

    # ---- focused evidence selection (§6: retrievable, not dumped) ------
    def characters_mentioned(self, text: str) -> list[CharacterCard]:
        low = text.lower()
        out = []
        for ch in self.characters:
            tokens = {ch.key.lower(), ch.name.lower(), ch.name.split()[0].lower().strip('"')}
            if any(t and re.search(rf"\b{re.escape(t)}\b", low) for t in tokens):
                out.append(ch)
        return out

    def relevant_facts(self, text: str, limit: int = 24) -> list[CanonFact]:
        """Global (unprotected) facts plus protected facts about characters
        who appear in `text`. Protected facts are exactly what a leak check
        needs, so they are always included for mentioned characters."""
        mentioned = {c.key for c in self.characters_mentioned(text)}
        picked: list[CanonFact] = []
        for fact in self.facts:
            about_mentioned = bool(mentioned & set(fact.known_by)) or any(
                k in fact.id for k in mentioned
            )
            if not fact.protected or about_mentioned:
                picked.append(fact)
        # protected-first so truncation drops generic context before secrets
        picked.sort(key=lambda f: (not f.protected, f.id))
        return picked[:limit]


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def story_files(story_id: str) -> tuple[Path, Path | None]:
    """Locate authored story + world JSON via the shared content registry."""
    from backend.app.engine.story_loader import build_story_registry

    entry = build_story_registry().get(story_id)
    if not entry:
        raise KeyError(f"unknown story: {story_id}")
    story_path = Path(entry["path"])
    worlds = sorted(story_path.parent.glob("*_world.json"))
    return story_path, (worlds[0] if worlds else None)


def setting_text(setting: Any) -> str:
    if isinstance(setting, dict):
        return "; ".join(f"{k}: {v}" for k, v in setting.items() if v)
    return str(setting or "")


def build_bundle(story_cfg: dict[str, Any], world_cfg: dict[str, Any] | None) -> GameKnowledgeBundle:
    world_cfg = world_cfg or {}
    mode = story_cfg.get("mode") or {}
    facts = []
    for f in (story_cfg.get("epistemic_seed") or {}).get("canonical_facts") or []:
        known_by = tuple(f.get("known_by") or ())
        not_known = set(f.get("not_known_by") or ())
        facts.append(CanonFact(
            id=str(f.get("id", "")),
            text=str(f.get("text") or f.get("content") or ""),
            known_by=known_by,
            protected=("player" in not_known) or ("player" not in known_by and bool(known_by)),
        ))
    characters = tuple(
        CharacterCard(
            key=str(c.get("key", "")),
            name=str(c.get("name", "")),
            role=str(c.get("role", "")),
            motive=str(c.get("motive", "")),
        )
        for c in story_cfg.get("characters") or []
    )
    raw_locs = world_cfg.get("locations") or {}
    if isinstance(raw_locs, list):
        raw_locs = {str(l.get("id")): l for l in raw_locs}
    locations = tuple(
        LocationNode(id=str(lid), name=str(l.get("name", lid)), area_id=str(l.get("area_id", "")))
        for lid, l in raw_locs.items()
    )
    edges = tuple(
        (str(e["from"]), str(e["to"]), int(e.get("minutes") or 0))
        for e in world_cfg.get("edges") or []
        if not e.get("blocked")
    )
    adjacency: dict[str, list[str]] = {}
    for a, b, _ in edges:
        adjacency.setdefault(a, []).append(b)
    win = story_cfg.get("win_detection") or {}
    return GameKnowledgeBundle(
        story_id=str(story_cfg.get("id", "")),
        title=str(story_cfg.get("title", "")),
        genre=str(story_cfg.get("genre", "")),
        setting=setting_text(mode.get("setting") or story_cfg.get("setting")),
        goal=str((story_cfg.get("goal") or {}).get("win_text_rule") or ""),
        open_ended=bool(mode.get("open_ended")),
        characters=characters,
        facts=tuple(facts),
        locations=locations,
        edges=edges,
        win_patterns=tuple(win.get("regex") or ()),
        source_hash=stable_hash({"story": story_cfg, "world": world_cfg}),
        adjacency={k: tuple(v) for k, v in adjacency.items()},
    )


def load_bundle(story_id: str) -> GameKnowledgeBundle:
    story_path, world_path = story_files(story_id)
    story_cfg = json.loads(story_path.read_text(encoding="utf-8-sig"))
    world_cfg = json.loads(world_path.read_text(encoding="utf-8-sig")) if world_path else None
    return build_bundle(story_cfg, world_cfg)


def load_bundles(story_ids: Iterable[str]) -> dict[str, GameKnowledgeBundle]:
    return {sid: load_bundle(sid) for sid in story_ids}
