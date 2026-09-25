"""Objects and evidence: entities in the world index with surfaces a person can
notice. Inspection is deterministic and records only what the viewer can
perceive; an item's hidden link to the truth (`truth_event`) is never rendered."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from backend.app.engine.world_model.entities import Entity
from backend.app.engine.world_model.model import PLAYER

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

INSPECT = re.compile(r"\b(examine|examining|inspect|inspecting|look(?:ing)? (?:at|closely at|under|inside|in|behind)|"
                     r"search(?:ing)?|check(?:ing)?|study(?:ing)?|run my (?:hand|fingers) (?:over|along))\b", re.I)
CLOSE = re.compile(r"\b(closely|carefully|up close|thoroughly|search|searching|run my (?:hand|fingers))\b", re.I)


@dataclass
class Inspection:
    entity: Entity
    noticed: list[str]
    missed: int


def find_inspect_target(model: "WorldModel", message: str, viewer: str = PLAYER) -> Optional[Entity]:
    if not INSPECT.search(message or ""):
        return None
    place = model.world.place_of(viewer)
    if not place:
        return None
    here = model.world.contents_of(place, recursive=True)
    matches = [model.world.entities[eid] for eid in sorted(here)
               if eid in model.world.entities and model.world.entities[eid].kind in ("object", "evidence")
               and model.world.entities[eid].matches(message)]
    return max(matches, key=lambda e: len(e.name)) if matches else None


def _perceivable(surface: dict, model: "WorldModel", viewer: str, message: str) -> bool:
    needs = surface.get("requires") or {}
    if needs.get("attention") == "close" and not CLOSE.search(message or ""):
        return False
    tool = needs.get("tool")
    if tool and tool not in model.world.contents_of(viewer):
        return False
    return True


def inspect(model: "WorldModel", entity: Entity, message: str, viewer: str = PLAYER,
            witnesses: tuple[str, ...] = ()) -> Inspection:
    surfaces = list(entity.props.get("surfaces") or [])
    noticed = [s["text"] for s in surfaces if _perceivable(s, model, viewer, message)]
    minute, place = model.world.minute, model.world.place_of(viewer) or ""
    if noticed:
        event = model.world.add_event(minute, place, (viewer, *witnesses),
                                      f"@{viewer} inspected {entity.name}", kind="inspection")
        for text in noticed:
            if not model.memories.has_text(viewer, f"{entity.name}: {text}"):
                model.memories.add(viewer, f"{entity.name}: {text}", "witnessed", minute, event_id=event.id)
        for witness in witnesses:
            model.memories.add(witness, f"@{viewer} examined {entity.name}", "witnessed", minute, event_id=event.id)
    return Inspection(entity, noticed, len(surfaces) - len(noticed))
