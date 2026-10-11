"""Authored-content checks that report exact field paths for author review.

Text is never rewritten here: a literal backslash sequence may be intentional,
so the fix belongs in the story file once an author has looked at it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

_BACKSLASH = "\\"
_ESCAPES = {_BACKSLASH + "n": "literal_escaped_newline", _BACKSLASH + "t": "literal_escaped_tab"}
_REPLACEMENT_CHAR = "�"


@dataclass(frozen=True)
class ContentIssue:
    path: str
    kind: str
    count: int

    def message(self) -> str:
        return f"{self.path}: {self.count} x {self.kind}"


def _strings(node: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def find_text_defects(story: dict[str, Any]) -> list[ContentIssue]:
    """Return decoding defects in every authored string of a story dict."""
    issues: list[ContentIssue] = []
    for path, text in _strings(story, ""):
        for sequence, kind in _ESCAPES.items():
            if count := text.count(sequence):
                issues.append(ContentIssue(path, kind, count))
        if count := text.count(_REPLACEMENT_CHAR):
            issues.append(ContentIssue(path, "replacement_character", count))
    return issues
