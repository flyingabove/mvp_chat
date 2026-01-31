from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Step:
    kind: str  # e.g., "action", "assert", "note"
    description: str
    fn: Optional[Callable[..., Any]] = None
    kwargs: Dict[str, Any] = field(default_factory=dict)
    uses_llm: bool = False  # flag so UI can label LLM-backed steps

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "description": self.description,
            "has_fn": self.fn is not None,
            "kwargs": self.kwargs,
            "uses_llm": self.uses_llm,
        }


@dataclass
class Scenario:
    id: str
    title: str
    description: str
    tags: List[str]
    requires_api_key: bool = False
    requires_cache: bool = False
    steps: List[Step] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "requires_api_key": self.requires_api_key,
            "requires_cache": self.requires_cache,
            "steps": [s.to_dict() for s in self.steps],
        }
