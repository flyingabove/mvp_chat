from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class KnowledgeChunk:
    id: str
    text: str
    tier: str
    source: str
    certainty: str
    known_by: List[str] = field(default_factory=list)
    not_known_by: List[str] = field(default_factory=list)
    maybe_known_by: List[str] = field(default_factory=list)


def normalize_party_token(value: str) -> str:
    token = (value or "").strip().lower().replace(" ", "_")
    if token in {"all", "everyone", "all_characters", "allcharacters", "common_knowledge"}:
        return "all_characters"
    return token


def normalize_parties(values: list | None) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values or []:
        token = normalize_party_token(str(v))
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out
