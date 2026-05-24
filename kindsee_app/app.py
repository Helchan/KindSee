from __future__ import annotations

import uuid
from pathlib import Path
from tkinter import filedialog, font
import tkinter as tk

_ICON_DIR = Path(__file__).parent / "icon"

from .config import AppConfig, autosave_dir, clamp_font_size, clear_persistence, load_config, save_config
from .constants import APP_TITLE, AUTOSAVE_DELAY_MS, PARSE_DELAY_MS, SYNC_DELAY_MS
from .documents import (
    DocumentType,
    EmptyPositionIndex,
    TreeNode,
    any_collapsible,
    any_expandable,
    default_registry,
)
from .platforms import apply_titlebar_theme, is_macos
from .syntax import default_syntax_registry
from .tabs import TabState
from .theme import DARK, LIGHT, effective_palette
from .widgets import FastContextMenu, JsonTreeCanvas, LineNumberText, MarkdownPreview, SettingsDialog, StatusBar


class KindSeeApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1034x680")
        self.root.minsize(880, 560)
        self._center_window(1034, 680)
        self.document_registry = default_registry()
        self.syntax_registry = default_syntax_registry()
        self.config = load_config()
        self.palette = LIGHT
        self.tabs: list[TabState] = []
        self.active_tab_id: str | None = None
        self.current_tree: TreeNode | None = None
        self.position_index = EmptyPositionIndex()
        self.parse_job = None
        self.autosave_job = None
        self.sync_job = None
        self.loading_text = False
        self.pending_auto_detect_after_change = False
        self.untitled_counter = 1
        self.menu_font = font.Font(size=10)
        self.toolbar_font = font.Font(size=16)
        self.tab_font = font.Font(size=13)
        self.current_view_mode = "split"
        self.settings_dialog: SettingsDialog | None = None
        self.toolbar_hotspots: list[tuple[int, int, int, int, object]] = []
        self.tab_hotspots: list[tuple[int, int, int, int, str, str]] = []
        self._build_ui()
        self._load_tabs()
        self.apply_theme()
        self.bind_shortcuts()
        self._try_tkdnd()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self._initial_sash)
        self.root.after(120, self.editor.request_text_cursor_refresh)
        self.root.after(360, self.editor.request_text_cursor_refresh)

    def _center_window(self, w: int, h: int) -> None:
        self.root.update_idletasks()
        x = max(0, (self.root.winfo_screenwidth() - w) // 2)
        y = max(0, (self.root.winfo_screenheight() - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.toolbar = tk.Canvas(self.root, height=40, bd=0, highlightthickness=0)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        self._load_toolbar_icons()
        self._build_toolbar()
        self.tab_bar = tk.Canvas(self.root, height=36, bd=0, highlightthickness=0)
        self.tab_bar.grid(row=1, column=0, sticky="ew")
        self.tab_bar.bind("<Configure>", lambda _e: self.draw_tabs())
        self.tab_bar.bind("<Button-1>", self._tab_click)
        self.tab_bar.bind("<Motion>", self._tab_motion)
        self.tab_bar.bind("<Leave>", lambda _e: self.tab_bar.configure(cursor=""))
        self.paned = tk.PanedWindow(self.root, orient="horizontal", sashwidth=6, bd=0, showhandle=False)
        self.paned.grid(row=2, column=0, sticky="nsew")
        self.tree_panel = tk.Frame(self.paned, bd=0, highlightthickness=0)
        self.preview_panel = tk.Frame(self.paned, bd=0, highlightthickness=0)
        self.text_panel = tk.Frame(self.paned, bd=0, highlightthickness=0)
        self.tree = JsonTreeCanvas(self.tree_panel, self.on_tree_select, self.show_tree_menu, self.adjust_tree_font)
        self.preview = MarkdownPreview(self.preview_panel, self.adjust_tree_font)
        self.editor = LineNumberText(self.text_panel, self.on_text_change, self.on_cursor_move, self.adjust_text_font)
        self.tree.pack(fill="both", expand=True)
        self.preview.pack(fill="both", expand=True)
        self.editor.pack(fill="both", expand=True)
        self.paned.add(self.tree_panel, minsize=280)
        self.paned.add(self.text_panel, minsize=420)
        self.status = StatusBar(self.root, self)
        self.status.grid(row=3, column=0, sticky="ew")
        self.editor.text.bind("<Button-2>", self.show_text_menu)
        self.editor.text.bind("<Button-3>", self.show_text_menu)
        self.editor.text.bind("<<Paste>>", self.before_text_paste, add="+")
        self.editor.set_occurrence_ignore_case(self.config.occurrence_ignore_case)

    def _build_toolbar(self) -> None:
        self.toolbar.bind("<Configure>", lambda _e: self.draw_toolbar())
        self.toolbar.bind("<Button-1>", self._toolbar_click)
        self.toolbar.bind("<Motion>", self._toolbar_motion)
        self.toolbar.bind("<Leave>", lambda _e: self.toolbar.configure(cursor=""))

    def _load_toolbar_icons(self) -> None:
        """加载工具栏图标并缩放至适当尺寸"""
        self._icon_open = tk.PhotoImage(file=str(_ICON_DIR / "open.png")).subsample(11)
        self._icon_save = tk.PhotoImage(file=str(_ICON_DIR / "save.png")).subsample(11)
        self._icon_settings = tk.PhotoImage(file=str(_ICON_DIR / "setting.png")).subsample(11)

    def draw_toolbar(self) -> None:
        self.toolbar.delete("all")
        self.toolbar.configure(bg=self.palette["panel2"])
        h = max(1, self.toolbar.winfo_height())
        w = max(1, self.toolbar.winfo_width())
        self.toolbar.create_rectangle(0, 0, w, h, fill=self.palette["panel2"], width=0)
        items = [
            (self._icon_open, self.open_files),
            (self._icon_save, self.save_current_file),
            (self._icon_settings, self.open_settings),
        ]
        self.toolbar_hotspots = []
        x = 10
        for icon_img, command in items:
            btn_width = 32
            self.toolbar.create_image(x + btn_width // 2, h // 2, image=icon_img)
            self.toolbar_hotspots.append((x, 4, x + btn_width, h - 4, command))
            x += btn_width + 6

    def _toolbar_click(self, event) -> None:
        for x1, y1, x2, y2, command in self.toolbar_hotspots:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                command()
                return

    def _toolbar_motion(self, event) -> None:
        self.toolbar.configure(cursor="")

    def _initial_sash(self) -> None:
        try:
            width = self.root.winfo_width()
            self.paned.sash_place(0, max(320, width // 3), 0)
        except Exception:
            pass

    def bind_shortcuts(self) -> None:
        mod = "Command" if is_macos() else "Control"
        self.root.bind_all(f"<{mod}-s>", lambda _e: (self.save_current_file(), "break"))
        self.root.bind_all(f"<{mod}-o>", lambda _e: (self.open_files(), "break"))
        self.root.bind_all(f"<{mod}-c>", self.copy_tree_shortcut)
        self.root.bind_all("<Control-s>", lambda _e: (self.save_current_file(), "break"))
        self.root.bind_all("<Control-o>", lambda _e: (self.open_files(), "break"))

    def _try_tkdnd(self) -> None:
        try:
            self.root.tk.call("package", "require", "tkdnd")
            self.root.tk.call("tkdnd::drop_target", "register", self.root, "DND_Files")
            self.root.bind("<<Drop>>", self._drop_files)
        except Exception:
            pass

    def _drop_files(self, event) -> None:
        files = self.root.tk.splitlist(event.data)
        self.open_paths([Path(p) for p in files])

    def current_document_type(self) -> DocumentType:
        if not self.active_tab_id:
            return self.document_registry.get(None)
        return self.document_registry.get(self.current_tab().document_type)

    def document_type_menu_items(self) -> list[tuple]:
        current_type_id = self.current_document_type().type_id
        items = []
        for doc_type in self.document_registry.all_types():
            label = doc_type.default_extension
            if doc_type.type_id == current_type_id:
                label = f"✓ {label}"
            items.append((label, lambda type_id=doc_type.type_id: self.switch_document_type(type_id), True))
        return items

    def switch_document_type(self, type_id: str) -> None:
        if not self.active_tab_id:
            return
        tab = self.current_tab()
        if tab.document_type == type_id:
            tab.document_type_locked = True
            self.save_session()
            return
        if self.parse_job:
            self.root.after_cancel(self.parse_job)
            self.parse_job = None
        tab.content = self.editor.get()
        tab.document_type = self.document_registry.get(type_id).type_id
        tab.document_type_locked = True
        self.current_tree = None
        self.position_index = EmptyPositionIndex()
        self.apply_document_view_mode()
        self.parse_now()
        self.refresh_tabs()
        self.save_session()

    def apply_syntax_highlighting(self) -> None:
        if not self.active_tab_id:
            self.editor.clear_syntax()
            return
        doc_type = self.current_document_type()
        if not doc_type.parse_on_change:
            self.editor.clear_syntax()
            return
        tokens = self.syntax_registry.get(doc_type.type_id).highlight(self.editor.get())
        self.editor.apply_syntax_tokens(tokens)

    def apply_document_view_mode(self) -> None:
        doc_type = self.current_document_type()
        mode = doc_type.view_mode
        if mode == self.current_view_mode:
            return
        panes = {str(pane) for pane in self.paned.panes()}
        tree_name = str(self.tree_panel)
        preview_name = str(self.preview_panel)
        text_name = str(self.text_panel)
        if mode == "preview":
            if tree_name in panes:
                self.paned.forget(self.tree_panel)
            if text_name in {str(pane) for pane in self.paned.panes()}:
                self.paned.forget(self.text_panel)
            if preview_name not in {str(pane) for pane in self.paned.panes()}:
                self.paned.add(self.preview_panel, minsize=280)
            self.paned.add(self.text_panel, minsize=420)
            self.root.after(50, self._initial_sash)
        if mode == "text":
            if tree_name in panes:
                self.paned.forget(self.tree_panel)
            if preview_name in {str(pane) for pane in self.paned.panes()}:
                self.paned.forget(self.preview_panel)
            if text_name not in {str(pane) for pane in self.paned.panes()}:
                self.paned.add(self.text_panel, minsize=420)
        elif mode != "preview":
            if preview_name in panes:
                self.paned.forget(self.preview_panel)
            if tree_name not in panes:
                if text_name in panes:
                    self.paned.forget(self.text_panel)
                self.paned.add(self.tree_panel, minsize=280)
                self.paned.add(self.text_panel, minsize=420)
            self.root.after(50, self._initial_sash)
        self.current_view_mode = mode

    def should_auto_detect_document_type(self) -> bool:
        if not self.active_tab_id:
            return False
        tab = self.current_tab()
        return not tab.file_path and not tab.document_type_locked

    def auto_detect_document_type(self, text: str, force: bool = False) -> bool:
        if not force and not self.should_auto_detect_document_type():
            return False
        tab = self.current_tab()
        if force:
            tab.document_type_locked = False
        detected = self.document_registry.detect_content(text, "text")
        if detected.type_id == tab.document_type:
            return False
        tab.document_type = detected.type_id
        self.current_tree = None
        self.position_index = EmptyPositionIndex()
        self.apply_document_view_mode()
        self.refresh_tabs()
        return True

    def should_detect_after_content_change(self, previous: str, current: str) -> tuple[bool, bool]:
        if not self.active_tab_id or self.current_tab().file_path:
            return False, False
        force = self.pending_auto_detect_after_change or (not previous.strip() and bool(current.strip()))
        if force:
            return True, True
        return False, False

    def selection_covers_all_text(self) -> bool:
        try:
            return bool(self.editor.text.compare("sel.first", "==", "1.0") and self.editor.text.compare("sel.last", "==", "end-1c"))
        except tk.TclError:
            return False

    def mark_auto_detect_if_content_will_be_replaced(self) -> None:
        self.pending_auto_detect_after_change = self.pending_auto_detect_after_change or self.selection_covers_all_text() or not self.editor.get().strip()

    def before_text_paste(self, _event=None):
        self.mark_auto_detect_if_content_will_be_replaced()
        return None

    def _load_tabs(self) -> None:
        for meta in self.config.tabs:
            tab = self._tab_from_meta(meta)
            if tab:
                self.tabs.append(tab)
        if not self.tabs:
            content = self.config.legacy_text_content or ""
            self.tabs.append(self._new_tab_state("未命名", content=content))
        active = self.config.active_tab_id if any(t.id == self.config.active_tab_id for t in self.tabs) else self.tabs[0].id
        self.switch_tab(active)

    def _tab_from_meta(self, meta: dict) -> TabState | None:
        try:
            tab_id = str(meta.get("id") or uuid.uuid4().hex)
            file_path = str(meta.get("file_path") or "")
            autosave_path = str(meta.get("autosave_path") or "")
            if meta.get("document_type"):
                doc_type = self.document_registry.get(meta.get("document_type"))
            elif file_path:
                doc_type = self.document_registry.detect(Path(file_path))
            else:
                doc_type = self.document_registry.get("text")
            title = str(meta.get("title") or (Path(file_path).name if file_path else "未命名"))
            content = ""
            if file_path and Path(file_path).exists():
                content = Path(file_path).read_text(encoding="utf-8")
            elif autosave_path and Path(autosave_path).exists():
                content = Path(autosave_path).read_text(encoding="utf-8")
            return TabState(tab_id, title, file_path, autosave_path, bool(meta.get("dirty")), content, doc_type.type_id, bool(meta.get("document_type_locked")))
        except Exception:
            return None

    def _new_tab_state(self, title: str | None = None, content: str = "", document_type: DocumentType | None = None) -> TabState:
        doc_type = document_type or self.document_registry.get("text")
        if title is None:
            title = f"未命名{self.untitled_counter}"
            self.untitled_counter += 1
        tab_id = uuid.uuid4().hex
        auto = autosave_dir() / f"{tab_id}{doc_type.default_extension}"
        return TabState(tab_id, title, "", str(auto), False, content, doc_type.type_id)

    def current_tab(self) -> TabState:
        return next(t for t in self.tabs if t.id == self.active_tab_id)

    def active_tab_or_none(self) -> TabState | None:
        if not self.active_tab_id:
            return None
        return next((t for t in self.tabs if t.id == self.active_tab_id), None)

    def refresh_tabs(self) -> None:
        self.draw_tabs()

    def draw_tabs(self) -> None:
        self.tab_bar.delete("all")
        self.tab_bar.configure(bg=self.palette["bg"])
        w = max(1, self.tab_bar.winfo_width())
        h = max(1, self.tab_bar.winfo_height())
        self.tab_bar.create_rectangle(0, 0, w, h, fill=self.palette["bg"], width=0)
        self.tab_hotspots = []
        x = 8
        y = 4
        tab_h = 28
        for tab in self.tabs:
            selected = tab.id == self.active_tab_id
            title = tab.title + (" *" if tab.dirty else "")
            title_w = self.tab_font.measure(title)
            tab_w = max(116, min(240, title_w + 48))
            bg = self.palette["panel"] if selected else self.palette["tab_inactive"]
            fg = self.palette["text"] if selected else self.palette["muted"]
            self.tab_bar.create_rectangle(x, y, x + tab_w, y + tab_h, fill=bg, outline="")
            self.tab_bar.create_text(x + 12, y + tab_h // 2, text=title, anchor="w", fill=fg, font=self.tab_font)
            close_x1 = x + tab_w - 32
            self.tab_bar.create_text(close_x1 + 14, y + tab_h // 2, text="×", anchor="center", fill=self.palette["muted"], font=self.tab_font)
            if selected:
                self.tab_bar.create_rectangle(x, y + tab_h - 2, x + tab_w, y + tab_h, fill=self.palette["accent"], outline="")
            self.tab_hotspots.append((x, y, close_x1, y + tab_h, "select", tab.id))
            self.tab_hotspots.append((close_x1, y, x + tab_w, y + tab_h, "close", tab.id))
            x += tab_w + 6
        add_w = 40
        self.tab_bar.create_rectangle(x, y, x + add_w, y + tab_h, fill=self.palette["panel2"], outline="")
        self.tab_bar.create_text(x + add_w // 2, y + tab_h // 2, text="+", anchor="center", fill=self.palette["accent"], font=self.tab_font)
        self.tab_hotspots.append((x, y, x + add_w, y + tab_h, "new", ""))

    def _tab_click(self, event) -> None:
        for x1, y1, x2, y2, action, tab_id in self.tab_hotspots:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if action == "select":
                    self.switch_tab(tab_id)
                elif action == "close":
                    self.close_tab(tab_id)
                elif action == "new":
                    self.new_tab()
                return

    def _tab_motion(self, event) -> None:
        self.tab_bar.configure(cursor="")

    def switch_tab(self, tab_id: str) -> None:
        previous_tab = self.active_tab_or_none()
        if previous_tab:
            previous_tab.content = self.editor.get()
        if not any(t.id == tab_id for t in self.tabs):
            return
        self.active_tab_id = tab_id
        tab = self.current_tab()
        self.loading_text = True
        self.editor.set(tab.content)
        self.loading_text = False
        self.apply_document_view_mode()
        self.parse_now()
        self.refresh_tabs()
        self.update_title()
        self.save_session()
        self.editor.request_text_cursor_refresh()

    def new_tab(self) -> None:
        previous_tab = self.active_tab_or_none()
        if previous_tab:
            previous_tab.content = self.editor.get()
        tab = self._new_tab_state()
        self.tabs.append(tab)
        self.switch_tab(tab.id)
        self.set_status("已新增页签")

    def close_tab(self, tab_id: str) -> None:
        if not any(t.id == tab_id for t in self.tabs):
            self.refresh_tabs()
            return
        if len(self.tabs) == 1:
            tab = self.tabs[0]
            self.active_tab_id = tab.id
            tab.content = ""
            tab.file_path = ""
            tab.title = "未命名"
            tab.dirty = False
            tab.document_type = self.document_registry.get("text").type_id
            tab.document_type_locked = False
            self.editor.set("")
            self.apply_document_view_mode()
            self.parse_now()
            self.refresh_tabs()
            self.save_session()
            self.editor.request_text_cursor_refresh()
            return
        idx = next((i for i, t in enumerate(self.tabs) if t.id == tab_id), 0)
        closing = self.tabs[idx]
        if closing.id == self.active_tab_id:
            closing.content = self.editor.get()
        self.tabs = [t for t in self.tabs if t.id != tab_id]
        try:
            if closing.autosave_path and Path(closing.autosave_path).exists():
                Path(closing.autosave_path).unlink()
        except Exception:
            pass
        if self.active_tab_id == tab_id:
            self.switch_tab(self.tabs[min(idx, len(self.tabs) - 1)].id)
        else:
            self.refresh_tabs()
            self.save_session()

    def on_text_change(self) -> None:
        if self.loading_text or not self.active_tab_id:
            return
        tab = self.current_tab()
        previous_content = tab.content
        current_content = self.editor.get()
        should_auto_detect, force_auto_detect = self.should_detect_after_content_change(previous_content, current_content)
        self.pending_auto_detect_after_change = False
        tab.content = current_content
        tab.dirty = True
        self.refresh_tabs()
        self.update_title()
        if self.parse_job:
            self.root.after_cancel(self.parse_job)
        if self.autosave_job:
            self.root.after_cancel(self.autosave_job)
        if self.current_document_type().parse_on_change or should_auto_detect:
            self.parse_job = self.root.after(
                PARSE_DELAY_MS,
                lambda detect=should_auto_detect, force=force_auto_detect: self.parse_now(auto_detect=detect, force_auto_detect=force),
            )
        self.autosave_job = self.root.after(AUTOSAVE_DELAY_MS, self.autosave_current)

    def parse_now(self, auto_detect: bool = False, force_auto_detect: bool = False) -> None:
        self.parse_job = None
        text = self.editor.get()
        if self.active_tab_id:
            self.current_tab().content = text
        if auto_detect:
            self.auto_detect_document_type(text, force=force_auto_detect)
        doc_type = self.current_document_type()
        if not doc_type.parse_on_change:
            self.current_tree = None
            self.position_index = EmptyPositionIndex()
            self.tree.set_tree(None)
            self.preview.clear()
            self.editor.clear_syntax()
            self.set_status(doc_type.empty_status if self.editor.is_empty() else "", False)
            return
        result = doc_type.parse(text)
        self.current_tree = result.tree
        self.position_index = result.position_index
        self.tree.set_tree(result.tree)
        if doc_type.view_mode == "preview":
            self.preview.set_markdown(text)
        else:
            self.preview.clear()
        self.apply_syntax_highlighting()
        self.set_status(result.status, result.error)

    def autosave_current(self) -> None:
        self.autosave_job = None
        if not self.active_tab_id:
            return
        tab = self.current_tab()
        tab.content = self.editor.get()
        if not tab.autosave_path:
            doc_type = self.document_registry.get(tab.document_type)
            tab.autosave_path = str(autosave_dir() / f"{tab.id}{doc_type.default_extension}")
        try:
            autosave_dir().mkdir(parents=True, exist_ok=True)
            Path(tab.autosave_path).write_text(tab.content, encoding="utf-8")
        except Exception:
            pass
        self.save_session()

    def save_session(self) -> None:
        if self.active_tab_id:
            try:
                self.current_tab().content = self.editor.get()
            except Exception:
                pass
        metas = []
        for tab in self.tabs:
            metas.append(
                {
                    "id": tab.id,
                    "title": tab.title,
                    "file_path": tab.file_path,
                    "autosave_path": tab.autosave_path,
                    "dirty": tab.dirty,
                    "document_type": tab.document_type,
                    "document_type_locked": tab.document_type_locked,
                }
            )
        self.config.tabs = metas
        self.config.active_tab_id = self.active_tab_id
        save_config(self.config)

    def set_status(self, text: str, error: bool = False) -> None:
        self.status.set_status(text, error)
        if text and not error:
            self.root.after(2600, lambda: self.status.set_status("", False) if self.status.status_text == text else None)

    def open_settings(self) -> None:
        if self.settings_dialog is not None and self.settings_dialog.winfo_exists():
            self.settings_dialog.lift()
            self.settings_dialog.focus_force()
            return
        self.settings_dialog = SettingsDialog(self)

    def set_occurrence_ignore_case(self, enabled: bool) -> None:
        self.config.occurrence_ignore_case = bool(enabled)
        self.editor.set_occurrence_ignore_case(self.config.occurrence_ignore_case)
        self.save_session()

    def update_title(self) -> None:
        if not self.active_tab_id:
            self.root.title(APP_TITLE)
            return
        title = self.current_tab().title
        self.root.title(f"{APP_TITLE} - {title}" if title else APP_TITLE)

    def apply_theme(self) -> None:
        self.palette, effective_dark = effective_palette(self.config.theme)
        p = self.palette
        self.root.configure(bg=p["bg"])
        self.toolbar.configure(bg=p["panel2"])
        self.tab_bar.configure(bg=p["bg"])
        self.paned.configure(bg=p["border"], sashrelief="flat")
        self.tree_panel.configure(bg=p["panel"])
        self.preview_panel.configure(bg=p["panel"])
        self.text_panel.configure(bg=p["panel"])
        self.editor.set_palette(p)
        self.tree.set_palette(p)
        self.preview.set_palette(p)
        self.status.set_palette(p)
        self.editor.set_font_size(self.config.text_font_size)
        self.editor.set_occurrence_ignore_case(self.config.occurrence_ignore_case)
        self.tree.set_font_size(self.config.tree_font_size)
        self.preview.set_font_size(self.config.tree_font_size)
        self.apply_syntax_highlighting()
        self._apply_toolbar_palette()
        self.refresh_tabs()
        if self.settings_dialog is not None and self.settings_dialog.winfo_exists():
            self.settings_dialog.apply_palette(p)
        apply_titlebar_theme(self.root, effective_dark)

    def _apply_toolbar_palette(self) -> None:
        self.draw_toolbar()
        self.draw_tabs()

    def toggle_theme(self) -> None:
        current_dark = self.palette is DARK
        self.config.theme = "light" if current_dark else "dark"
        self.apply_theme()
        self.save_session()

    def toggle_sync(self) -> None:
        self.config.sync_display = not self.config.sync_display
        self.save_session()
        self.editor.request_text_cursor_refresh()
        self.editor.text.focus_set()
        self.root.after(80, self.editor.request_text_cursor_refresh)

    def reset_settings(self) -> None:
        defaults = AppConfig()
        self.config.tree_font_size = defaults.tree_font_size
        self.config.text_font_size = defaults.text_font_size
        self.config.theme = defaults.theme
        self.config.sync_display = defaults.sync_display
        self.config.occurrence_ignore_case = defaults.occurrence_ignore_case
        self.editor.set_occurrence_ignore_case(self.config.occurrence_ignore_case)
        self.apply_theme()
        self.save_session()
        self.set_status("设置已重置")

    def reset_all(self) -> None:
        clear_persistence()
        self.config = AppConfig()
        self.tabs = [self._new_tab_state("未命名")]
        self.active_tab_id = None
        self.switch_tab(self.tabs[0].id)
        self.apply_theme()
        self.set_status("已重置")

    def adjust_text_font(self, delta: int) -> None:
        self.config.text_font_size = clamp_font_size(self.config.text_font_size + delta)
        self.editor.set_font_size(self.config.text_font_size)
        self.save_session()

    def adjust_tree_font(self, delta: int) -> None:
        self.config.tree_font_size = clamp_font_size(self.config.tree_font_size + delta)
        self.tree.set_font_size(self.config.tree_font_size)
        self.save_session()

    def show_text_menu(self, event):
        doc_type = self.current_document_type()
        sync_label = "✓ 同步" if self.config.sync_display else "同步"
        sync_enabled = doc_type.view_mode == "split"
        items = [
            ("格式化", self.format_text, doc_type.supports_format),
            ("压缩", self.compact_text, doc_type.supports_compact),
            ("-", None, False),
            ("类型", self.document_type_menu_items(), True, "submenu"),
            ("-", None, False),
            (sync_label, self.toggle_sync, sync_enabled),
            ("-", None, False),
            ("复制", self.copy_text, True),
            ("粘贴", self.paste_text, True),
            ("-", None, False),
            ("清空", self.clear_text, True),
        ]
        FastContextMenu(self.root, items, self.palette, self.menu_font).popup(event.x_root, event.y_root)
        self.editor.request_text_cursor_refresh()
        self.root.after(250, self.editor.request_text_cursor_refresh)
        self.root.after(800, self.editor.request_text_cursor_refresh)
        return "break"

    def format_text(self) -> None:
        try:
            content = self.current_document_type().format_text(self.editor.get())
        except Exception as exc:
            self.set_status(f"格式化失败：{exc}", error=True)
            return
        self.editor.replace_all(content)

    def compact_text(self) -> None:
        try:
            content = self.current_document_type().compact_text(self.editor.get())
        except Exception as exc:
            self.set_status(f"压缩失败：{exc}", error=True)
            return
        self.editor.replace_all(content)

    def copy_text(self) -> None:
        try:
            content = self.editor.text.get("sel.first", "sel.last")
        except tk.TclError:
            content = self.editor.get()
        self.clipboard_set(content)

    def paste_text(self) -> None:
        try:
            content = self.root.clipboard_get()
        except Exception:
            return
        self.mark_auto_detect_if_content_will_be_replaced()
        try:
            self.editor.text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.editor.text.insert("insert", content)
        self.editor.text.edit_modified(True)
        self.editor._modified()

    def clear_text(self) -> None:
        self.editor.replace_all("")
        if self.active_tab_id:
            tab = self.current_tab()
            tab.dirty = True
            tab.content = ""
        self.parse_now()

    def show_tree_menu(self, x: int, y: int, node: TreeNode | None) -> None:
        root = self.current_tree
        sync_label = "✓ 同步" if self.config.sync_display else "同步"
        expand_all_enabled = any_expandable(root)
        collapse_all_enabled = any_collapsible(root)
        can_expand_item = bool(node and node.can_expand_item)
        can_collapse_item = bool(node and node.can_collapse_item)
        has_node = node is not None
        items = [
            ("展开所有", lambda: self.tree.expand_all(), expand_all_enabled),
            ("展开此项", lambda: self.tree.expand_item(node), can_expand_item),
            ("-", None, False),
            ("折叠所有", self.tree.collapse_all, collapse_all_enabled),
            ("折叠此项", lambda: self.tree.collapse_item(node), can_collapse_item),
            ("-", None, False),
            ("复制", lambda: self.copy_node(node, "node"), has_node),
            ("复制值", lambda: self.copy_node(node, "value"), has_node),
            ("复制路径", lambda: self.copy_node(node, "path"), has_node),
            ("-", None, False),
            ("类型", self.document_type_menu_items(), True, "submenu"),
            ("-", None, False),
            (sync_label, self.toggle_sync, True),
        ]
        FastContextMenu(self.root, items, self.palette, self.menu_font).popup(x, y)

    def on_tree_select(self, node: TreeNode | None) -> None:
        if not node or not self.config.sync_display:
            return
        cursor_offset = self.position_index.cursor_positions.get(node.path)
        if cursor_offset is None:
            span = self.position_index.positions.get(node.path)
            if not span:
                return
            cursor_offset = span[0]
        self.editor.move_cursor_to_offset(cursor_offset)

    def on_cursor_move(self) -> None:
        if not self.config.sync_display:
            return
        if self.sync_job:
            self.root.after_cancel(self.sync_job)
        self.sync_job = self.root.after(SYNC_DELAY_MS, self._sync_from_cursor)

    def _sync_from_cursor(self) -> None:
        self.sync_job = None
        if not self.current_tree:
            return
        path = self.position_index.path_for_offset(self.editor.cursor_offset())
        self.tree.select_path(path)

    def copy_tree_shortcut(self, event):
        focus = self.root.focus_get()
        if focus is self.editor.text:
            return None
        if self.tree.selected:
            self.copy_node(self.tree.selected, "node")
            return "break"
        return None

    def copy_node(self, node: TreeNode | None, mode: str) -> None:
        if not node:
            return
        doc_type = self.current_document_type()
        if mode == "path":
            text = doc_type.copy_node_path(node)
        elif mode == "value":
            text = doc_type.copy_node_value(node)
        else:
            text = doc_type.copy_node(node)
        self.clipboard_set(text)

    def clipboard_set(self, text: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            pass

    def open_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="打开文件",
            filetypes=self.document_registry.filetypes(),
        )
        self.open_paths([Path(p) for p in paths])

    def open_paths(self, paths: list[Path]) -> None:
        for path in paths:
            try:
                resolved = str(path.expanduser().resolve())
                existing = next((t for t in self.tabs if t.file_path == resolved), None)
                if existing:
                    self.switch_tab(existing.id)
                    continue
                file_path = Path(resolved)
                doc_type = self.document_registry.detect(file_path)
                content = file_path.read_text(encoding="utf-8")
                tab = self._new_tab_state(file_path.name, content, doc_type)
                tab.file_path = resolved
                tab.dirty = False
                self.tabs.append(tab)
                self.switch_tab(tab.id)
                self.set_status(f"已打开：{file_path.name}")
            except Exception as exc:
                self.set_status(f"打开失败：{exc}", error=True)

    def save_current_file(self) -> None:
        tab = self.current_tab()
        doc_type = self.current_document_type()
        path = tab.file_path
        if not path:
            selected = filedialog.asksaveasfilename(
                title="保存文件",
                defaultextension=doc_type.default_extension,
                filetypes=self.document_registry.filetypes(),
            )
            if not selected:
                return
            path = selected
        try:
            content = self.editor.get()
            Path(path).write_text(content, encoding="utf-8")
            saved_path = Path(path).resolve()
            tab.file_path = str(saved_path)
            tab.document_type = self.document_registry.detect(saved_path).type_id
            tab.title = saved_path.name
            tab.dirty = False
            tab.content = content
            if tab.autosave_path and Path(tab.autosave_path).exists():
                try:
                    Path(tab.autosave_path).unlink()
                except Exception:
                    pass
            self.apply_document_view_mode()
            self.parse_now()
            self.refresh_tabs()
            self.update_title()
            self.save_session()
            self.set_status("已保存")
        except Exception as exc:
            self.set_status(f"保存失败：{exc}", error=True)

    def close(self) -> None:
        self.autosave_current()
        self.save_session()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
