from __future__ import annotations

import re
from tkinter import font
import tkinter as tk

from ..config import clamp_font_size, default_tree_font_size
from ..platforms import is_macos
from ..theme import LIGHT
from .common import SlimScrollbar


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
ORDERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
UNORDERED_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
TASK_RE = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)$")
QUOTE_RE = re.compile(r"^>\s?(.*)$")
RULE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
INLINE_RE = re.compile(
    r"`[^`\n]+`"
    r"|\*\*(?=\S).+?(?<=\S)\*\*"
    r"|__(?=\S).+?(?<=\S)__"
    r"|(?<!\*)\*(?!\*)(?=\S).+?(?<=\S)\*(?!\*)"
    r"|(?<!_)_(?!_)(?=\S).+?(?<=\S)_(?!_)"
    r"|!?\[[^\]\n]+\]\([^) \n]+(?:\s+\"[^\"]*\")?\)"
)
LINK_PARTS_RE = re.compile(r"(!?)\[([^\]\n]+)\]\(([^) \n]+)(?:\s+\"[^\"]*\")?\)")


class MarkdownPreview(tk.Frame):
    def __init__(self, master, on_font_delta):
        super().__init__(master, bd=0, highlightthickness=0)
        self.palette = LIGHT
        self.on_font_delta = on_font_delta
        family = "Menlo" if is_macos() else "Consolas"
        ui_family = ".AppleSystemUIFont" if is_macos() else "Segoe UI"
        size = default_tree_font_size()
        self.body_font = font.Font(family=ui_family, size=size)
        self.bold_font = font.Font(family=ui_family, size=size, weight="bold")
        self.italic_font = font.Font(family=ui_family, size=size, slant="italic")
        self.code_font = font.Font(family=family, size=size)
        self.code_block_font = font.Font(family=family, size=size)
        self.heading_fonts = {
            1: font.Font(family=ui_family, size=size + 8, weight="bold"),
            2: font.Font(family=ui_family, size=size + 5, weight="bold"),
            3: font.Font(family=ui_family, size=size + 3, weight="bold"),
            4: font.Font(family=ui_family, size=size + 1, weight="bold"),
            5: font.Font(family=ui_family, size=size, weight="bold"),
            6: font.Font(family=ui_family, size=max(8, size - 1), weight="bold"),
        }
        self.text = tk.Text(
            self,
            wrap="word",
            bd=0,
            highlightthickness=0,
            cursor="arrow",
            font=self.body_font,
            padx=22,
            pady=18,
            state="disabled",
        )
        self.vbar = SlimScrollbar(self, "vertical", self.text.yview)
        self.text.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.text.configure(yscrollcommand=self.vbar.set)
        self.text.bind("<MouseWheel>", self._wheel)
        self.text.bind("<Control-MouseWheel>", self._font_wheel)
        self.set_palette(self.palette)

    def set_palette(self, palette: dict) -> None:
        self.palette = palette
        self.configure(bg=palette["panel"])
        self.text.configure(bg=palette["input"], fg=palette["text"], insertbackground=palette["text"])
        self.vbar.set_palette(palette)
        self._configure_tags()

    def set_font_size(self, size: int) -> None:
        size = clamp_font_size(size)
        self.body_font.configure(size=size)
        self.bold_font.configure(size=size)
        self.italic_font.configure(size=size)
        self.code_font.configure(size=size)
        self.code_block_font.configure(size=size)
        self.heading_fonts[1].configure(size=size + 8)
        self.heading_fonts[2].configure(size=size + 5)
        self.heading_fonts[3].configure(size=size + 3)
        self.heading_fonts[4].configure(size=size + 1)
        self.heading_fonts[5].configure(size=size)
        self.heading_fonts[6].configure(size=max(8, size - 1))
        self._configure_tags()

    def set_markdown(self, markdown: str) -> None:
        yview = self.text.yview()[0]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self._render(markdown)
        self.text.configure(state="disabled")
        self.text.yview_moveto(yview)

    def clear(self) -> None:
        self.set_markdown("")

    def _configure_tags(self) -> None:
        p = self.palette
        self.text.tag_configure("p", font=self.body_font, foreground=p["text"], spacing1=2, spacing3=8)
        self.text.tag_configure("muted", foreground=p["muted"])
        self.text.tag_configure("strong", font=self.bold_font, foreground=p["text"])
        self.text.tag_configure("em", font=self.italic_font, foreground=p["text"])
        self.text.tag_configure("inline_code", font=self.code_font, background=p["panel2"], foreground=p["syntax_string"])
        self.text.tag_configure("code_block", font=self.code_block_font, background=p["panel2"], foreground=p["text"], lmargin1=14, lmargin2=14, spacing1=8, spacing3=8)
        self.text.tag_configure("quote", foreground=p["muted"], lmargin1=18, lmargin2=18, spacing1=3, spacing3=8)
        self.text.tag_configure("list", lmargin1=20, lmargin2=38, spacing1=1, spacing3=4)
        self.text.tag_configure("task_done", foreground=p["muted"], overstrike=True)
        self.text.tag_configure("rule", foreground=p["border"], spacing1=5, spacing3=10)
        self.text.tag_configure("table", font=self.code_font, lmargin1=10, lmargin2=10, spacing1=1, spacing3=3)
        self.text.tag_configure("link", foreground=p["accent"], underline=True)
        for level, heading_font in self.heading_fonts.items():
            self.text.tag_configure(f"h{level}", font=heading_font, foreground=p["text"], spacing1=8, spacing3=8)

    def _render(self, markdown: str) -> None:
        lines = markdown.splitlines()
        in_code = False
        fence = ""
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                if not in_code:
                    in_code = True
                    fence = marker
                    language = stripped[3:].strip()
                    if language:
                        self._insert_text(language + "\n", ("muted", "code_block"))
                    i += 1
                    continue
                if marker == fence:
                    in_code = False
                    fence = ""
                    self._ensure_trailing_newline()
                    i += 1
                    continue
            if in_code:
                self._insert_text(line + "\n", ("code_block",))
                i += 1
                continue
            if not line.strip():
                self._insert_text("\n", ("p",))
                i += 1
                continue
            if self._render_table(lines, i):
                i = self._next_after_table(lines, i)
                continue
            heading = HEADING_RE.match(line)
            if heading:
                level = min(6, len(heading.group(1)))
                self._insert_inline(heading.group(2), (f"h{level}",))
                self._insert_text("\n", (f"h{level}",))
                i += 1
                continue
            if RULE_RE.match(line):
                self._insert_text("-" * 36 + "\n", ("rule",))
                i += 1
                continue
            task = TASK_RE.match(line)
            if task:
                done = task.group(2).lower() == "x"
                prefix = "☑ " if done else "☐ "
                self._insert_text(prefix, ("list", "muted"))
                tags = ("list", "task_done") if done else ("list",)
                self._insert_inline(task.group(3), tags)
                self._insert_text("\n", tags)
                i += 1
                continue
            unordered = UNORDERED_RE.match(line)
            if unordered:
                self._insert_text("• ", ("list", "muted"))
                self._insert_inline(unordered.group(2), ("list",))
                self._insert_text("\n", ("list",))
                i += 1
                continue
            ordered = ORDERED_RE.match(line)
            if ordered:
                self._insert_text(f"{ordered.group(2)}. ", ("list", "muted"))
                self._insert_inline(ordered.group(3), ("list",))
                self._insert_text("\n", ("list",))
                i += 1
                continue
            quote = QUOTE_RE.match(line)
            if quote:
                self._insert_inline(quote.group(1), ("quote",))
                self._insert_text("\n", ("quote",))
                i += 1
                continue
            self._insert_inline(line.strip(), ("p",))
            self._insert_text("\n", ("p",))
            i += 1

    def _render_table(self, lines: list[str], index: int) -> bool:
        if index + 1 >= len(lines) or "|" not in lines[index]:
            return False
        if not TABLE_SEPARATOR_RE.match(lines[index + 1]):
            return False
        end = self._next_after_table(lines, index)
        rows = [self._table_cells(line) for line in lines[index:end] if not TABLE_SEPARATOR_RE.match(line)]
        if not rows:
            return False
        widths = [0] * max(len(row) for row in rows)
        for row in rows:
            for idx, cell in enumerate(row):
                widths[idx] = max(widths[idx], len(cell))
        for row_index, row in enumerate(rows):
            rendered = "  ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)).rstrip()
            tags = ("table", "strong") if row_index == 0 else ("table",)
            self._insert_text(rendered + "\n", tags)
        self._insert_text("\n", ("p",))
        return True

    def _next_after_table(self, lines: list[str], index: int) -> int:
        end = index + 1
        while end < len(lines) and "|" in lines[end] and lines[end].strip():
            end += 1
        return end

    def _table_cells(self, line: str) -> list[str]:
        stripped = line.strip().strip("|")
        return [cell.strip() for cell in stripped.split("|")]

    def _insert_inline(self, text: str, base_tags: tuple[str, ...]) -> None:
        pos = 0
        for match in INLINE_RE.finditer(text):
            if match.start() > pos:
                self._insert_text(text[pos : match.start()], base_tags)
            token = match.group(0)
            if token.startswith("`"):
                self._insert_text(token[1:-1], base_tags + ("inline_code",))
            elif token.startswith(("**", "__")):
                self._insert_text(token[2:-2], base_tags + ("strong",))
            elif token.startswith(("*", "_")):
                self._insert_text(token[1:-1], base_tags + ("em",))
            elif token.startswith("!"):
                link = LINK_PARTS_RE.match(token)
                label = link.group(2) if link else token
                target = link.group(3) if link else ""
                self._insert_text(f"图片：{label}", base_tags + ("strong",))
                if target:
                    self._insert_text(f" ({target})", base_tags + ("muted",))
            else:
                link = LINK_PARTS_RE.match(token)
                label = link.group(2) if link else token
                target = link.group(3) if link else ""
                self._insert_text(label, base_tags + ("link",))
                if target:
                    self._insert_text(f" ({target})", base_tags + ("muted",))
            pos = match.end()
        if pos < len(text):
            self._insert_text(text[pos:], base_tags)

    def _insert_text(self, text: str, tags: tuple[str, ...]) -> None:
        self.text.insert("end", text, tags)

    def _ensure_trailing_newline(self) -> None:
        if self.text.index("end-1c") != "1.0":
            last = self.text.get("end-2c", "end-1c")
            if last != "\n":
                self._insert_text("\n", ("p",))

    def _wheel(self, event):
        units = -1 if event.delta > 0 else 1
        self.text.yview_scroll(units, "units")
        return "break"

    def _font_wheel(self, event):
        self.on_font_delta(1 if event.delta > 0 else -1)
        return "break"
