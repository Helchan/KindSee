from __future__ import annotations

import re

from .base import MAX_HIGHLIGHT_CHARS, MAX_HIGHLIGHT_TOKENS, SyntaxToken


NAME_RE = re.compile(r"[A-Za-z_:\-][A-Za-z0-9_.:\-]*")


class XmlSyntaxHighlighter:
    type_id = "xml"

    def highlight(self, text: str) -> list[SyntaxToken]:
        if not text or len(text) > MAX_HIGHLIGHT_CHARS:
            return []
        tokens: list[SyntaxToken] = []
        i = 0
        n = len(text)
        while i < n and len(tokens) < MAX_HIGHLIGHT_TOKENS:
            if text[i] != "<":
                i += 1
                continue
            if text.startswith("<!--", i):
                end = text.find("-->", i + 4)
                end = n if end < 0 else end + 3
                tokens.append(SyntaxToken("literal", i, end))
                i = end
                continue
            if text.startswith("<![CDATA[", i):
                end = text.find("]]>", i + 9)
                end = n if end < 0 else end + 3
                tokens.append(SyntaxToken("literal", i, end))
                i = end
                continue
            i = self._highlight_tag(text, i, tokens)
        return tokens

    def _highlight_tag(self, text: str, start: int, tokens: list[SyntaxToken]) -> int:
        n = len(text)
        i = start
        tokens.append(SyntaxToken("punctuation", i, i + 1))
        i += 1
        if i < n and text[i] in "/?!":
            tokens.append(SyntaxToken("punctuation", i, i + 1))
            i += 1
        while i < n and len(tokens) < MAX_HIGHLIGHT_TOKENS:
            ch = text[i]
            if ch in " \t\r\n":
                i += 1
                continue
            if ch in "'\"":
                end = self._quoted_end(text, i)
                tokens.append(SyntaxToken("string", i, end))
                i = end
                continue
            if ch == "=":
                tokens.append(SyntaxToken("punctuation", i, i + 1))
                i += 1
                continue
            if ch == ">":
                tokens.append(SyntaxToken("punctuation", i, i + 1))
                return i + 1
            if ch == "/" and i + 1 < n and text[i + 1] == ">":
                tokens.append(SyntaxToken("punctuation", i, i + 2))
                return i + 2
            match = NAME_RE.match(text, i)
            if match:
                tokens.append(SyntaxToken("key", match.start(), match.end()))
                i = match.end()
                continue
            tokens.append(SyntaxToken("punctuation", i, i + 1))
            i += 1
        return i

    def _quoted_end(self, text: str, start: int) -> int:
        quote = text[start]
        i = start + 1
        while i < len(text):
            if text[i] == quote:
                return i + 1
            i += 1
        return len(text)
