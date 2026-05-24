from .base import NoopHighlighter, SyntaxHighlighter, SyntaxRegistry, SyntaxToken
from .java_highlighter import JavaSyntaxHighlighter
from .javascript_highlighter import JavaScriptSyntaxHighlighter
from .json_highlighter import JsonSyntaxHighlighter
from .python_highlighter import PythonSyntaxHighlighter
from .xml_highlighter import XmlSyntaxHighlighter


def default_syntax_registry() -> SyntaxRegistry:
    registry = SyntaxRegistry()
    registry.register(JsonSyntaxHighlighter())
    registry.register(XmlSyntaxHighlighter())
    registry.register(JavaSyntaxHighlighter())
    registry.register(PythonSyntaxHighlighter())
    registry.register(JavaScriptSyntaxHighlighter())
    registry.register(NoopHighlighter())
    return registry


__all__ = [
    "JsonSyntaxHighlighter",
    "JavaSyntaxHighlighter",
    "JavaScriptSyntaxHighlighter",
    "NoopHighlighter",
    "PythonSyntaxHighlighter",
    "SyntaxHighlighter",
    "SyntaxRegistry",
    "SyntaxToken",
    "XmlSyntaxHighlighter",
    "default_syntax_registry",
]
