#!/usr/bin/env python3
from __future__ import annotations

from kindedit_app import KindEditApp
from kindedit_app.documents import TreeNode
from kindedit_app.documents.json_document import JsonDocumentType, JsonPositionIndex, build_tree, display_scalar, json_value_text


def main() -> None:
    app = KindEditApp()
    app.run()


if __name__ == "__main__":
    main()
