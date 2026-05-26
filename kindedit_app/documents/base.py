from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class TreeNode:
    label: str
    value: object
    depth: int
    parent: "TreeNode | None"
    path: tuple[str, ...]
    kind: str
    expanded: bool = False
    children: list["TreeNode"] = field(default_factory=list)
    can_expand_item: bool = False
    can_collapse_item: bool = False
    display_text: str = ""

    @property
    def has_children(self) -> bool:
        return bool(self.children)


@dataclass
class ParseResult:
    tree: TreeNode | None
    position_index: "PositionIndex"
    status: str = ""
    error: bool = False


class PositionIndex(Protocol):
    positions: dict[tuple[str, ...], tuple[int, int]]
    cursor_positions: dict[tuple[str, ...], int]

    def path_for_offset(self, offset: int) -> tuple[str, ...]:
        ...


class EmptyPositionIndex:
    positions: dict[tuple[str, ...], tuple[int, int]] = {}
    cursor_positions: dict[tuple[str, ...], int] = {}

    def path_for_offset(self, offset: int) -> tuple[str, ...]:
        return ()


class DocumentType(Protocol):
    type_id: str
    display_name: str
    default_extension: str
    file_dialog_patterns: tuple[str, ...]
    view_mode: str
    parse_on_change: bool
    supports_format: bool
    supports_compact: bool
    empty_status: str

    def matches_path(self, path: Path) -> bool:
        ...

    def content_score(self, text: str) -> int:
        ...

    def parse(self, text: str) -> ParseResult:
        ...

    def format_text(self, text: str) -> str:
        ...

    def compact_text(self, text: str) -> str:
        ...

    def copy_node(self, node: TreeNode) -> str:
        ...

    def copy_node_value(self, node: TreeNode) -> str:
        ...

    def copy_node_path(self, node: TreeNode) -> str:
        ...


def refresh_tree_states(node: TreeNode) -> None:
    for child in node.children:
        refresh_tree_states(child)
    node.can_collapse_item = node.has_children and node.expanded
    node.can_expand_item = node.has_children and (not node.expanded or any(child.can_expand_item for child in node.children))


def refresh_to_root(node: TreeNode | None) -> None:
    while node is not None:
        node.can_collapse_item = node.has_children and node.expanded
        node.can_expand_item = node.has_children and (not node.expanded or any(child.can_expand_item for child in node.children))
        node = node.parent


def any_expandable(node: TreeNode | None) -> bool:
    return bool(node and node.can_expand_item)


def any_collapsible(node: TreeNode | None) -> bool:
    return bool(node and node.can_collapse_item)


class DocumentRegistry:
    def __init__(self) -> None:
        self._types: dict[str, DocumentType] = {}
        self._default_type_id = ""

    def register(self, doc_type: DocumentType, default: bool = False) -> None:
        self._types[doc_type.type_id] = doc_type
        if default or not self._default_type_id:
            self._default_type_id = doc_type.type_id

    def get(self, type_id: str | None) -> DocumentType:
        if type_id and type_id in self._types:
            return self._types[type_id]
        return self._types[self._default_type_id]

    def all_types(self) -> list[DocumentType]:
        return list(self._types.values())

    def detect(self, path: Path | None) -> DocumentType:
        if path is not None:
            for doc_type in self._types.values():
                if doc_type.matches_path(path):
                    return doc_type
        return self.get(None)

    def detect_content(self, text: str, fallback_type_id: str = "text") -> DocumentType:
        best_type: DocumentType | None = None
        best_score = 0
        for doc_type in self._types.values():
            scorer = getattr(doc_type, "content_score", None)
            if callable(scorer):
                score = scorer(text)
                if score > best_score:
                    best_type = doc_type
                    best_score = score
                continue
            matcher = getattr(doc_type, "matches_content", None)
            if callable(matcher) and matcher(text) and best_score < 50:
                best_type = doc_type
                best_score = 50
        if best_type is not None:
            return best_type
        return self.get(fallback_type_id)

    def filetypes(self) -> list[tuple[str, str]]:
        filetypes = []
        for doc_type in self._types.values():
            pattern = " ".join(doc_type.file_dialog_patterns)
            filetypes.append((f"{doc_type.display_name} ({pattern})", pattern))
        filetypes.append(("所有文件", "*.*"))
        return filetypes

    def text_filetypes(self) -> list[tuple[str, str]]:
        patterns = []
        for doc_type in self._types.values():
            patterns.extend(doc_type.file_dialog_patterns)
        combined = " ".join(dict.fromkeys(patterns))
        return [("所有文本文件", combined), *self.filetypes()]

    def save_filetypes(self, current_type_id: str | None) -> list[tuple[str, str]]:
        current = self.get(current_type_id)
        current_pattern = " ".join(current.file_dialog_patterns)
        filetypes = [(f"{current.display_name} ({current_pattern})", current_pattern)]
        for doc_type in self._types.values():
            if doc_type.type_id == current.type_id:
                continue
            pattern = " ".join(doc_type.file_dialog_patterns)
            filetypes.append((f"{doc_type.display_name} ({pattern})", pattern))
        filetypes.append(("所有文件", "*.*"))
        return filetypes
