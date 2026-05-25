from __future__ import annotations

import re

from .base import MAX_HIGHLIGHT_CHARS, MAX_HIGHLIGHT_TOKENS, SyntaxToken


NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")


class JsonSyntaxHighlighter:
    type_id = "json"

    def highlight(self, text: str) -> list[SyntaxToken]:
        if not text or len(text) > MAX_HIGHLIGHT_CHARS:
            return []
        tokens: list[SyntaxToken] = []
        i = 0
        n = len(text)
        while i < n and len(tokens) < MAX_HIGHLIGHT_TOKENS:
            ch = text[i]
            if ch in " \t\r\n":
                i += 1
                continue
            if ch == '"':
                end = self._string_end(text, i)
                kind = "key" if self._is_key(text, end) else "string"
                tokens.append(SyntaxToken(kind, i, end))
                i = end
                continue
            if ch in "{}[]:,":
                tokens.append(SyntaxToken("punctuation", i, i + 1))
                i += 1
                continue
            if text.startswith("true", i) and self._literal_boundary(text, i + 4):
                tokens.append(SyntaxToken("literal", i, i + 4))
                i += 4
                continue
            if text.startswith("false", i) and self._literal_boundary(text, i + 5):
                tokens.append(SyntaxToken("literal", i, i + 5))
                i += 5
                continue
            if text.startswith("null", i) and self._literal_boundary(text, i + 4):
                tokens.append(SyntaxToken("literal", i, i + 4))
                i += 4
                continue
            match = NUMBER_RE.match(text, i)
            if match:
                tokens.append(SyntaxToken("number", i, match.end()))
                i = match.end()
                continue
            i += 1
        return tokens

    def _string_end(self, text: str, start: int) -> int:
        i = start + 1
        escaped = False
        while i < len(text):
            ch = text[i]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                return i + 1
            i += 1
        return len(text)

    def _is_key(self, text: str, end: int) -> bool:
        i = end
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        return i < len(text) and text[i] == ":"

    def _literal_boundary(self, text: str, end: int) -> bool:
        return end >= len(text) or not (text[end].isalnum() or text[end] == "_")
