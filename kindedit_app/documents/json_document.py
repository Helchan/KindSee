from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .base import EmptyPositionIndex, ParseResult, TreeNode, refresh_tree_states


def display_scalar(value) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return str(value)


def json_value_text(value, pretty: bool = True) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":"))
    if isinstance(value, str):
        return value
    return display_scalar(value)


def node_kind(value) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "field"


def make_display(label: str, value, is_root: bool = False) -> str:
    prefix = "Root" if is_root else f"{label}:"
    if isinstance(value, dict):
        return f"{prefix} {{{len(value)}}}"
    if isinstance(value, list):
        return f"{prefix} [{len(value)}]"
    return f"{prefix} {display_scalar(value)}"


def build_tree(value) -> TreeNode:
    root = TreeNode("Root", value, 0, None, (), node_kind(value), expanded=True)
    root.display_text = make_display("Root", value, True)

    def add_children(node: TreeNode) -> None:
        if isinstance(node.value, dict):
            iterable = node.value.items()
        elif isinstance(node.value, list):
            iterable = ((str(i), v) for i, v in enumerate(node.value))
        else:
            return
        for label, child_value in iterable:
            child = TreeNode(
                label=str(label),
                value=child_value,
                depth=node.depth + 1,
                parent=node,
                path=node.path + (str(label),),
                kind=node_kind(child_value),
                expanded=False,
            )
            child.display_text = make_display(child.label, child.value)
            node.children.append(child)
            add_children(child)

    add_children(root)
    refresh_tree_states(root)
    return root


class JsonPositionIndex:
    def __init__(self, text: str):
        self.text = text
        self.positions: dict[tuple[str, ...], tuple[int, int]] = {}
        self.value_spans: dict[tuple[str, ...], tuple[int, int]] = {}
        self.cursor_positions: dict[tuple[str, ...], int] = {}
        self._parse_value(0, ())

    @classmethod
    def build(cls, text: str) -> "JsonPositionIndex | EmptyPositionIndex":
        try:
            return cls(text)
        except Exception:
            return EmptyPositionIndex()

    def _skip_ws(self, i: int) -> int:
        n = len(self.text)
        while i < n and self.text[i] in " \t\r\n":
            i += 1
        return i

    def _parse_string(self, i: int) -> tuple[str, int]:
        if self.text[i] != '"':
            raise ValueError("expected string")
        start = i
        i += 1
        escaped = False
        while i < len(self.text):
            ch = self.text[i]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                raw = self.text[start : i + 1]
                return json.loads(raw), i + 1
            i += 1
        raise ValueError("unterminated string")

    def _parse_number(self, i: int) -> int:
        match = re.match(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", self.text[i:])
        if not match:
            raise ValueError("expected number")
        return i + match.end()

    def _parse_value(self, i: int, path: tuple[str, ...]) -> int:
        i = self._skip_ws(i)
        start = i
        if i >= len(self.text):
            raise ValueError("empty")
        ch = self.text[i]
        self.positions[path] = (start, min(start + 1, len(self.text)))
        cursor_start = start + 1 if not path and ch in "{[" else start
        self.cursor_positions.setdefault(path, cursor_start)
        if ch == "{":
            i += 1
            i = self._skip_ws(i)
            if i < len(self.text) and self.text[i] == "}":
                self.value_spans[path] = (start, i + 1)
                return i + 1
            while True:
                i = self._skip_ws(i)
                key_start = i
                key, i = self._parse_string(i)
                i = self._skip_ws(i)
                if self.text[i] != ":":
                    raise ValueError("expected colon")
                i = self._skip_ws(i + 1)
                child_path = path + (key,)
                self.cursor_positions[child_path] = key_start + 1
                i = self._parse_value(i, child_path)
                self.value_spans[child_path] = (key_start, i)
                i = self._skip_ws(i)
                if self.text[i] == "}":
                    self.value_spans[path] = (start, i + 1)
                    return i + 1
                if self.text[i] != ",":
                    raise ValueError("expected comma")
                i += 1
        if ch == "[":
            i += 1
            idx = 0
            i = self._skip_ws(i)
            if i < len(self.text) and self.text[i] == "]":
                self.value_spans[path] = (start, i + 1)
                return i + 1
            while True:
                i = self._parse_value(i, path + (str(idx),))
                idx += 1
                i = self._skip_ws(i)
                if self.text[i] == "]":
                    self.value_spans[path] = (start, i + 1)
                    return i + 1
                if self.text[i] != ",":
                    raise ValueError("expected comma")
                i += 1
        if ch == '"':
            _, end = self._parse_string(i)
            self.positions[path] = (start, end)
            self.value_spans[path] = (start, end)
            return end
        for literal in ("true", "false", "null"):
            if self.text.startswith(literal, i):
                end = i + len(literal)
                self.positions[path] = (start, end)
                self.value_spans[path] = (start, end)
                return end
        end = self._parse_number(i)
        self.positions[path] = (start, end)
        self.value_spans[path] = (start, end)
        return end

    def path_for_offset(self, offset: int) -> tuple[str, ...]:
        best: tuple[str, ...] = ()
        best_len = sys.maxsize
        for path, (start, end) in self.value_spans.items():
            if start <= offset <= end:
                span_len = end - start
                if span_len <= best_len:
                    best = path
                    best_len = span_len
        return best


class JsonDocumentType:
    type_id = "json"
    display_name = "JSON 文件"
    default_extension = ".json"
    file_dialog_patterns = ("*.json",)
    view_mode = "split"
    parse_on_change = True
    supports_format = True
    supports_compact = True
    empty_status = "请输入 JSON 内容"

    def matches_path(self, path: Path) -> bool:
        return path.suffix.lower() == ".json"

    def matches_content(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped or stripped[0] not in "{[":
            return False
        try:
            json.loads(stripped)
        except json.JSONDecodeError:
            return False
        return True

    def parse(self, text: str) -> ParseResult:
        if not text.strip():
            return ParseResult(None, EmptyPositionIndex(), self.empty_status, False)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            message = f"语法错误：第 {exc.lineno} 行，第 {exc.colno} 列，{exc.msg}"
            return ParseResult(None, EmptyPositionIndex(), message, True)
        return ParseResult(build_tree(data), JsonPositionIndex.build(text), "", False)

    def format_text(self, text: str) -> str:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)

    def compact_text(self, text: str) -> str:
        return json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))

    def copy_node(self, node: TreeNode) -> str:
        if node.parent is None:
            return json_value_text(node.value)
        if isinstance(node.parent.value, dict):
            return f"{json.dumps(node.label, ensure_ascii=False)}: {json.dumps(node.value, ensure_ascii=False, indent=2)}"
        if isinstance(node.parent.value, list):
            return f"{node.label}: {json.dumps(node.value, ensure_ascii=False, indent=2)}"
        return json_value_text(node.value)

    def copy_node_value(self, node: TreeNode) -> str:
        return json_value_text(node.value)

    def copy_node_path(self, node: TreeNode) -> str:
        if node.parent is None:
            return "Root"
        parts = ["Root"]
        cur: TreeNode | None = node
        chain: list[TreeNode] = []
        while cur and cur.parent:
            chain.append(cur)
            cur = cur.parent
        for item in reversed(chain):
            if isinstance(item.parent.value, list):
                parts[-1] += f"[{item.label}]"
            else:
                parts.append(item.label)
        return ".".join(parts)
