from __future__ import annotations

import re
from pathlib import Path

from .base import EmptyPositionIndex, ParseResult, TreeNode


MAX_JAVA_CHECK_CHARS = 500_000
JAVA_STRONG_CONTENT_RE = re.compile(
    r"\b(?:package|import)\s+[A-Za-z_$][A-Za-z0-9_$.]*\s*;"
    r"|\b(?:public|private|protected)\s+(?:final\s+)?(?:class|interface|enum|record)\s+[A-Za-z_$][A-Za-z0-9_$]*"
    r"|\bpublic\s+static\s+void\s+main\s*\(",
)
JAVA_WEAK_CONTENT_RE = re.compile(r"\b(?:class|interface|enum|record)\s+[A-Za-z_$][A-Za-z0-9_$]*")


class JavaDocumentType:
    type_id = "java"
    display_name = "Java 文件"
    default_extension = ".java"
    file_dialog_patterns = ("*.java",)
    view_mode = "text"
    parse_on_change = True
    supports_format = False
    supports_compact = False
    empty_status = "请输入 Java 内容"

    def matches_path(self, path: Path) -> bool:
        return path.suffix.lower() == ".java"

    def matches_content(self, text: str) -> bool:
        return self.content_score(text) > 0

    def content_score(self, text: str) -> int:
        stripped = text.strip()
        if not stripped or len(stripped) > MAX_JAVA_CHECK_CHARS:
            return 0
        if JAVA_STRONG_CONTENT_RE.search(stripped):
            return 82
        if JAVA_WEAK_CONTENT_RE.search(stripped) and ";" in stripped:
            return 62
        return 0

    def parse(self, text: str) -> ParseResult:
        if not text.strip():
            return ParseResult(None, EmptyPositionIndex(), self.empty_status, False)
        if len(text) > MAX_JAVA_CHECK_CHARS:
            return ParseResult(None, EmptyPositionIndex(), "", False)
        error = _check_java_balance(text)
        if error:
            return ParseResult(None, EmptyPositionIndex(), error, True)
        return ParseResult(None, EmptyPositionIndex(), "", False)

    def format_text(self, text: str) -> str:
        raise ValueError("Java 文件暂不支持格式化")

    def compact_text(self, text: str) -> str:
        raise ValueError("Java 文件暂不支持压缩")

    def copy_node(self, node: TreeNode) -> str:
        return ""

    def copy_node_value(self, node: TreeNode) -> str:
        return ""

    def copy_node_path(self, node: TreeNode) -> str:
        return ""


def _check_java_balance(text: str) -> str:
    stack: list[tuple[str, int, int]] = []
    pairs = {"{": "}", "[": "]", "(": ")"}
    closers = {value: key for key, value in pairs.items()}
    line = 1
    column = 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "\n":
            line += 1
            column = 1
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i, line, column = _skip_line_comment(text, i, line, column)
            continue
        if ch == "/" and nxt == "*":
            skipped = _skip_block_comment(text, i, line, column)
            if skipped is None:
                return f"语法错误：第 {line} 行，第 {column} 列，块注释未闭合"
            i, line, column = skipped
            continue
        if ch in ("'", '"'):
            skipped = _skip_quoted(text, i, line, column, ch)
            if skipped is None:
                return f"语法错误：第 {line} 行，第 {column} 列，字符串或字符字面量未闭合"
            i, line, column = skipped
            continue
        if ch in pairs:
            stack.append((ch, line, column))
        elif ch in closers:
            if not stack or stack[-1][0] != closers[ch]:
                return f"语法错误：第 {line} 行，第 {column} 列，括号不匹配"
            stack.pop()
        i += 1
        column += 1
    if stack:
        opener, opener_line, opener_column = stack[-1]
        return f"语法错误：第 {opener_line} 行，第 {opener_column} 列，'{opener}' 未闭合"
    return ""


def _skip_line_comment(text: str, start: int, line: int, column: int) -> tuple[int, int, int]:
    i = start + 2
    column += 2
    while i < len(text) and text[i] != "\n":
        i += 1
        column += 1
    return i, line, column


def _skip_block_comment(text: str, start: int, line: int, column: int) -> tuple[int, int, int] | None:
    i = start + 2
    column += 2
    while i < len(text):
        if text[i] == "\n":
            line += 1
            column = 1
            i += 1
            continue
        if text[i] == "*" and i + 1 < len(text) and text[i + 1] == "/":
            return i + 2, line, column + 2
        i += 1
        column += 1
    return None


def _skip_quoted(text: str, start: int, line: int, column: int, quote: str) -> tuple[int, int, int] | None:
    i = start + 1
    column += 1
    escaped = False
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            return None
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == quote:
            return i + 1, line, column + 1
        i += 1
        column += 1
    return None
