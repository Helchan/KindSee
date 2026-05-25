from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


MAX_HIGHLIGHT_CHARS = 300_000
MAX_HIGHLIGHT_TOKENS = 20_000


@dataclass(frozen=True)
class SyntaxToken:
    kind: str
    start: int
    end: int


class SyntaxHighlighter(Protocol):
    type_id: str

    def highlight(self, text: str) -> list[SyntaxToken]:
        ...


class NoopHighlighter:
    type_id = "text"

    def highlight(self, text: str) -> list[SyntaxToken]:
        return []


class SyntaxRegistry:
    def __init__(self) -> None:
        self._highlighters: dict[str, SyntaxHighlighter] = {}
        self._default = NoopHighlighter()

    def register(self, highlighter: SyntaxHighlighter) -> None:
        self._highlighters[highlighter.type_id] = highlighter

    def get(self, type_id: str | None) -> SyntaxHighlighter:
        if type_id and type_id in self._highlighters:
            return self._highlighters[type_id]
        return self._default
