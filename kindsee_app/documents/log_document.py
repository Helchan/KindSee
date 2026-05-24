from __future__ import annotations

from pathlib import Path

from .base import EmptyPositionIndex, ParseResult, TreeNode


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
