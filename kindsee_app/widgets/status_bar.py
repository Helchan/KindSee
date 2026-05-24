from __future__ import annotations

import webbrowser
from tkinter import font
import tkinter as tk

from ..constants import APP_VERSION_TEXT, BRAND_TEXT, LATEST_VERSION_TEXT, LATEST_VERSION_URL
from ..theme import LIGHT


class StatusBar(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, height=28, highlightthickness=0, bd=0)
        self.app = app
        self.palette = LIGHT
        self.status_text = ""
        self.status_error = False
        self.hotspots: list[tuple[int, int, str]] = []
        self.font = font.Font(size=10)
        self.link_font = font.Font(size=10, underline=True)
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Motion>", self._motion)
        self.bind("<Button-1>", self._click)

    def set_palette(self, palette: dict) -> None:
        self.palette = palette
        self.configure(bg=palette["panel2"])
        self.draw()

    def set_status(self, text: str, error: bool = False) -> None:
        self.status_text = text
        self.status_error = error
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        self.create_rectangle(0, 0, w, h, fill=self.palette["panel2"], width=0)
        text_y = max(1, (h - self.font.metrics("linespace")) // 2)
        left_color = self.palette["error"] if self.status_error else self.palette["muted"]
        self.create_text(10, text_y, text=self.status_text, anchor="nw", fill=left_color, font=self.font)
        items = [
            (APP_VERSION_TEXT + " | ", "", self.palette["muted"], self.font),
            (LATEST_VERSION_TEXT, "latest", self.palette["accent"], self.link_font),
            (" | " + BRAND_TEXT, "", self.palette["muted"], self.font),
        ]
        x = w - 8
        measured = []
        for text, key, color, fnt in reversed(items):
            measured.append((text, key, color, fnt, fnt.measure(text)))
        self.hotspots = []
        for text, key, color, fnt, width in measured:
            x -= width
            item_y = max(1, (h - fnt.metrics("linespace")) // 2)
            self.create_text(x, item_y, text=text, anchor="nw", fill=color, font=fnt)
            if key:
                self.hotspots.append((x, x + width, key))
            x -= 10 if key in {"sync", "reset"} else 0

    def _motion(self, event) -> None:
        key = self._hotspot(event.x)
        self.configure(cursor="hand2" if key else "")

    def _hotspot(self, x: int) -> str | None:
        for x1, x2, key in self.hotspots:
            if x1 <= x <= x2:
                return key
        return None

    def _click(self, event) -> None:
        key = self._hotspot(event.x)
        if key == "latest":
            webbrowser.open(LATEST_VERSION_URL)
