from __future__ import annotations

from pathlib import Path

from .base import EmptyPositionIndex, ParseResult, TreeNode


class TextDocumentType:
    type_id = "text"
    display_name = "TXT 文件"
    default_extension = ".txt"
    file_dialog_patterns = ("*.txt",)
    view_mode = "text"
    parse_on_change = False
    supports_format = False
    supports_compact = False
    empty_status = "请输入文本内容"

    def matches_path(self, path: Path) -> bool:
        return path.suffix.lower() == ".txt"

    def parse(self, text: str) -> ParseResult:
        status = self.empty_status if not text else ""
        return ParseResult(None, EmptyPositionIndex(), status, False)

    def format_text(self, text: str) -> str:
        raise ValueError("TXT 文件不支持格式化")

    def compact_text(self, text: str) -> str:
        raise ValueError("TXT 文件不支持压缩")

    def copy_node(self, node: TreeNode) -> str:
        return ""

    def copy_node_value(self, node: TreeNode) -> str:
        return ""

    def copy_node_path(self, node: TreeNode) -> str:
        return ""
