from __future__ import annotations

import re

from .base import MAX_HIGHLIGHT_CHARS, MAX_HIGHLIGHT_TOKENS, SyntaxToken
from ..sql_keywords import SQL_KEYWORDS, SQL_LITERALS


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


class SqlSyntaxHighlighter:
    type_id = "sql"

    def highlight(self, text: str) -> list[SyntaxToken]:
        if not text or len(text) > MAX_HIGHLIGHT_CHARS:
            return []
        tokens: list[SyntaxToken] = []
        i = 0
        n = len(text)
        while i < n and len(tokens) < MAX_HIGHLIGHT_TOKENS:
            ch = text[i]
            nxt = text[i + 1] if i + 1 < n else ""
            if ch in " \t\r\n":
                i += 1
                continue
            if ch == "-" and nxt == "-":
                end = text.find("\n", i + 2)
                end = n if end < 0 else end
                tokens.append(SyntaxToken("literal", i, end))
                i = end
                continue
            if ch == "/" and nxt == "*":
                end = text.find("*/", i + 2)
                end = n if end < 0 else end + 2
                tokens.append(SyntaxToken("literal", i, end))
                i = end
                continue
            if ch in ("'", '"', "`"):
                end = self._quoted_end(text, i, ch)
                tokens.append(SyntaxToken("string", i, end))
                i = end
                continue
            if ch == "[":
                end = text.find("]", i + 1)
                end = n if end < 0 else end + 1
                tokens.append(SyntaxToken("string", i, end))
                i = end
                continue
            match = IDENT_RE.match(text, i)
            if match:
                word = match.group(0).lower()
                if word in SQL_KEYWORDS:
                    tokens.append(SyntaxToken("key", match.start(), match.end()))
                elif word in SQL_LITERALS:
                    tokens.append(SyntaxToken("literal", match.start(), match.end()))
                i = match.end()
                continue
            match = NUMBER_RE.match(text, i)
            if match:
                tokens.append(SyntaxToken("number", match.start(), match.end()))
                i = match.end()
                continue
            if ch in "();,.=+-*/%<>!|":
                tokens.append(SyntaxToken("punctuation", i, i + 1))
            i += 1
        return tokens

    def _quoted_end(self, text: str, start: int, quote: str) -> int:
        i = start + 1
        while i < len(text):
            ch = text[i]
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if ch == quote:
                if nxt == quote:
                    i += 2
                    continue
                return i + 1
            i += 1
        return len(text)
