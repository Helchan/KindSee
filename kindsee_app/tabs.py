from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TabState:
    id: str
    title: str
    file_path: str = ""
    autosave_path: str = ""
    dirty: bool = False
    content: str = ""
    document_type: str = "text"
    document_type_locked: bool = False
