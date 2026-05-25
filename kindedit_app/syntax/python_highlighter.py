from __future__ import annotations

import keyword
import re

from .base import MAX_HIGHLIGHT_CHARS, MAX_HIGHLIGHT_TOKENS, SyntaxToken


KEYWORDS = set(keyword.kwlist)
LITERALS = {"True", "False", "None", "Ellipsis"}
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER_RE = re.compile(r"(?:0[xX][0-9A-Fa-f_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d[\d_]*)?)[jJ]?")
PREFIX_CHARS = set("rRuUbBfF")


class PythonSyntaxHighlighter:
    type_id = "python"

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
            if ch == "#":
                end = text.find("\n", i + 1)
                end = n if end < 0 else end
                tokens.append(SyntaxToken("literal", i, end))
                i = end
                continue
            string_start = self._string_start(text, i)
            if string_start is not None:
                end = self._string_end(text, string_start)
                tokens.append(SyntaxToken("string", i, end))
                i = end
                continue
            match = IDENT_RE.match(text, i)
            if match:
                word = match.group(0)
                if word in KEYWORDS:
                    tokens.append(SyntaxToken("key", match.start(), match.end()))
                elif word in LITERALS:
                    tokens.append(SyntaxToken("literal", match.start(), match.end()))
                i = match.end()
                continue
            match = NUMBER_RE.match(text, i)
            if match:
                tokens.append(SyntaxToken("number", match.start(), match.end()))
                i = match.end()
                continue
            if ch in "{}[]():,.;=+-*/%@<>!&|~^":
                tokens.append(SyntaxToken("punctuation", i, i + 1))
            i += 1
        return tokens

    def _string_start(self, text: str, start: int) -> int | None:
        if text[start] in ("'", '"'):
            return start
        i = start
        while i < len(text) and text[i] in PREFIX_CHARS and i - start < 3:
            i += 1
        if i > start and i < len(text) and text[i] in ("'", '"'):
            return i
        return None

    def _string_end(self, text: str, quote_start: int) -> int:
        quote = text[quote_start]
        triple = text.startswith(quote * 3, quote_start)
        i = quote_start + (3 if triple else 1)
        escaped = False
        while i < len(text):
            if triple and text.startswith(quote * 3, i):
                return i + 3
            ch = text[i]
            if not triple and ch == "\n":
                return i
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif not triple and ch == quote:
                return i + 1
            i += 1
        return len(text)
