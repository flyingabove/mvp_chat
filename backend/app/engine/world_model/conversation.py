"""Questions the player addressed to characters, tracked until they are resolved.

A question closes only when the addressee answered, refused, said they do not
know, or acknowledged that they will answer later. Other people's chatter does
not close it, and nobody answers on behalf of an absent addressee.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

OPEN = "open"
RESOLUTIONS = frozenset({"answered", "refused", "unknown", "deferred"})
LAPSED = "lapsed"
# An unresolved question this old no longer belongs in the scene.
LAPSE_AFTER_TURNS = 12
MAX_OPEN = 6
# The extractor's verdict can lag or miss, and a question left open is re-demanded every turn (live beta
# 2026-09-29: Riko re-answered one question for ~8 turns; a second beta run had Minori and Hikaru each answer a
# question twice). Repeating an answer is the visible failure, forgetting one is not (owner rule), so the engine
# closes a question on the addressee's first reply after it was asked. If they dodged it, it is let go.
MAX_DIRECTED_REPLIES = 1
KEEP_CLOSED = 20


@dataclass
class PendingQuestion:
    id: str
    addressee: str
    text: str
    asked_turn: int
    status: str = OPEN
    resolved_turn: int = 0
    replies: int = 0

    @property
    def is_open(self) -> bool:
        return self.status == OPEN

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "addressee": self.addressee, "text": self.text,
                "asked_turn": self.asked_turn, "status": self.status, "resolved_turn": self.resolved_turn,
                "replies": self.replies}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PendingQuestion":
        return cls(str(raw["id"]), str(raw["addressee"]), str(raw.get("text") or ""),
                   int(raw.get("asked_turn") or 0), str(raw.get("status") or OPEN),
                   int(raw.get("resolved_turn") or 0), int(raw.get("replies") or 0))


@dataclass
class ConversationState:
    questions: list[PendingQuestion] = field(default_factory=list)
    counter: int = 0

    def open_questions(self) -> list[PendingQuestion]:
        return [q for q in self.questions if q.is_open]

    def ask(self, addressee: str, text: str, turn: int) -> Optional[PendingQuestion]:
        text = " ".join(str(text or "").split())[:200]
        if not addressee or not text:
            return None
        for existing in self.open_questions():
            if existing.addressee == addressee and existing.text.lower() == text.lower():
                return existing
        self.counter += 1
        question = PendingQuestion(f"q{self.counter}", addressee, text, turn)
        self.questions.append(question)
        overflow = self.open_questions()[:-MAX_OPEN]
        for old in overflow:
            old.status, old.resolved_turn = LAPSED, turn
        return question

    def resolve(self, question_id: str, status: str, turn: int) -> bool:
        if status not in RESOLUTIONS:
            return False
        for question in self.open_questions():
            if question.id == question_id:
                question.status, question.resolved_turn = status, turn
                return True
        return False

    def note_reply(self, addressee: str, turn: int) -> None:
        """The addressee spoke this turn: count it, and close a question they keep answering."""
        for question in self.open_questions():
            if question.addressee != addressee or question.asked_turn > turn:
                continue
            question.replies += 1
            if question.replies >= MAX_DIRECTED_REPLIES:
                question.status, question.resolved_turn = "answered", turn

    def lapse_stale(self, turn: int) -> None:
        for question in self.open_questions():
            if turn - question.asked_turn >= LAPSE_AFTER_TURNS:
                question.status, question.resolved_turn = LAPSED, turn
        closed = [q for q in self.questions if not q.is_open][-KEEP_CLOSED:]
        self.questions = [q for q in self.questions if q.is_open or q in closed]

    def to_dict(self) -> dict[str, Any]:
        return {"questions": [q.to_dict() for q in self.questions], "counter": self.counter}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ConversationState":
        questions = [PendingQuestion.from_dict(q) for q in raw.get("questions") or []]
        return cls(questions, max(int(raw.get("counter") or 0), len(questions)))
