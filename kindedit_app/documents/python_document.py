from __future__ import annotations

import ast
import re
from pathlib import Path

from .base import EmptyPositionIndex, ParseResult, TreeNode


MAX_PYTHON_CHECK_CHARS = 500_000
PYTHON_CONTENT_RE = re.compile(
    r"\b(?:def|class|import|async\s+def)\s+[A-Za-z_][A-Za-z0-9_]*"
    r"|\bfrom\s+[A-Za-z_][A-Za-z0-9_.]*\s+import\b"
    r"|\bif\s+__name__\s*==\s*['\"]__main__['\"]",
)


class PythonDocumentType:
    type_id = "python"
    display_name = "Python 文件"
    default_extension = ".py"
    file_dialog_patterns = ("*.py", "*.pyw")
    view_mode = "text"
    parse_on_change = True
    supports_format = False
    supports_compact = False
    empty_status = "请输入 Python 内容"

    def matches_path(self, path: Path) -> bool:
        return path.suffix.lower() in (".py", ".pyw")

    def matches_content(self, text: str) -> bool:
        return self.content_score(text) > 0

    def content_score(self, text: str) -> int:
        stripped = text.strip()
        if not stripped or len(stripped) > MAX_PYTHON_CHECK_CHARS:
            return 0
        if not PYTHON_CONTENT_RE.search(stripped):
            return 0
        try:
            ast.parse(stripped)
        except SyntaxError:
            return 0
        return 85

    def parse(self, text: str) -> ParseResult:
        if not text.strip():
            return ParseResult(None, EmptyPositionIndex(), self.empty_status, False)
        if len(text) > MAX_PYTHON_CHECK_CHARS:
            return ParseResult(None, EmptyPositionIndex(), "", False)
        try:
            ast.parse(text)
        except SyntaxError as exc:
            line = exc.lineno or 1
            column = (exc.offset or 1)
            message = exc.msg or "invalid syntax"
            return ParseResult(None, EmptyPositionIndex(), f"语法错误：第 {line} 行，第 {column} 列，{message}", True)
        return ParseResult(None, EmptyPositionIndex(), "", False)

    def format_text(self, text: str) -> str:
        raise ValueError("Python 文件暂不支持格式化")

    def compact_text(self, text: str) -> str:
        raise ValueError("Python 文件暂不支持压缩")

    def copy_node(self, node: TreeNode) -> str:
        return ""

    def copy_node_value(self, node: TreeNode) -> str:
        return ""

    def copy_node_path(self, node: TreeNode) -> str:
        return ""
