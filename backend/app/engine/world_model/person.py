"""The character aggregate (BL-39 "Character"): one person, one point of view.

A Person composes what already exists instead of copying it: the authored
profile (engine.state.Character), the world-model body (CharacterState), the
heart (bonds over the character graph) and scoped views over the shared
stores. Callers ask the person; they never filter shared lists by owner.
The player is a Person too, with no authored profile or body.
"""
from __future__ import annotations

from typing import Any, Optional

from backend.app.engine.world_model.heart import Heart
from backend.app.engine.world_model.model import PLAYER, WorldModel


class Person:
    def __init__(self, cid: str, model: WorldModel, graph: Any = None, profile: Any = None) -> None:
        self.id = cid
        self._model = model
        self.profile = profile
        self.body = model.characters.get(cid)
        self.heart = Heart(cid, graph)

    @property
    def is_player(self) -> bool:
        return self.id == PLAYER

    @property
    def name(self) -> str:
        if self.is_player:
            return self._model.player_name
        return self.body.name if self.body is not None else str(getattr(self.profile, "name", "") or self.id)

    # -- scoped views over shared stores (no copies) ------------------------------------
    def memories(self) -> list:
        return self._model.memories.of(self.id)

    def beliefs(self) -> list:
        return [b for b in self._model.epistemics.beliefs if b.owner == self.id]

    def observations(self) -> list:
        return [o for o in self._model.epistemics.observations if o.owner == self.id]

    def commitments(self) -> list:
        return [a for a in self._model.agreements.items if self.id in (a.proposer, a.counterpart)]

    def owed_questions(self) -> list:
        return [q for q in self._model.conversation.open_questions() if q.addressee == self.id]

    def knows_player_name(self) -> bool:
        return self.is_player or self.id in self._model.knows_player_name

    def last_with_player(self) -> Optional[int]:
        return None if self.is_player else self._model.last_with_player.get(self.id)

    def warmth_toward(self, target: str) -> float:
        bond = self.heart.bond(target)
        return bond.warmth() if bond is not None else 0.0


class Cast:
    """Resolves one Person per id from a game state's existing stores."""

    def __init__(self, state: Any) -> None:
        model = getattr(state, "world_model", None)
        if model is None:
            raise ValueError("the cast needs a world model")
        self._model = model
        self._graph = getattr(state, "character_graph", None)
        self._profiles = getattr(state, "characters", {}) or {}

    def ids(self) -> list[str]:
        return sorted(self._model.characters)

    def get(self, cid: str) -> Person:
        if cid != PLAYER and cid not in self._model.characters:
            raise KeyError(cid)
        return Person(cid, self._model, self._graph, None if cid == PLAYER else self._profiles.get(cid))

    def player(self) -> Person:
        return self.get(PLAYER)
