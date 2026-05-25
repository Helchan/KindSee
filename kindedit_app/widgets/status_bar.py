from __future__ import annotations

from tkinter import font
import tkinter as tk

from ..theme import LIGHT


class StatusBar(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, height=21, highlightthickness=0, bd=0)
        self.app = app
        self.palette = LIGHT
        self.status_text = ""
        self.status_error = False
        self.font = font.Font(size=8)
        self.bind("<Configure>", lambda _e: self.draw())

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
