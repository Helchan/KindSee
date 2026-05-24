from .base import (
    DocumentRegistry,
    DocumentType,
    EmptyPositionIndex,
    ParseResult,
    TreeNode,
    any_collapsible,
    any_expandable,
    refresh_to_root,
    refresh_tree_states,
)
from .java_document import JavaDocumentType
from .javascript_document import JavaScriptDocumentType
from .json_document import JsonDocumentType
from .log_document import LogDocumentType
from .markdown_document import MarkdownDocumentType
from .python_document import PythonDocumentType
from .sql_document import SqlDocumentType
from .text_document import TextDocumentType
from .xml_document import XmlDocumentType


def default_registry() -> DocumentRegistry:
    registry = DocumentRegistry()
    registry.register(JsonDocumentType(), default=True)
    registry.register(TextDocumentType())
    registry.register(LogDocumentType())
    registry.register(XmlDocumentType())
    registry.register(MarkdownDocumentType())
    registry.register(JavaDocumentType())
    registry.register(PythonDocumentType())
    registry.register(JavaScriptDocumentType())
    registry.register(SqlDocumentType())
    return registry


__all__ = [
    "DocumentRegistry",
    "DocumentType",
    "EmptyPositionIndex",
    "JavaDocumentType",
    "JavaScriptDocumentType",
    "JsonDocumentType",
    "LogDocumentType",
    "MarkdownDocumentType",
    "ParseResult",
    "PythonDocumentType",
    "SqlDocumentType",
    "TextDocumentType",
    "TreeNode",
    "XmlDocumentType",
    "any_collapsible",
    "any_expandable",
    "default_registry",
    "refresh_to_root",
    "refresh_tree_states",
]
