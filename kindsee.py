#!/usr/bin/env python3
from __future__ import annotations

from kindsee_app import KindSeeApp
from kindsee_app.documents import TreeNode
from kindsee_app.documents.json_document import JsonDocumentType, JsonPositionIndex, build_tree, display_scalar, json_value_text


def main() -> None:
    app = KindSeeApp()
    app.run()


if __name__ == "__main__":
    main()
