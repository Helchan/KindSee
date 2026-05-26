from __future__ import annotations

from pathlib import Path
import re

from .base import EmptyPositionIndex, ParseResult, TreeNode


LOG_LINE_RE = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|\[[A-Z][A-Z0-9_-]*\]|[A-Z][A-Z0-9_-]*\b).*?\b(?:TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\b",
    re.IGNORECASE,
)


class LogDocumentType:
    type_id = "log"
    display_name = "LOG 文件"
    default_extension = ".log"
    file_dialog_patterns = ("*.log",)
    view_mode = "text"
    parse_on_change = False
    supports_format = False
    supports_compact = False
    empty_status = "请输入日志内容"

    def matches_path(self, path: Path) -> bool:
        return path.suffix.lower() == ".log"

    def matches_content(self, text: str) -> bool:
        return self.content_score(text) > 0

    def content_score(self, text: str) -> int:
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            return 0
        sample = lines[:20]
        matches = sum(1 for line in sample if LOG_LINE_RE.search(line))
        if matches >= 3 or matches >= max(2, len(sample) // 2):
            return 70
        return 0

    def parse(self, text: str) -> ParseResult:
        status = self.empty_status if not text else ""
        return ParseResult(None, EmptyPositionIndex(), status, False)

    def format_text(self, text: str) -> str:
        raise ValueError("LOG 文件不支持格式化")

    def compact_text(self, text: str) -> str:
        raise ValueError("LOG 文件不支持压缩")

    def copy_node(self, node: TreeNode) -> str:
        return ""

    def copy_node_value(self, node: TreeNode) -> str:
        return ""

    def copy_node_path(self, node: TreeNode) -> str:
        return ""
