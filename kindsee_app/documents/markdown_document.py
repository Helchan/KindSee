from __future__ import annotations

import re
from pathlib import Path

from .base import EmptyPositionIndex, ParseResult, TreeNode


MAX_MARKDOWN_CHECK_CHARS = 500_000
MARKDOWN_CONTENT_RE = re.compile(
    r"(?m)^(?:#{1,6}\s+\S|>\s+\S|[-*+]\s+\S|\d+\.\s+\S|```|~~~|\|.+\|)"
    r"|!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\)",
)


class MarkdownDocumentType:
    type_id = "markdown"
    display_name = "Markdown 文件"
    default_extension = ".md"
    file_dialog_patterns = ("*.md", "*.markdown", "*.mdown")
    view_mode = "preview"
    parse_on_change = True
    supports_format = False
    supports_compact = False
    empty_status = "请输入 Markdown 内容"

    def matches_path(self, path: Path) -> bool:
        return path.suffix.lower() in (".md", ".markdown", ".mdown")

    def matches_content(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped or len(stripped) > MAX_MARKDOWN_CHECK_CHARS:
            return False
        return bool(MARKDOWN_CONTENT_RE.search(stripped))

    def parse(self, text: str) -> ParseResult:
        if not text.strip():
            return ParseResult(None, EmptyPositionIndex(), self.empty_status, False)
        if len(text) > MAX_MARKDOWN_CHECK_CHARS:
            return ParseResult(None, EmptyPositionIndex(), "", False)
        error = _check_fences(text)
        if error:
            return ParseResult(None, EmptyPositionIndex(), error, True)
        return ParseResult(None, EmptyPositionIndex(), "", False)

    def format_text(self, text: str) -> str:
        raise ValueError("Markdown 文件暂不支持格式化")

    def compact_text(self, text: str) -> str:
        raise ValueError("Markdown 文件不支持压缩")

    def copy_node(self, node: TreeNode) -> str:
        return ""

    def copy_node_value(self, node: TreeNode) -> str:
        return ""

    def copy_node_path(self, node: TreeNode) -> str:
        return ""


def _check_fences(text: str) -> str:
    fence_marker = ""
    fence_line = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not fence_marker:
                fence_marker = marker
                fence_line = line_number
            elif marker == fence_marker:
                fence_marker = ""
                fence_line = 0
    if fence_marker:
        return f"语法错误：第 {fence_line} 行，第 1 列，代码块未闭合"
    return ""
