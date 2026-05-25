from __future__ import annotations

import re

from .base import MAX_HIGHLIGHT_CHARS, MAX_HIGHLIGHT_TOKENS, SyntaxToken


INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
LINK_RE = re.compile(r"!?\[[^\]\n]+\]\([^) \n]+(?:\s+\"[^\"]*\")?\)")
STRONG_RE = re.compile(r"(\*\*|__)(?=\S).+?(?<=\S)\1")
EMPHASIS_RE = re.compile(r"(?<!\*)\*(?!\*)(?=\S).+?(?<=\S)\*(?!\*)|(?<!_)_(?!_)(?=\S).+?(?<=\S)_(?!_)")
HEADING_RE = re.compile(r"^(#{1,6})(\s+.*)?$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+")
QUOTE_RE = re.compile(r"^(\s*>+)\s?")
RULE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


class MarkdownSyntaxHighlighter:
    type_id = "markdown"

    def highlight(self, text: str) -> list[SyntaxToken]:
        if not text or len(text) > MAX_HIGHLIGHT_CHARS:
            return []
        tokens: list[SyntaxToken] = []
        offset = 0
        in_fence = False
        fence_marker = ""
        for line in text.splitlines(keepends=True):
            line_text = line.rstrip("\r\n")
            stripped = line_text.lstrip()
            indent = len(line_text) - len(stripped)
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                tokens.append(SyntaxToken("literal", offset + indent, offset + len(line_text)))
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = ""
                offset += len(line)
                if len(tokens) >= MAX_HIGHLIGHT_TOKENS:
                    break
                continue
            if in_fence:
                if line_text:
                    tokens.append(SyntaxToken("string", offset, offset + len(line_text)))
                offset += len(line)
                if len(tokens) >= MAX_HIGHLIGHT_TOKENS:
                    break
                continue
            self._line_tokens(line_text, offset, tokens)
            offset += len(line)
            if len(tokens) >= MAX_HIGHLIGHT_TOKENS:
                break
        return tokens[:MAX_HIGHLIGHT_TOKENS]

    def _line_tokens(self, line: str, offset: int, tokens: list[SyntaxToken]) -> None:
        heading = HEADING_RE.match(line)
        if heading:
            tokens.append(SyntaxToken("key", offset + heading.start(1), offset + heading.end(1)))
        quote = QUOTE_RE.match(line)
        if quote:
            tokens.append(SyntaxToken("literal", offset + quote.start(1), offset + quote.end(1)))
        listing = LIST_RE.match(line)
        if listing:
            tokens.append(SyntaxToken("key", offset + listing.start(2), offset + listing.end(2)))
        if RULE_RE.match(line) or TABLE_SEPARATOR_RE.match(line):
            tokens.append(SyntaxToken("punctuation", offset, offset + len(line)))
        for match in INLINE_CODE_RE.finditer(line):
            tokens.append(SyntaxToken("string", offset + match.start(), offset + match.end()))
        for match in LINK_RE.finditer(line):
            tokens.append(SyntaxToken("literal", offset + match.start(), offset + match.end()))
        for match in STRONG_RE.finditer(line):
            tokens.append(SyntaxToken("key", offset + match.start(), offset + match.end()))
        for match in EMPHASIS_RE.finditer(line):
            tokens.append(SyntaxToken("literal", offset + match.start(), offset + match.end()))
