from __future__ import annotations

import time
from pathlib import Path
from typing import Callable
from tkinter import font
import tkinter as tk

from ..config import clamp_font_size, default_text_font_size
from ..large_text import LARGE_TEXT_CHUNK_CHARS, LARGE_TEXT_TIME_BUDGET_MS, is_large_text_size
from ..platforms import is_macos, text_edit_cursor_name
from ..syntax import SyntaxToken
from ..theme import LIGHT

MAX_OCCURRENCE_HIGHLIGHT_CHARS = 500_000
MAX_OCCURRENCE_TEXT_LENGTH = 200
MAX_OCCURRENCE_MATCHES = 2_000
MAX_VISIBLE_OCCURRENCE_MATCHES = 300
MAX_OCCURRENCE_QUERIES = 6
CURSOR_REFRESH_FALLBACK = "arrow"
CONTROL_MASK = 0x0004
ALT_MASK = 0x0008
OPTION_ALT_MASKS = (0x0008, 0x0010, 0x0020, 0x0040, 0x0080)
MAC_COMMAND_MASKS = (0x0008, 0x0010)
OCCURRENCE_MODIFIER_KEYSYMS = {
    "Control_L",
    "Control_R",
    "Command",
    "Command_L",
    "Command_R",
    "Meta_L",
    "Meta_R",
    "Super_L",
    "Super_R",
}
WHEEL_SCROLL_UNITS = 6
MACOS_COLUMN_EDIT_START_EVENTS = ("<Option-Button-1>", "<Alt-Button-1>", "<Mod1-Button-1>", "<Mod2-Button-1>")
DEFAULT_COLUMN_EDIT_START_EVENTS = ("<Alt-Button-1>",)


def column_edit_start_events(mac: bool) -> tuple[str, ...]:
    return MACOS_COLUMN_EDIT_START_EVENTS if mac else DEFAULT_COLUMN_EDIT_START_EVENTS


class SlimScrollbar(tk.Canvas):
    def __init__(self, master, orient: str, command, **kwargs):
        super().__init__(master, highlightthickness=0, bd=0, **kwargs)
        self.orient = orient
        self.command = command
        self.first = 0.0
        self.last = 1.0
        self.palette = LIGHT
        self.dragging = False
        self.drag_offset = 0
        self.configure(width=8 if orient == "vertical" else 1, height=8 if orient == "horizontal" else 1)
        self.bind("<Button-1>", self._click)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda _e: setattr(self, "dragging", False))
        self.bind("<Configure>", lambda _e: self._draw())

    def set_palette(self, palette: dict) -> None:
        self.palette = palette
        self.configure(bg=palette["panel"])
        self._draw()

    def set(self, first, last) -> None:
        self.first = max(0.0, min(1.0, float(first)))
        self.last = max(0.0, min(1.0, float(last)))
        self._draw()

    def _thumb(self) -> tuple[int, int, int, int] | None:
        if self.last - self.first >= 0.999:
            return None
        w, h = max(1, self.winfo_width()), max(1, self.winfo_height())
        if self.orient == "vertical":
            size = max(24, int(h * (self.last - self.first)))
            top = int((h - size) * self.first / max(0.0001, 1 - (self.last - self.first)))
            return 1, top, w - 1, top + size
        size = max(24, int(w * (self.last - self.first)))
        left = int((w - size) * self.first / max(0.0001, 1 - (self.last - self.first)))
        return left, 1, left + size, h - 1

    def _draw(self) -> None:
        self.delete("all")
        self.create_rectangle(0, 0, self.winfo_width(), self.winfo_height(), fill=self.palette["scroll_track"], width=0)
        thumb = self._thumb()
        if thumb:
            self.create_rectangle(*thumb, fill=self.palette["scroll"], width=0)

    def _click(self, event) -> None:
        thumb = self._thumb()
        if not thumb:
            return
        x1, y1, x2, y2 = thumb
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            self.dragging = True
            self.drag_offset = event.y - y1 if self.orient == "vertical" else event.x - x1
            return
        size = y2 - y1 if self.orient == "vertical" else x2 - x1
        total = self.winfo_height() if self.orient == "vertical" else self.winfo_width()
        pos = event.y if self.orient == "vertical" else event.x
        frac = (pos - size / 2) / max(1, total - size)
        self.command("moveto", max(0.0, min(1.0, frac)))

    def _drag(self, event) -> None:
        if not self.dragging:
            return
        thumb = self._thumb()
        if not thumb:
            return
        x1, y1, x2, y2 = thumb
        size = y2 - y1 if self.orient == "vertical" else x2 - x1
        total = self.winfo_height() if self.orient == "vertical" else self.winfo_width()
        pos = (event.y if self.orient == "vertical" else event.x) - self.drag_offset
        frac = pos / max(1, total - size)
        self.command("moveto", max(0.0, min(1.0, frac)))


class FastContextMenu:
    active_menu: "FastContextMenu | None" = None

    def __init__(self, master, items: list[tuple], palette: dict, font_obj):
        if FastContextMenu.active_menu is not None:
            FastContextMenu.active_menu.destroy()
        self.master = master
        self.palette = palette
        self.font = font_obj
        self.variables: list[tk.BooleanVar] = []
        self.menu = tk.Menu(master, tearoff=False)
        self._configure_menu(self.menu)
        self._build_menu(self.menu, items)
        self._bind_disabled_hover_guard(self.menu)
        FastContextMenu.active_menu = self

    def popup(self, x: int, y: int) -> None:
        try:
            self.menu.tk_popup(x, y)
        finally:
            try:
                self.menu.grab_release()
            except tk.TclError:
                pass

    def destroy(self) -> None:
        try:
            self.menu.unpost()
            self.menu.destroy()
        except tk.TclError:
            pass
        if FastContextMenu.active_menu is self:
            FastContextMenu.active_menu = None

    def _configure_menu(self, menu: tk.Menu) -> None:
        try:
            menu.configure(
                bg=self.palette["panel"],
                fg=self.palette["text"],
                activebackground=self.palette["hover"],
                activeforeground=self.palette["text"],
                disabledforeground=self.palette["muted"],
                borderwidth=1,
                relief="solid",
                font=self.font,
            )
            menu.configure(disabledforeground=self.palette.get("disabled", self.palette["muted"]))
        except tk.TclError:
            pass

    def _build_menu(self, menu: tk.Menu, items: list[tuple]) -> None:
        for item in items:
            label = item[0]
            if label == "-":
                menu.add_separator()
                continue
            enabled = bool(item[2])
            state = "normal" if enabled else "disabled"
            if self._is_submenu(item):
                submenu = tk.Menu(menu, tearoff=False)
                self._configure_menu(submenu)
                self._build_menu(submenu, item[1])
                self._bind_disabled_hover_guard(submenu)
                menu.add_cascade(label=self._clean_label(label), menu=submenu, state=state)
                continue
            _check, text = self._split_check_label(label)
            if self._uses_check_column(label):
                variable = tk.BooleanVar(master=self.master, value=bool(_check))
                self.variables.append(variable)
                menu.add_checkbutton(label=text, variable=variable, command=item[1], state=state)
            else:
                menu.add_command(label=text, command=item[1], state=state)

    def _bind_disabled_hover_guard(self, menu: tk.Menu) -> None:
        menu.bind("<Motion>", lambda event, target=menu: self._clear_disabled_active(target, event), add="+")

    def _clear_disabled_active(self, menu: tk.Menu, event) -> None:
        try:
            index = menu.index(f"@{event.x},{event.y}")
            if index is None:
                return
            if str(menu.entrycget(index, "state")) == "disabled":
                menu.activate("none")
        except tk.TclError:
            pass

    def _is_submenu(self, item: tuple) -> bool:
        return len(item) >= 4 and item[3] == "submenu"

    def _split_check_label(self, label: str) -> tuple[str, str]:
        if label.startswith("✓ "):
            return "✓", label[2:]
        return "", label

    def _clean_label(self, label: str) -> str:
        _check, text = self._split_check_label(label)
        return text

    def _uses_check_column(self, label: str) -> bool:
        _check, text = self._split_check_label(label)
        return text == "同步" or text.startswith(".")

class LineNumberText(tk.Frame):
    def __init__(self, master, on_change, on_cursor, on_font_delta):
        super().__init__(master, bd=0, highlightthickness=0)
        self.on_change = on_change
        self.on_cursor = on_cursor
        self.on_font_delta = on_font_delta
        self.palette = LIGHT
        self.occurrence_job = None
        self.occurrence_queries: list[str] = []
        self.occurrence_add_query = False
        self.keep_occurrence_query = False
        self.pending_occurrence_selection: str | None = None
        self.occurrence_ignore_case = False
        self.occurrence_modifier_down = False
        self.cursor_refresh_job = None
        self.cursor_refresh_needed = True
        self.bulk_job = None
        self.bulk_cancel_token = 0
        self.bulk_cleanup: Callable[[], None] | None = None
        self.large_content_mode = False
        self.column_edit_anchor: str | None = None
        self.column_edit_active = False
        self.column_edit_lines: list[int] = []
        self.column_edit_column = 0
        self.column_edit_range_end_column = 0
        self.column_caret_widgets: list[tk.Frame] = []
        self.occurrence_tag_names = tuple(["occurrence_highlight"] + [f"occurrence_highlight_{i}" for i in range(1, MAX_OCCURRENCE_QUERIES)])
        self.syntax_tag_names = ("syntax_key", "syntax_string", "syntax_number", "syntax_literal", "syntax_punctuation")
        self.text_cursor = text_edit_cursor_name()
        family = "Menlo" if is_macos() else "Consolas"
        self.text_font = font.Font(family=family, size=default_text_font_size())
        self.line_font = font.Font(family=family, size=default_text_font_size())
        self.line_canvas = tk.Canvas(self, width=34, highlightthickness=0, bd=0)
        self.scroll_corner = tk.Frame(self, bd=0, highlightthickness=0)
        self.text = tk.Text(
            self,
            wrap="none",
            undo=True,
            autoseparators=True,
            maxundo=-1,
            bd=0,
            highlightthickness=0,
            insertwidth=2,
            cursor=self.text_cursor,
            font=self.text_font,
        )
        self.text.tag_configure("sync_highlight", background=self.palette["select"])
        self.text.tag_configure("column_selection", background=self.palette["occurrence"])
        self._configure_occurrence_tags()
        self.vbar = SlimScrollbar(self, "vertical", self.text.yview)
        self.hbar = SlimScrollbar(self, "horizontal", self.text.xview)
        self.line_canvas.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.vbar.grid(row=0, column=2, sticky="ns")
        self.scroll_corner.grid(row=1, column=0, sticky="nsew")
        self.hbar.grid(row=1, column=1, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.text.configure(yscrollcommand=self._yscroll, xscrollcommand=self._xscroll)
        self.text.bind("<<Modified>>", self._modified)
        self.text.bind("<KeyRelease>", self._key_release)
        self.text.bind("<ButtonRelease-1>", self._button_release)
        self.text.bind("<Button-1>", self._button_press, add="+")
        self._bind_column_edit_start_events()
        self.text.bind("<B1-Motion>", self._column_edit_motion, add="+")
        self.text.bind("<ButtonRelease-1>", self._column_edit_release, add="+")
        self.text.bind("<KeyPress>", self._column_edit_key, add="+")
        self.text.bind("<Double-ButtonRelease-1>", self._button_release)
        self.text.bind("<Control-ButtonRelease-1>", self._button_release)
        self.text.bind("<Control-Double-ButtonRelease-1>", self._button_release)
        self.text.bind("<Control-KeyPress>", self._modifier_key_press, add="+")
        self.text.bind("<Control-KeyRelease>", self._modifier_key_release, add="+")
        self.text.bind("<KeyPress-Control_L>", self._modifier_key_press, add="+")
        self.text.bind("<KeyPress-Control_R>", self._modifier_key_press, add="+")
        self.text.bind("<KeyRelease-Control_L>", self._modifier_key_release, add="+")
        self.text.bind("<KeyRelease-Control_R>", self._modifier_key_release, add="+")
        self.text.bind("<Enter>", self._refresh_cursor_if_needed)
        self.text.bind("<Motion>", self._refresh_cursor_if_needed)
        self.text.bind("<Configure>", lambda _e: self._draw_lines())
        self.text.bind("<MouseWheel>", self._wheel)
        self.line_canvas.bind("<MouseWheel>", self._wheel)
        self.text.bind("<Control-MouseWheel>", self._font_wheel)
        self.line_canvas.bind("<Control-MouseWheel>", self._font_wheel)

    def set_palette(self, palette: dict) -> None:
        self.palette = palette
        self.configure(bg=palette["panel"])
        self.line_canvas.configure(bg=palette["panel2"])
        self.scroll_corner.configure(bg=palette["scroll_track"])
        self.text.configure(
            bg=palette["input"],
            fg=palette["text"],
            insertbackground=palette["text"],
            selectbackground=palette["select"],
            selectforeground=palette["text"],
        )
        self.text.tag_configure("sync_highlight", background=palette["select"])
        self.text.tag_configure("column_selection", background=palette["select"])
        self._configure_occurrence_tags()
        self._configure_syntax_tags()
        self.restore_text_cursor()
        self.vbar.set_palette(palette)
        self.hbar.set_palette(palette)
        self._draw_lines()

    def set_font_size(self, size: int) -> None:
        size = clamp_font_size(size)
        self.text_font.configure(size=size)
        self.line_font.configure(size=size)
        self._update_line_width()
        self._draw_lines()

    def set_occurrence_ignore_case(self, enabled: bool) -> None:
        self.occurrence_ignore_case = bool(enabled)
        if self.occurrence_queries:
            self.schedule_occurrence_highlight(0, keep_query=True)

    def get(self) -> str:
        return self.text.get("1.0", "end-1c")

    def char_count(self) -> int:
        counted = self.text.count("1.0", "end-1c", "chars")
        return int(counted[0]) if counted else 0

    def content_is_large(self) -> bool:
        return self.large_content_mode or is_large_text_size(self.char_count())

    def sample_text(self, limit: int) -> str:
        if limit <= 0:
            return ""
        return self.text.get("1.0", f"1.0+{limit}c")

    def selection_char_count(self) -> int:
        try:
            counted = self.text.count("sel.first", "sel.last", "chars")
            return int(counted[0]) if counted else 0
        except tk.TclError:
            return 0

    def is_blank_for_detection(self, scan_limit: int = 4096) -> bool:
        if self.is_empty():
            return True
        if self.content_is_large():
            return False
        return not self.sample_text(scan_limit).strip() and self.char_count() <= scan_limit

    def is_empty(self) -> bool:
        return self.text.index("end-1c") == "1.0"

    def set(self, content: str) -> None:
        self.cancel_bulk_operation()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if content:
            self.text.insert("1.0", content)
        self.large_content_mode = is_large_text_size(len(content))
        self.text.edit_modified(False)
        self.occurrence_queries = []
        self.clear_occurrence_highlight()
        self._update_line_width()
        self._draw_lines()

    def replace_all(self, content: str) -> None:
        self.cancel_bulk_operation()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.large_content_mode = is_large_text_size(len(content))
        self.text.edit_modified(True)
        self.on_change()
        self._update_line_width()
        self._draw_lines()

    def cancel_bulk_operation(self) -> None:
        self.bulk_cancel_token += 1
        if self.bulk_job:
            try:
                self.after_cancel(self.bulk_job)
            except tk.TclError:
                pass
            self.bulk_job = None
        cleanup = self.bulk_cleanup
        self.bulk_cleanup = None
        if cleanup:
            cleanup()

    def _begin_bulk_operation(self) -> int:
        self.cancel_bulk_operation()
        self.bulk_cancel_token += 1
        return self.bulk_cancel_token

    def load_file_chunked(
        self,
        path: Path,
        on_progress: Callable[[int], None] | None = None,
        on_complete: Callable[[int], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        token = self._begin_bulk_operation()
        old_undo = self.text.cget("undo")
        stream = path.open("r", encoding="utf-8", errors="replace", newline="")
        total_chars = 0

        def cleanup() -> None:
            try:
                stream.close()
            except Exception:
                pass

        self.bulk_cleanup = cleanup
        self.text.configure(state="normal", undo=False)
        self.text.delete("1.0", "end")
        self.large_content_mode = True
        self.occurrence_queries = []
        self.clear_occurrence_highlight()
        self.clear_syntax()

        def finish() -> None:
            self.bulk_job = None
            self.bulk_cleanup = None
            cleanup()
            self.text.configure(undo=old_undo)
            self.text.edit_modified(False)
            self._update_line_width()
            self._draw_lines()
            if on_complete:
                on_complete(total_chars)

        def fail(exc: Exception) -> None:
            self.bulk_job = None
            self.bulk_cleanup = None
            cleanup()
            self.text.configure(undo=old_undo)
            if on_error:
                on_error(exc)

        def step() -> None:
            nonlocal total_chars
            if token != self.bulk_cancel_token:
                return
            try:
                started = time.perf_counter()
                while (time.perf_counter() - started) * 1000 < LARGE_TEXT_TIME_BUDGET_MS:
                    chunk = stream.read(LARGE_TEXT_CHUNK_CHARS)
                    if not chunk:
                        finish()
                        return
                    self.text.insert("end-1c", chunk)
                    total_chars += len(chunk)
                    if on_progress:
                        on_progress(total_chars)
                self.text.edit_modified(False)
                self._update_line_width()
                self._draw_lines()
                self.bulk_job = self.after(1, step)
            except Exception as exc:
                fail(exc)

        self.bulk_job = self.after(1, step)

    def insert_text_chunked(
        self,
        content: str,
        replace_selection: bool = True,
        on_progress: Callable[[int, int], None] | None = None,
        on_complete: Callable[[int], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        token = self._begin_bulk_operation()
        old_undo = self.text.cget("undo")
        total = len(content)
        offset = 0
        self.text.configure(state="normal", undo=False)
        if replace_selection:
            try:
                self.text.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
        self.text.mark_set("_kindedit_bulk_insert", "insert")
        self.text.mark_gravity("_kindedit_bulk_insert", "right")
        self.large_content_mode = True

        def cleanup() -> None:
            try:
                self.text.mark_unset("_kindedit_bulk_insert")
            except tk.TclError:
                pass

        self.bulk_cleanup = cleanup

        def finish() -> None:
            self.bulk_job = None
            self.bulk_cleanup = None
            cleanup()
            self.text.configure(undo=old_undo)
            self.text.edit_modified(False)
            self._update_line_width()
            self._draw_lines()
            if on_complete:
                on_complete(total)

        def fail(exc: Exception) -> None:
            self.bulk_job = None
            self.bulk_cleanup = None
            cleanup()
            self.text.configure(undo=old_undo)
            if on_error:
                on_error(exc)

        def step() -> None:
            nonlocal offset
            if token != self.bulk_cancel_token:
                return
            try:
                started = time.perf_counter()
                while offset < total and (time.perf_counter() - started) * 1000 < LARGE_TEXT_TIME_BUDGET_MS:
                    next_offset = min(total, offset + LARGE_TEXT_CHUNK_CHARS)
                    self.text.insert("_kindedit_bulk_insert", content[offset:next_offset])
                    offset = next_offset
                    if on_progress:
                        on_progress(offset, total)
                self.text.edit_modified(False)
                self._update_line_width()
                self._draw_lines()
                if offset >= total:
                    finish()
                    return
                self.bulk_job = self.after(1, step)
            except Exception as exc:
                fail(exc)

        self.bulk_job = self.after(1, step)

    def save_to_path_chunked(
        self,
        path: Path,
        on_progress: Callable[[int, int], None] | None = None,
        on_complete: Callable[[int], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        token = self._begin_bulk_operation()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.kindedit.tmp")
        stream = tmp_path.open("w", encoding="utf-8", newline="")
        start_index = "1.0"
        end_index = self.text.index("end-1c")
        total_chars = self.char_count()
        written = 0

        def cleanup() -> None:
            try:
                stream.close()
            except Exception:
                pass
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

        self.bulk_cleanup = cleanup

        def finish() -> None:
            self.bulk_job = None
            self.bulk_cleanup = None
            try:
                stream.close()
                tmp_path.replace(path)
            except Exception as exc:
                fail(exc)
                return
            if on_complete:
                on_complete(total_chars)

        def fail(exc: Exception) -> None:
            self.bulk_job = None
            self.bulk_cleanup = None
            cleanup()
            if on_error:
                on_error(exc)

        def step() -> None:
            nonlocal start_index, written
            if token != self.bulk_cancel_token:
                return
            try:
                started = time.perf_counter()
                while self.text.compare(start_index, "<", end_index) and (time.perf_counter() - started) * 1000 < LARGE_TEXT_TIME_BUDGET_MS:
                    next_index = self.text.index(f"{start_index}+{LARGE_TEXT_CHUNK_CHARS}c")
                    if self.text.compare(next_index, ">", end_index):
                        next_index = end_index
                    chunk = self.text.get(start_index, next_index)
                    stream.write(chunk)
                    written += len(chunk)
                    start_index = next_index
                    if on_progress:
                        on_progress(written, total_chars)
                if not self.text.compare(start_index, "<", end_index):
                    finish()
                    return
                self.bulk_job = self.after(1, step)
            except Exception as exc:
                fail(exc)

        self.bulk_job = self.after(1, step)

    def _modified(self, _event=None) -> None:
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._update_line_width()
            self._draw_lines()
            self.schedule_occurrence_highlight()
            self.on_change()

    def _key_release(self, _event=None) -> None:
        self.on_cursor()
        if self._is_occurrence_modifier_key(_event):
            if self.occurrence_queries:
                self.schedule_occurrence_highlight(keep_query=True)
            return
        selected = self._current_selection_text()
        if selected:
            self.schedule_occurrence_highlight(selected_text=selected)
        elif self.occurrence_queries:
            self.schedule_occurrence_highlight(keep_query=True)

    def _button_release(self, _event=None) -> None:
        self.on_cursor()
        if self.column_edit_anchor:
            return
        add_query = self._is_add_occurrence_event(_event)
        self.after_idle(lambda: self.schedule_occurrence_highlight(add_query=add_query, selected_text=self._current_selection_text()))

    def _button_press(self, event=None) -> None:
        self.clear_column_edit()
        return None

    def _bind_column_edit_start_events(self) -> None:
        for sequence in column_edit_start_events(is_macos()):
            self.text.bind(sequence, lambda event: self._column_edit_start(event, force=True))

    def _column_edit_start(self, event, force: bool = False):
        if not force and not self._is_column_edit_event(event):
            return None
        self.column_edit_anchor = self._column_boundary_index(event.x, event.y)
        self._update_column_edit(self.column_edit_anchor)
        self.text.focus_set()
        return "break"

    def _column_edit_motion(self, event):
        if not self.column_edit_anchor:
            return None
        self._update_column_edit(self._column_boundary_index(event.x, event.y))
        return "break"

    def _column_edit_release(self, event):
        if not self.column_edit_anchor:
            return None
        self._update_column_edit(self._column_boundary_index(event.x, event.y))
        return "break"

    def clear_column_edit(self) -> None:
        self.column_edit_anchor = None
        self.column_edit_active = False
        self.column_edit_lines = []
        self.column_edit_column = 0
        self.column_edit_range_end_column = 0
        self.text.tag_remove("column_selection", "1.0", "end")
        self._clear_column_carets()

    def _is_column_edit_event(self, event) -> bool:
        if not event:
            return False
        state = int(getattr(event, "state", 0))
        if is_macos():
            return any(state & mask for mask in OPTION_ALT_MASKS)
        return bool(state & ALT_MASK)

    def _update_column_edit(self, target_index: str) -> None:
        if not self.column_edit_anchor:
            return
        anchor_line, anchor_col = self._split_index(self.column_edit_anchor)
        target_line, target_col = self._split_index(target_index)
        start_line, end_line = sorted((anchor_line, target_line))
        start_col, end_col = sorted((anchor_col, target_col))
        self.column_edit_lines = list(range(start_line, end_line + 1))
        self.column_edit_column = start_col
        self.column_edit_range_end_column = end_col
        self.column_edit_active = bool(self.column_edit_lines)
        self.text.tag_remove("column_selection", "1.0", "end")
        if end_col != start_col:
            highlight_end_col = max(start_col + 1, end_col)
            for line_no in self.column_edit_lines:
                self.text.tag_add("column_selection", f"{line_no}.{start_col}", f"{line_no}.{highlight_end_col}")
        self.text.mark_set("insert", f"{target_line}.{target_col}")
        self._draw_column_carets()

    def _column_edit_key(self, event):
        if not self.column_edit_active:
            return None
        keysym = getattr(event, "keysym", "")
        char = getattr(event, "char", "")
        if keysym == "Escape":
            self.clear_column_edit()
            return "break"
        if keysym == "BackSpace":
            self._column_edit_backspace()
            return "break"
        if keysym == "Delete":
            self._column_edit_delete()
            return "break"
        if keysym in {"Return", "KP_Enter", "Tab"}:
            text = "\n" if keysym in {"Return", "KP_Enter"} else "\t"
            self._column_edit_insert(text)
            return "break"
        if char and char >= " ":
            self._column_edit_insert(char)
            return "break"
        return None

    def _column_edit_insert(self, value: str) -> None:
        for line_no in reversed(self.column_edit_lines):
            index = self._padded_column_index(line_no, self.column_edit_column)
            self.text.insert(index, value)
        self.column_edit_column += len(value)
        self._refresh_column_edit_after_edit()

    def _column_edit_backspace(self) -> None:
        if self.column_edit_column <= 0:
            return
        target_col = self.column_edit_column - 1
        for line_no in reversed(self.column_edit_lines):
            if self._line_length(line_no) >= self.column_edit_column:
                self.text.delete(f"{line_no}.{target_col}", f"{line_no}.{self.column_edit_column}")
        self.column_edit_column = target_col
        self._refresh_column_edit_after_edit()

    def _column_edit_delete(self) -> None:
        for line_no in reversed(self.column_edit_lines):
            if self._line_length(line_no) > self.column_edit_column:
                self.text.delete(f"{line_no}.{self.column_edit_column}", f"{line_no}.{self.column_edit_column + 1}")
        self._refresh_column_edit_after_edit()

    def _refresh_column_edit_after_edit(self) -> None:
        self.text.edit_modified(True)
        self._modified()
        self.text.tag_remove("column_selection", "1.0", "end")
        self.column_edit_range_end_column = self.column_edit_column
        self._draw_column_carets()
        if self.column_edit_lines:
            self.text.mark_set("insert", f"{self.column_edit_lines[-1]}.{self.column_edit_column}")

    def _column_boundary_index(self, x: int, y: int) -> str:
        index = self.text.index(f"@{x},{y}")
        bbox = self.text.bbox(index)
        if not bbox:
            return index
        char_x, _char_y, char_w, _char_h = bbox
        if x >= char_x + max(1, char_w) / 2:
            return self.text.index(f"{index}+1c")
        return index

    def _clear_column_carets(self) -> None:
        for caret in self.column_caret_widgets:
            try:
                caret.destroy()
            except tk.TclError:
                pass
        self.column_caret_widgets = []

    def _draw_column_carets(self) -> None:
        self._clear_column_carets()
        if not self.column_edit_active:
            return
        color = self.palette.get("accent", self.palette["text"])
        for line_no in self.column_edit_lines:
            geometry = self._column_caret_geometry(line_no, self.column_edit_column)
            if not geometry:
                continue
            x, y, height = geometry
            caret = tk.Frame(self.text, bg=color, bd=0, highlightthickness=0, width=2, height=height)
            caret.place(x=x, y=y, width=2, height=height)
            self.column_caret_widgets.append(caret)

    def _column_caret_geometry(self, line_no: int, column: int) -> tuple[int, int, int] | None:
        index = f"{line_no}.{column}"
        bbox = self.text.bbox(index)
        if bbox:
            return bbox[0], bbox[1], bbox[3]
        line_info = self.text.dlineinfo(f"{line_no}.0")
        if not line_info:
            return None
        x, y, _w, height, _baseline = line_info
        text = self.text.get(f"{line_no}.0", f"{line_no}.{column}")
        return x + self.text_font.measure(text), y, height

    def _padded_column_index(self, line_no: int, column: int) -> str:
        line_length = self._line_length(line_no)
        if line_length < column:
            self.text.insert(f"{line_no}.end", " " * (column - line_length))
        return f"{line_no}.{column}"

    def _line_length(self, line_no: int) -> int:
        counted = self.text.count(f"{line_no}.0", f"{line_no}.end", "chars")
        return int(counted[0]) if counted else 0

    def _split_index(self, index: str) -> tuple[int, int]:
        line, col = self.text.index(index).split(".")
        return int(line), int(col)

    def _yscroll(self, first, last) -> None:
        self.vbar.set(first, last)
        self._draw_lines()
        if self.occurrence_queries:
            self.schedule_occurrence_highlight(180, keep_query=True)

    def _xscroll(self, first, last) -> None:
        self.hbar.set(first, last)
        self._draw_column_carets()

    def _wheel(self, event):
        if event.state & 0x0004:
            return self._font_wheel(event)
        units = -1 if event.delta > 0 else 1
        self.text.yview_scroll(units * WHEEL_SCROLL_UNITS, "units")
        return "break"

    def _font_wheel(self, event):
        self.on_font_delta(1 if event.delta > 0 else -1)
        return "break"

    def _update_line_width(self) -> None:
        total = int(self.text.index("end-1c").split(".")[0])
        digits = max(1, len(str(total)))
        width = self.line_font.measure("9" * digits) + 16
        self.line_canvas.configure(width=width)

    def _draw_lines(self) -> None:
        self.line_canvas.delete("all")
        self._update_line_width()
        i = self.text.index("@0,0")
        width = int(self.line_canvas.cget("width"))
        while True:
            dline = self.text.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            line_no = i.split(".")[0]
            self.line_canvas.create_text(width - 8, y, anchor="ne", text=line_no, fill=self.palette["muted"], font=self.line_font)
            i = self.text.index(f"{i}+1line")
        self._draw_column_carets()

    def offset_to_index(self, offset: int) -> str:
        return self.text.index(f"1.0+{max(0, offset)}c")

    def cursor_offset(self) -> int:
        counted = self.text.count("1.0", "insert", "chars")
        return int(counted[0]) if counted else 0

    def request_text_cursor_refresh(self) -> None:
        self.cursor_refresh_needed = True
        self.restore_text_cursor(force=True)

    def _refresh_cursor_if_needed(self, _event=None) -> None:
        if not self.cursor_refresh_needed:
            return
        self.cursor_refresh_needed = False
        self.restore_text_cursor(force=True)

    def restore_text_cursor(self, force: bool = False) -> None:
        if force:
            if self.cursor_refresh_job:
                self.after_cancel(self.cursor_refresh_job)
            self.text.configure(cursor=CURSOR_REFRESH_FALLBACK)
            self.cursor_refresh_job = self.after_idle(self._apply_text_cursor)
            return
        if self.text.cget("cursor") != self.text_cursor:
            self.text.configure(cursor=self.text_cursor)

    def _apply_text_cursor(self) -> None:
        self.cursor_refresh_job = None
        self.text.configure(cursor=self.text_cursor)

    def highlight_span(self, start: int, end: int) -> None:
        self.text.tag_remove("sync_highlight", "1.0", "end")
        s = self.offset_to_index(start)
        e = self.offset_to_index(max(start + 1, end))
        self.text.tag_configure("sync_highlight", background=self.palette["select"])
        self.text.tag_add("sync_highlight", s, e)
        self.text.see(s)
        self.after(900, lambda: self.text.tag_remove("sync_highlight", "1.0", "end"))

    def highlight_span_and_move_cursor(self, start: int, end: int, cursor_offset: int) -> None:
        self.highlight_span(start, end)
        cursor_index = self.offset_to_index(cursor_offset)
        self.text.mark_set("insert", cursor_index)
        self.text.see(cursor_index)
        self.text.focus_set()
        self.restore_text_cursor()

    def move_cursor_to_offset(self, offset: int) -> None:
        self.text.tag_remove("sync_highlight", "1.0", "end")
        cursor_index = self.offset_to_index(offset)
        self.text.mark_set("insert", cursor_index)
        self.text.see(cursor_index)
        self.text.focus_set()
        self.restore_text_cursor()

    def clear_occurrence_highlight(self) -> None:
        for tag in self.occurrence_tag_names:
            self.text.tag_remove(tag, "1.0", "end")

    def _current_selection_text(self) -> str:
        try:
            counted = self.text.count("sel.first", "sel.last", "chars")
            if counted and int(counted[0]) > MAX_OCCURRENCE_TEXT_LENGTH:
                return ""
            return self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return ""

    def _is_add_occurrence_event(self, event) -> bool:
        if not event:
            return self.occurrence_modifier_down
        state = int(getattr(event, "state", 0))
        if is_macos():
            return self.occurrence_modifier_down or bool(state & CONTROL_MASK) or any(state & mask for mask in MAC_COMMAND_MASKS)
        return self.occurrence_modifier_down or bool(state & CONTROL_MASK)

    def _is_occurrence_modifier_key(self, event) -> bool:
        return bool(event and getattr(event, "keysym", "") in OCCURRENCE_MODIFIER_KEYSYMS)

    def _modifier_key_press(self, event=None) -> None:
        if self._is_occurrence_modifier_key(event):
            self.occurrence_modifier_down = True

    def _modifier_key_release(self, event=None) -> None:
        if self._is_occurrence_modifier_key(event):
            self.occurrence_modifier_down = False

    def schedule_occurrence_highlight(self, delay_ms: int = 120, keep_query: bool = False, add_query: bool = False, selected_text: str | None = None) -> None:
        if self.occurrence_job:
            self.after_cancel(self.occurrence_job)
        self.keep_occurrence_query = keep_query
        self.occurrence_add_query = add_query
        self.pending_occurrence_selection = selected_text
        self.occurrence_job = self.after(delay_ms, self.highlight_selected_occurrences)

    def highlight_selected_occurrences(self) -> None:
        self.occurrence_job = None
        self.clear_occurrence_highlight()
        selected = self.pending_occurrence_selection
        self.pending_occurrence_selection = None
        if selected is None and not self.keep_occurrence_query:
            selected = self._current_selection_text()
        if not selected:
            if not self.keep_occurrence_query and not self.occurrence_add_query:
                self.occurrence_queries = []
            self.keep_occurrence_query = False
            self.occurrence_add_query = False
            if self.occurrence_queries:
                self._highlight_occurrence_queries()
            return
        self.keep_occurrence_query = False
        if selected:
            if selected.isspace() or len(selected) > MAX_OCCURRENCE_TEXT_LENGTH:
                if not self.occurrence_add_query:
                    self.occurrence_queries = []
                self.occurrence_add_query = False
                return
            if self.occurrence_add_query:
                if selected not in self.occurrence_queries:
                    self.occurrence_queries.append(selected)
                    self.occurrence_queries = self.occurrence_queries[-MAX_OCCURRENCE_QUERIES:]
            else:
                self.occurrence_queries = [selected]
        self.occurrence_add_query = False
        if not self.occurrence_queries:
            return
        self._highlight_occurrence_queries()

    def _highlight_occurrence_queries(self) -> None:
        try:
            total_chars = int(self.text.count("1.0", "end-1c", "chars")[0])
        except Exception:
            total_chars = MAX_OCCURRENCE_HIGHLIGHT_CHARS + 1
        for idx, query in enumerate(self.occurrence_queries):
            tag = self.occurrence_tag_names[idx % len(self.occurrence_tag_names)]
            if total_chars > MAX_OCCURRENCE_HIGHLIGHT_CHARS:
                self._highlight_visible_occurrences(query, tag)
            else:
                self._highlight_occurrences_between(query, tag, "1.0", "end", MAX_OCCURRENCE_MATCHES)
        self.text.tag_raise("sel")
        self.text.tag_raise("sync_highlight")

    def _highlight_visible_occurrences(self, selected: str, tag: str) -> None:
        start = self.text.index("@0,0")
        end = self.text.index(f"@0,{max(1, self.text.winfo_height())}")
        start = self.text.index(f"{start} linestart -2 lines")
        end = self.text.index(f"{end} lineend +2 lines")
        self._highlight_occurrences_between(selected, tag, start, end, MAX_VISIBLE_OCCURRENCE_MATCHES)

    def _highlight_occurrences_between(self, selected: str, tag: str, start: str, stop: str, max_matches: int) -> None:
        pos = start
        matches = 0
        while matches < max_matches:
            pos = self.text.search(selected, pos, stopindex=stop, exact=True, nocase=self.occurrence_ignore_case)
            if not pos:
                break
            end = self.text.index(f"{pos}+{len(selected)}c")
            self.text.tag_add(tag, pos, end)
            pos = end
            matches += 1

    def clear_syntax(self) -> None:
        for tag in self.syntax_tag_names:
            self.text.tag_remove(tag, "1.0", "end")

    def apply_syntax_tokens(self, tokens: list[SyntaxToken]) -> None:
        self.clear_syntax()
        for token in tokens:
            tag = f"syntax_{token.kind}"
            if tag not in self.syntax_tag_names or token.end <= token.start:
                continue
            self.text.tag_add(tag, self.offset_to_index(token.start), self.offset_to_index(token.end))
        self.text.tag_raise("sel")
        self.text.tag_raise("sync_highlight")

    def _configure_syntax_tags(self) -> None:
        for tag in self.syntax_tag_names:
            self.text.tag_configure(tag, foreground=self.palette.get(tag, self.palette["text"]))

    def _configure_occurrence_tags(self) -> None:
        for idx, tag in enumerate(self.occurrence_tag_names):
            key = "occurrence" if idx == 0 else f"occurrence_{idx}"
            self.text.tag_configure(tag, background=self.palette.get(key, self.palette["occurrence"]))
