"""The aggregate saved with a game: world, characters, memories, threads,
contact queue and visible traces. Everything else is a query over these."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from backend.app.engine.world_model.character import CharacterState
from backend.app.engine.world_model.agreements import AgreementBook
from backend.app.engine.world_model.epistemics import EpistemicLedger
from backend.app.engine.world_model.drama import DramaBook
from backend.app.engine.world_model.memory import MemoryStore
from backend.app.engine.world_model.threads import Thread
from backend.app.engine.world_model.world import World

PLAYER = "player"
TRACE_LIFETIME_MIN = 36 * 60
VERSION = 2


@dataclass
class Trace:
    """A consequence the player could notice. Never a log line: it is only
    surfaced to the storyteller when the player is where it can be seen."""
    minute: int
    place: str
    text: str
    involves: tuple[str, ...] = ()
    shown: bool = False

    def visible(self, now: int, player_place: str, present: set[str]) -> bool:
        if self.shown or now - self.minute > TRACE_LIFETIME_MIN:
            return False
        if self.involves:
            return set(self.involves) <= present
        return bool(self.place) and self.place == player_place

    def to_dict(self) -> dict[str, Any]:
        return {"minute": self.minute, "place": self.place, "text": self.text,
                "involves": list(self.involves), "shown": self.shown}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trace":
        return cls(int(data.get("minute") or 0), str(data.get("place") or ""), str(data.get("text") or ""),
                   tuple(data.get("involves") or ()), bool(data.get("shown")))


@dataclass
class ContactMessage:
    sender: str
    minute: int
    intent: str
    kind: str = "text"            # text | call
    delivered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"sender": self.sender, "minute": self.minute, "intent": self.intent,
                "kind": self.kind, "delivered": self.delivered}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContactMessage":
        return cls(str(data["sender"]), int(data.get("minute") or 0), str(data.get("intent") or ""),
                   str(data.get("kind") or "text"), bool(data.get("delivered")))


@dataclass
class SpeakerPlan:
    primary: str = ""
    secondary: list[str] = field(default_factory=list)
    initiative: str = ""
    silent_present: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def speakers(self) -> list[str]:
        return [s for s in [self.primary, *self.secondary] if s]


@dataclass
class TurnView:
    """Per-turn projection handed to the prompt builder (not persisted)."""
    present: list[str] = field(default_factory=list)
    plan: SpeakerPlan = field(default_factory=SpeakerPlan)
    must_address: list[str] = field(default_factory=list)
    traces: list[str] = field(default_factory=list)
    transitions: list[str] = field(default_factory=list)
    perspectives: dict[str, list[str]] = field(default_factory=dict)
    ending_hint: str = ""
    allowed_speakers: Optional[list[str]] = None      # None = not computed; [] = nobody may speak
    time_text: str = ""
    cards: list[str] = field(default_factory=list)
    elsewhere: list[str] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)


@dataclass
class WorldModel:
    world: World
    characters: dict[str, CharacterState] = field(default_factory=dict)
    memories: MemoryStore = field(default_factory=MemoryStore)
    agreements: AgreementBook = field(default_factory=AgreementBook)
    epistemics: EpistemicLedger = field(default_factory=EpistemicLedger)
    drama: DramaBook = field(default_factory=DramaBook)
    threads: list[Thread] = field(default_factory=list)
    contacts: list[ContactMessage] = field(default_factory=list)
    traces: list[Trace] = field(default_factory=list)
    seed: str = "world"
    turn: int = 0
    endings: list[str] = field(default_factory=list)
    player_availability: str = "awake"
    player_name: str = "the player"
    known_names: list[str] = field(default_factory=list)   # character IDs whose names the player has learned
    home_of_player: str = ""
    initiative_last_day: dict[str, int] = field(default_factory=dict)
    romance_player_choice: str = ""
    romance_npc_choice: str = ""
    romance_outcome: str = ""
    romance_relationship_player_choice: str = ""
    romance_relationship_npc_choice: str = ""
    romance_relationship_partner: str = ""
    view: TurnView = field(default_factory=TurnView)       # transient

    # -- queries -----------------------------------------------------------------
    def rng(self, purpose: str, minute: Optional[int] = None) -> random.Random:
        return random.Random(f"{self.seed}:{purpose}:{self.world.minute if minute is None else minute}")

    def player_place(self) -> str:
        return self.world.place_of(PLAYER) or ""

    def is_placed(self, character_id: str) -> bool:
        return self.world.where_is(character_id) is not None

    def present_with_player(self, include_asleep: bool = False) -> list[str]:
        """Characters in the player's place (unplaced characters are never 'present' by location)."""
        place = self.player_place()
        if not place:
            return []
        here = []
        for cid, character in self.characters.items():
            if self.world.place_of(cid) == place and (include_asleep or character.availability != "asleep"):
                here.append(cid)
        return sorted(here)

    def names(self) -> dict[str, str]:
        names = {cid: c.name for cid, c in self.characters.items()}
        names[PLAYER] = self.player_name
        return names

    def descriptors(self) -> dict[str, str]:
        return {cid: c.descriptor or "someone" for cid, c in self.characters.items()}

    def add_trace(self, minute: int, place: str, text: str, involves: Iterable[str] = ()) -> None:
        self.traces.append(Trace(minute, place, text, tuple(involves)))
        self.traces = self.traces[-40:]

    # -- persistence -------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"version": VERSION, "world": self.world.to_dict(),
                "characters": {cid: c.to_dict() for cid, c in self.characters.items()},
                "memories": self.memories.to_dict(), "agreements": self.agreements.to_dict(),
                "epistemics": self.epistemics.to_dict(), "drama": self.drama.to_dict(),
                "threads": [t.to_dict() for t in self.threads],
                "contacts": [c.to_dict() for c in self.contacts], "traces": [t.to_dict() for t in self.traces],
                "seed": self.seed, "turn": self.turn, "endings": list(self.endings),
                "player_availability": self.player_availability, "player_name": self.player_name,
                "known_names": list(self.known_names), "home_of_player": self.home_of_player,
                "initiative_last_day": dict(self.initiative_last_day),
                "romance_player_choice": self.romance_player_choice,
                "romance_npc_choice": self.romance_npc_choice,
                "romance_outcome": self.romance_outcome,
                "romance_relationship_player_choice": self.romance_relationship_player_choice,
                "romance_relationship_npc_choice": self.romance_relationship_npc_choice,
                "romance_relationship_partner": self.romance_relationship_partner}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldModel":
        version = int(data.get("version") or 1)
        if version > VERSION or version < 1:
            raise ValueError(f"unsupported world model version {version}")
        return cls(world=World.from_dict(data.get("world") or {}),
                   characters={cid: CharacterState.from_dict(c) for cid, c in (data.get("characters") or {}).items()},
                   memories=MemoryStore.from_dict(data.get("memories") or {}),
                   agreements=AgreementBook.from_dict(data.get("agreements") or {}),
                   epistemics=EpistemicLedger.from_dict(data.get("epistemics") or {}),
                   drama=DramaBook.from_dict(data.get("drama") or {}),
                   threads=[Thread.from_dict(t) for t in data.get("threads") or []],
                   contacts=[ContactMessage.from_dict(c) for c in data.get("contacts") or []],
                   traces=[Trace.from_dict(t) for t in data.get("traces") or []],
                   seed=str(data.get("seed") or "world"), turn=int(data.get("turn") or 0),
                   endings=list(data.get("endings") or []),
                   player_availability=str(data.get("player_availability") or "awake"),
                   player_name=str(data.get("player_name") or "the player"),
                   known_names=list(data.get("known_names") or []),
                   home_of_player=str(data.get("home_of_player") or ""),
                   initiative_last_day={str(k): int(v) for k, v in
                                        (data.get("initiative_last_day") or {}).items()},
                   romance_player_choice=str(data.get("romance_player_choice") or ""),
                   romance_npc_choice=str(data.get("romance_npc_choice") or ""),
                   romance_outcome=str(data.get("romance_outcome") or ""),
                   romance_relationship_player_choice=str(data.get("romance_relationship_player_choice") or ""),
                   romance_relationship_npc_choice=str(data.get("romance_relationship_npc_choice") or ""),
                   romance_relationship_partner=str(data.get("romance_relationship_partner") or ""))
