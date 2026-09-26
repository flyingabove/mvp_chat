"""Per-character memory: one person's perspective, always with a source.

Text refers to people as `@id` when the owner knew who it was; the ID becomes a
name only for a viewer who knows that name. An unsure sighting stays a
descriptor, and its `actual` field is engine-only: never rendered, never sent to
the LLM, never shown to the player.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

REF = re.compile(r"@([A-Za-z0-9_]+)")
TOKEN = re.compile(r"[\w']+")
SOURCES = ("witnessed", "overheard", "authored", "promised")   # plus told_by:<id>
KINDS = ("fact", "lore", "promise", "contact", "dialogue", "claim")
STOPWORDS = frozenset("the a an and or of to in on at is are was were i you he she it we they my your "
                      "me him her them this that what who where when do did have has be been with for".split())


def valid_source(source: str) -> bool:
    return source in SOURCES or (source.startswith("told_by:") and len(source) > len("told_by:"))


@dataclass(frozen=True)
class Ref:
    descriptor: str
    actual: str = ""          # engine-only truth
    identified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"descriptor": self.descriptor, "actual": self.actual, "identified": self.identified}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Ref":
        return cls(str(data.get("descriptor") or ""), str(data.get("actual") or ""), bool(data.get("identified")))


@dataclass
class Memory:
    id: str
    owner: str
    text: str
    source: str
    minute: int
    confidence: float = 1.0
    kind: str = "fact"
    event_id: str = ""
    refs: tuple[Ref, ...] = ()
    due: Optional[int] = None          # promises
    status: str = "open"               # promises: open | kept | broken
    private: bool = False              # never gossiped
    counterpart: str = ""              # promises: the other party
    root_source_id: str = ""           # one independent observation/claim across gossip hops
    parent_memory_id: str = ""          # immediate transmission ancestor
    agreement_id: str = ""             # recall projection of authoritative agreement
    assertion_id: str = ""             # epistemic claim behind a retelling
    transmission_id: str = ""          # immediate delivery in the claim ledger

    def __post_init__(self) -> None:
        if not valid_source(self.source):
            raise ValueError(f"memory needs a channel, got source={self.source!r}")
        if self.kind not in KINDS:
            raise ValueError(f"unknown memory kind {self.kind!r}")
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def mentions(self) -> set[str]:
        return set(REF.findall(self.text))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "owner": self.owner, "text": self.text, "source": self.source,
                "minute": self.minute, "confidence": self.confidence, "kind": self.kind,
                "event_id": self.event_id, "refs": [r.to_dict() for r in self.refs], "due": self.due,
                "status": self.status, "private": self.private, "counterpart": self.counterpart,
                "root_source_id": self.root_source_id, "parent_memory_id": self.parent_memory_id,
                "agreement_id": self.agreement_id, "assertion_id": self.assertion_id,
                "transmission_id": self.transmission_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        return cls(id=str(data["id"]), owner=str(data["owner"]), text=str(data.get("text") or ""),
                   source=str(data.get("source") or "witnessed"), minute=int(data.get("minute") or 0),
                   confidence=float(data.get("confidence", 1.0)), kind=str(data.get("kind") or "fact"),
                   event_id=str(data.get("event_id") or ""),
                   refs=tuple(Ref.from_dict(r) for r in data.get("refs") or []),
                   due=data.get("due"), status=str(data.get("status") or "open"),
                   private=bool(data.get("private")), counterpart=str(data.get("counterpart") or ""),
                   root_source_id=str(data.get("root_source_id") or ""),
                   parent_memory_id=str(data.get("parent_memory_id") or ""),
                   agreement_id=str(data.get("agreement_id") or ""),
                   assertion_id=str(data.get("assertion_id") or ""),
                   transmission_id=str(data.get("transmission_id") or ""))


def _tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall((text or "").lower()) if t not in STOPWORDS]


def render(text: str, names: dict[str, str], known: Optional[set[str]] = None,
           descriptors: Optional[dict[str, str]] = None) -> str:
    """Turn `@id` into a name the viewer knows, else a descriptor ("the hair stylist").

    `known=None` means the viewer knows every name (engine/NPC view).
    """
    descriptors = descriptors or {}

    def _swap(match: re.Match) -> str:
        entity_id = match.group(1)
        if known is None or entity_id in known:
            return names.get(entity_id, entity_id.replace("_", " "))
        return descriptors.get(entity_id) or "someone"
    return REF.sub(_swap, text or "")


@dataclass
class MemoryStore:
    memories: list[Memory] = field(default_factory=list)
    counter: int = 0

    def add(self, owner: str, text: str, source: str, minute: int, **fields: Any) -> Memory:
        self.counter += 1
        memory = Memory(id=f"M{self.counter}", owner=owner, text=text, source=source, minute=minute, **fields)
        self.memories.append(memory)
        return memory

    def of(self, owner: str) -> list[Memory]:
        return [m for m in self.memories if m.owner == owner]

    def knows_event(self, owner: str, event_id: str) -> bool:
        return bool(event_id) and any(m.owner == owner and m.event_id == event_id for m in self.memories)

    def has_text(self, owner: str, text: str) -> bool:
        return any(m.owner == owner and m.text == text for m in self.memories)

    def open_promises(self, owner: Optional[str] = None) -> list[Memory]:
        return [m for m in self.memories if m.kind == "promise" and m.status == "open"
                and (owner is None or m.owner == owner)]

    def search(self, owner: str, query: str, mentions: Iterable[str] = (), k: int = 3,
               kinds: Optional[Iterable[str]] = None) -> list[Memory]:
        """Rank ONLY `owner`'s memories: BM25-style overlap + @id mention boost + recency tiebreak."""
        pool = [m for m in self.of(owner) if kinds is None or m.kind in set(kinds)]
        if not pool or k <= 0:
            return []
        query_terms = Counter(_tokens(query))
        docs = [_tokens(REF.sub(lambda mt: mt.group(1), m.text)) for m in pool]
        avg_len = sum(len(d) for d in docs) / len(docs) or 1.0
        doc_freq = Counter(t for d in docs for t in set(d))
        wanted = set(mentions)
        scored = []
        for memory, doc in zip(pool, docs):
            freqs = Counter(doc)
            score = 0.0
            for term in query_terms:
                if term in freqs:
                    idf = math.log(1 + (len(docs) - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
                    tf = freqs[term]
                    score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(doc) / avg_len))
            score += 3.0 * len(memory.mentions() & wanted)
            if score > 0:
                scored.append((score, memory.minute, memory))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [memory for _, _, memory in scored[:k]]

    def to_dict(self) -> dict[str, Any]:
        return {"counter": self.counter, "memories": [m.to_dict() for m in self.memories]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryStore":
        return cls(memories=[Memory.from_dict(m) for m in data.get("memories") or []],
                   counter=int(data.get("counter") or 0))
