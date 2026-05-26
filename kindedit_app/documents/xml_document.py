from __future__ import annotations

from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

from .base import EmptyPositionIndex, ParseResult, TreeNode, refresh_tree_states


def _short_text(text: str, limit: int = 80) -> str:
    value = " ".join(text.split())
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _strip_added_declaration(source: str, rendered: str) -> str:
    if source.lstrip().startswith("<?xml"):
        return rendered
    stripped = rendered.lstrip()
    if stripped.startswith("<?xml"):
        declaration_end = stripped.find("?>")
        if declaration_end >= 0:
            return stripped[declaration_end + 2 :].lstrip()
    lines = rendered.splitlines()
    if lines and lines[0].lstrip().startswith("<?xml"):
        return "\n".join(lines[1:])
    return rendered


def _remove_blank_text_nodes(node) -> None:
    for child in list(node.childNodes):
        if child.nodeType == child.TEXT_NODE and not child.data.strip():
            node.removeChild(child)
            child.unlink()
        else:
            _remove_blank_text_nodes(child)


def _format_xml_text(text: str) -> str:
    document = minidom.parseString(text)
    rendered = document.toprettyxml(indent="  ")
    lines = [line for line in rendered.splitlines() if line.strip()]
    return _strip_added_declaration(text, "\n".join(lines))


def _compact_xml_text(text: str) -> str:
    document = minidom.parseString(text)
    _remove_blank_text_nodes(document)
    return _strip_added_declaration(text, document.toxml())


def _serialize_element(element: ET.Element, pretty: bool = True) -> str:
    raw = ET.tostring(element, encoding="unicode", short_empty_elements=True)
    if not pretty:
        return raw
    return _format_xml_text(raw)


def _display_element(node: TreeNode, is_root: bool = False) -> str:
    element = node.value
    if not isinstance(element, ET.Element):
        return f"{node.label}: {element}"
    element_children = sum(1 for child in element if isinstance(child.tag, str))
    scalar_children = len(element.attrib) + (1 if element.text and element.text.strip() else 0)
    count = element_children + scalar_children
    prefix = f"Root <{element.tag}>" if is_root else f"{node.label}: <{element.tag}>"
    return f"{prefix} {{{count}}}" if count else prefix


def build_tree(element: ET.Element) -> TreeNode:
    root = TreeNode("Root", element, 0, None, (), "object", expanded=True)
    root.display_text = _display_element(root, True)

    def add_children(parent: TreeNode) -> None:
        value = parent.value
        if not isinstance(value, ET.Element):
            return
        for attr_name, attr_value in value.attrib.items():
            child = TreeNode(
                label=f"@{attr_name}",
                value=attr_value,
                depth=parent.depth + 1,
                parent=parent,
                path=parent.path + (f"@{attr_name}",),
                kind="field",
                expanded=False,
            )
            child.display_text = f"@{attr_name}: {attr_value}"
            parent.children.append(child)
        if value.text and value.text.strip():
            text_value = _short_text(value.text)
            child = TreeNode(
                label="#text",
                value=value.text.strip(),
                depth=parent.depth + 1,
                parent=parent,
                path=parent.path + ("#text",),
                kind="field",
                expanded=False,
            )
            child.display_text = f"#text: {text_value}"
            parent.children.append(child)
        seen: dict[str, int] = {}
        for child_element in value:
            if not isinstance(child_element.tag, str):
                continue
            seen[child_element.tag] = seen.get(child_element.tag, 0) + 1
            label = child_element.tag if seen[child_element.tag] == 1 else f"{child_element.tag}[{seen[child_element.tag]}]"
            child = TreeNode(
                label=label,
                value=child_element,
                depth=parent.depth + 1,
                parent=parent,
                path=parent.path + (label,),
                kind="object",
                expanded=False,
            )
            child.display_text = _display_element(child)
            parent.children.append(child)
            add_children(child)

    add_children(root)
    refresh_tree_states(root)
    return root


class XmlDocumentType:
    type_id = "xml"
    display_name = "XML 文件"
    default_extension = ".xml"
    file_dialog_patterns = ("*.xml",)
    view_mode = "split"
    parse_on_change = True
    supports_format = True
    supports_compact = True
    empty_status = "请输入 XML 内容"

    def matches_path(self, path: Path) -> bool:
        return path.suffix.lower() == ".xml"

    def matches_content(self, text: str) -> bool:
        return self.content_score(text) > 0

    def content_score(self, text: str) -> int:
        stripped = text.strip()
        if not stripped or not stripped.startswith("<"):
            return 0
        try:
            ET.fromstring(stripped)
        except ET.ParseError:
            return 0
        return 100

    def parse(self, text: str) -> ParseResult:
        if not text.strip():
            return ParseResult(None, EmptyPositionIndex(), self.empty_status, False)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            line, column = getattr(exc, "position", (1, 0))
            return ParseResult(None, EmptyPositionIndex(), f"语法错误：第 {line} 行，第 {column + 1} 列，{exc}", True)
        return ParseResult(build_tree(root), EmptyPositionIndex(), "", False)

    def format_text(self, text: str) -> str:
        return _format_xml_text(text)

    def compact_text(self, text: str) -> str:
        return _compact_xml_text(text)

    def copy_node(self, node: TreeNode) -> str:
        if isinstance(node.value, ET.Element):
            return _serialize_element(node.value, pretty=True)
        return f"{node.label}: {node.value}"

    def copy_node_value(self, node: TreeNode) -> str:
        if isinstance(node.value, ET.Element):
            return _serialize_element(node.value, pretty=True)
        return str(node.value)

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
            parts.append(item.label)
        return ".".join(parts)
