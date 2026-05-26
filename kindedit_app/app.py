from __future__ import annotations

import platform
import uuid
from pathlib import Path
import sys
from tkinter import filedialog, font, messagebox
import tkinter as tk

_APP_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
_ICON_DIR = Path(__file__).parent / "icon"
_VENDOR_DIR = _APP_ROOT / "vendor"
if _VENDOR_DIR.exists() and str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

try:
    from tkinterdnd2 import TkinterDnD
except Exception:
    TkinterDnD = None

from .config import AppConfig, autosave_dir, clamp_font_size, clear_persistence, load_config, save_config
from .constants import APP_TITLE, APP_VERSION_TEXT, AUTOSAVE_DELAY_MS, BRAND_TEXT, LATEST_VERSION_TEXT, LATEST_VERSION_URL, PARSE_DELAY_MS, SYNC_DELAY_MS
from .documents import (
    DocumentType,
    EmptyPositionIndex,
    TreeNode,
    any_collapsible,
    any_expandable,
    default_registry,
)
from .large_text import (
    LARGE_TEXT_AUTOSAVE_DELAY_MS,
    is_large_file,
    is_large_text_size,
    large_text_status,
)
from .platforms import apply_titlebar_theme, is_macos
from .syntax import default_syntax_registry
from .tabs import TabState
from .theme import DARK, LIGHT, effective_palette
from .widgets import FastContextMenu, JsonTreeCanvas, LineNumberText, MarkdownPreview, SettingsDialog, StatusBar

TAB_TITLE_FONT_SIZE = 10
TAB_TITLE_MAX_CHARS = 20
TAB_TITLE_PREFIX_CHARS = 17


class KindEditApp:
    def __init__(self):
        self.root = self._create_root()
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
        self.saving_large_text = False
        self.pending_after_large_save = None
        self.pending_auto_detect_after_change = False
        self.untitled_counter = 1
        self.menu_font = font.Font(size=10)
        self.toolbar_font = font.Font(size=16)
        self.tab_font = font.Font(size=TAB_TITLE_FONT_SIZE)
        self.current_view_mode = "split"
        self.settings_dialog: SettingsDialog | None = None
        self.toolbar_hotspots: list[tuple[int, int, int, int, object]] = []
        self.hovered_toolbar_index: int | None = None
        self.tab_hotspots: list[tuple[int, int, int, int, str, str, str]] = []
        self.tab_tooltip: tk.Toplevel | None = None
        self.tab_tooltip_tab_id: str | None = None
        self.effective_dark = False
        self._build_ui()
        self._load_tabs()
        self.apply_theme()
        self.bind_shortcuts()
        self._try_tkdnd()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self._initial_sash)
        self.root.after(120, self.editor.request_text_cursor_refresh)
        self.root.after(360, self.editor.request_text_cursor_refresh)

    def _create_root(self):
        return tk.Tk()

    def _center_window(self, w: int, h: int) -> None:
        self.root.update_idletasks()
        x = max(0, (self.root.winfo_screenwidth() - w) // 2)
        y = max(0, (self.root.winfo_screenheight() - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.toolbar = tk.Canvas(self.root, height=36, bd=0, highlightthickness=0)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        self._load_toolbar_icons()
        self._build_toolbar()
        self.tab_bar = tk.Canvas(self.root, height=36, bd=0, highlightthickness=0)
        self.tab_bar.grid(row=1, column=0, sticky="ew")
        self.tab_bar.bind("<Configure>", lambda _e: self.draw_tabs())
        self.tab_bar.bind("<Button-1>", self._tab_click)
        self.tab_bar.bind("<Motion>", self._tab_motion)
        self.tab_bar.bind("<Leave>", self._tab_leave)
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
        self.editor.text.bind("<<Paste>>", self.before_text_paste)
        self.editor.set_occurrence_ignore_case(self.config.occurrence_ignore_case)

    def _build_toolbar(self) -> None:
        self.toolbar.bind("<Configure>", lambda _e: self.draw_toolbar())
        self.toolbar.bind("<Button-1>", self._toolbar_click)
        self.toolbar.bind("<Motion>", self._toolbar_motion)
        self.toolbar.bind("<Leave>", self._toolbar_leave)

    def _load_toolbar_icons(self) -> None:
        """加载工具栏图标并缩放至适当尺寸"""
        self._icon_open = tk.PhotoImage(master=self.root, file=str(_ICON_DIR / "open.png")).subsample(11)
        self._icon_save = tk.PhotoImage(master=self.root, file=str(_ICON_DIR / "save.png")).subsample(11)
        self._icon_settings = tk.PhotoImage(master=self.root, file=str(_ICON_DIR / "setting.png")).subsample(11)
        self._icon_about = tk.PhotoImage(master=self.root, file=str(_ICON_DIR / "about.png")).subsample(11)

    def draw_toolbar(self) -> None:
        self.toolbar.delete("all")
        toolbar_bg = self.palette.get("toolbar", self.palette["panel"])
        self.toolbar.configure(bg=toolbar_bg)
        h = max(1, self.toolbar.winfo_height())
        w = max(1, self.toolbar.winfo_width())
        self.toolbar.create_rectangle(0, 0, w, h, fill=toolbar_bg, width=0)
        items = [
            (self._icon_open, self.open_files),
            (self._icon_save, self.save_current_file),
            (self._icon_settings, self.open_settings),
            (self._icon_about, self.show_about),
        ]
        self.toolbar_hotspots = []
        x = 10
        for index, (icon_img, command) in enumerate(items):
            btn_width = 32
            x1, y1, x2, y2 = x, 3, x + btn_width, h - 3
            if index == self.hovered_toolbar_index:
                self.toolbar.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=self.palette["hover"],
                    outline=self.palette["border"],
                    width=1,
                )
            self.toolbar.create_image(x + btn_width // 2, h // 2, image=icon_img)
            self.toolbar_hotspots.append((x1, y1, x2, y2, command))
            x += btn_width + 6

    def _toolbar_click(self, event) -> None:
        for x1, y1, x2, y2, command in self.toolbar_hotspots:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                command()
                return

    def _toolbar_motion(self, event) -> None:
        self.toolbar.configure(cursor="")
        hovered = None
        for index, (x1, y1, x2, y2, _command) in enumerate(self.toolbar_hotspots):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                hovered = index
                break
        if hovered != self.hovered_toolbar_index:
            self.hovered_toolbar_index = hovered
            self.draw_toolbar()

    def _toolbar_leave(self, _event) -> None:
        self.toolbar.configure(cursor="")
        if self.hovered_toolbar_index is not None:
            self.hovered_toolbar_index = None
            self.draw_toolbar()

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
        self.root.bind_all(f"<{mod}-z>", self.undo_text)
        self.root.bind_all(f"<{mod}-Shift-Z>", self.redo_text)
        self.root.bind_all(f"<{mod}-c>", self.copy_tree_shortcut)
        self.root.bind_all("<Control-s>", lambda _e: (self.save_current_file(), "break"))
        self.root.bind_all("<Control-o>", lambda _e: (self.open_files(), "break"))
        self.root.bind_all("<Control-z>", self.undo_text)
        self.root.bind_all("<Control-y>", self.redo_text)
        self.root.bind_all("<Control-Shift-Z>", self.redo_text)

    def _try_tkdnd(self) -> None:
        try:
            for tkdnd_dir in self._tkdnd_vendor_dirs():
                self.root.tk.call("lappend", "auto_path", str(tkdnd_dir))
            self.root.tk.call("package", "require", "tkdnd")
            self._register_drop_target(self.root)
        except Exception:
            pass
        if is_macos():
            self._install_macos_open_document_handler()

    def _tkdnd_vendor_dirs(self) -> list[Path]:
        base_dirs = [_VENDOR_DIR / "tkinterdnd2" / "tkdnd"]
        if TkinterDnD is not None:
            base_dirs.append(Path(TkinterDnD.__file__).resolve().parent / "tkdnd")

        try:
            tk_version = str(self.root.tk.call("info", "patchlevel"))
        except Exception:
            tk_version = ""

        names: list[str] = []
        machine = platform.machine()
        system = platform.system()
        if system == "Darwin" and machine == "arm64":
            if tk_version.startswith("9."):
                names.append("osx-arm64-tcl9")
            names.append("osx-arm64")
        elif system == "Darwin" and machine == "x86_64":
            names.append("osx-x64")
        elif system == "Linux" and machine == "aarch64":
            names.append("linux-arm64")
        elif system == "Linux" and machine == "x86_64":
            names.append("linux-x64")
        elif system == "Windows" and machine in {"AMD64", "x86_64"}:
            names.append("win-x64")
        elif system == "Windows" and machine == "ARM64":
            names.append("win-arm64")
        elif system == "Windows":
            names.append("win-x86")

        dirs: list[Path] = []
        for base_dir in base_dirs:
            for name in names:
                path = base_dir / name
                if path.exists() and path not in dirs:
                    dirs.append(path)
        return dirs

    def _register_drop_target(self, widget) -> None:
        try:
            self.root.tk.call("tkdnd::drop_target", "register", widget, "DND_Files")
            if hasattr(widget, "dnd_bind"):
                widget.dnd_bind("<<DropEnter>>", self._drop_accept, add="+")
                widget.dnd_bind("<<DropPosition>>", self._drop_accept, add="+")
                widget.dnd_bind("<<Drop>>", self._drop_files, add="+")
            else:
                command = self.root.register(self._drop_files_data)
                self.root.tk.call("bind", widget, "<<DropEnter>>", "copy")
                self.root.tk.call("bind", widget, "<<DropPosition>>", "copy")
                self.root.tk.call("bind", widget, "<<Drop>>", f"{command} %D")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._register_drop_target(child)

    def _drop_accept(self, _event=None) -> str:
        return "copy"

    def _install_macos_open_document_handler(self) -> None:
        try:
            self.root.createcommand("kindedit_open_documents", self._open_document_paths)
            self.root.tk.eval("proc ::tk::mac::OpenDocument {args} {kindedit_open_documents {*}$args}")
        except Exception:
            pass

    def _open_document_paths(self, *paths: str) -> None:
        self._open_dropped_paths([Path(path) for path in paths])

    def _drop_files(self, event) -> str:
        return self._drop_files_data(getattr(event, "data", ""))

    def _drop_files_data(self, data: str) -> str:
        paths = self._parse_drop_paths(data)
        if not paths:
            self.set_status("拖拽打开失败：未收到文件路径", error=True)
            return "copy"
        self._open_dropped_paths(paths)
        return "copy"

    def _parse_drop_paths(self, data: str) -> list[Path]:
        if not data:
            return []
        try:
            items = self.root.tk.splitlist(data)
        except Exception:
            items = data.splitlines() or [data]
        paths: list[Path] = []
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            if text.startswith("file://"):
                try:
                    from urllib.parse import unquote, urlparse

                    parsed = urlparse(text)
                    text = unquote(parsed.path)
                except Exception:
                    text = text[7:]
            paths.append(Path(text))
        return paths

    def _open_dropped_paths(self, paths: list[Path]) -> None:
        text_paths: list[Path] = []
        skipped = 0
        for path in paths:
            if self._is_text_file(path):
                text_paths.append(path)
            else:
                skipped += 1
        if text_paths:
            self.open_paths(text_paths)
        if skipped:
            self.set_status(f"已跳过 {skipped} 个非文本文件")

    def _is_text_file(self, path: Path) -> bool:
        try:
            if not path.is_file():
                return False
            with path.open("rb") as stream:
                sample = stream.read(8192)
        except OSError:
            return False
        return self._decode_text_bytes(sample) is not None

    def _read_text_file(self, path: Path) -> str:
        data = path.read_bytes()
        decoded = self._decode_text_bytes(data)
        if decoded is None:
            return data.decode("utf-8", errors="replace")
        return decoded

    def _decode_text_bytes(self, data: bytes) -> str | None:
        if not data:
            return ""
        encodings = ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "gb18030")
        for encoding in encodings:
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                continue
            if self._looks_like_text(text):
                return text
        return None

    def _looks_like_text(self, text: str) -> bool:
        if not text:
            return True
        allowed = {"\n", "\r", "\t", "\f", "\b"}
        control_count = 0
        checked = 0
        for char in text[:8192]:
            checked += 1
            if char in allowed:
                continue
            if ord(char) < 32:
                control_count += 1
        return checked > 0 and control_count / checked < 0.02

    def current_document_type(self) -> DocumentType:
        if not self.active_tab_id:
            return self.document_registry.get(None)
        return self.document_registry.get(self.current_tab().document_type)

    def active_tab_is_large(self) -> bool:
        tab = self.active_tab_or_none()
        return bool(tab and (tab.large_content or self.editor.content_is_large()))

    def effective_view_mode(self) -> str:
        if self.active_tab_is_large():
            return "text"
        return self.current_document_type().view_mode

    def _capture_active_editor_metadata(self, tab: TabState) -> None:
        if self.loading_text:
            return
        if self.editor.content_is_large():
            tab.large_content = True
            tab.content_loaded = True
            tab.content_size = self.editor.char_count()
            tab.content = ""
            return
        tab.content = self.editor.get()
        tab.content_size = len(tab.content)
        tab.large_content = is_large_text_size(tab.content_size)
        tab.content_loaded = True
        if not tab.large_content:
            tab.large_source_path = ""

    def _large_source_for_tab(self, tab: TabState) -> Path | None:
        for raw_path in (tab.large_source_path, tab.autosave_path if tab.dirty else "", tab.file_path, tab.autosave_path):
            if raw_path:
                path = Path(raw_path)
                if path.exists():
                    return path
        return None

    def _needs_large_snapshot_before_leave(self, tab: TabState) -> bool:
        return bool(tab.id == self.active_tab_id and tab.dirty and tab.content_loaded and self.editor.content_is_large())

    def _ensure_autosave_path(self, tab: TabState) -> None:
        if not tab.autosave_path:
            doc_type = self.document_registry.get(tab.document_type)
            tab.autosave_path = str(autosave_dir() / f"{tab.id}{doc_type.default_extension}")

    def _snapshot_active_large_tab(self, after_save=None) -> None:
        if self.saving_large_text or not self.active_tab_id:
            return
        tab = self.current_tab()
        self._ensure_autosave_path(tab)
        target = Path(tab.autosave_path)
        self.saving_large_text = True
        self.pending_after_large_save = after_save
        self.set_status("正在保存大文本快照...")

        def on_progress(done: int, total: int) -> None:
            self.status.set_status(f"正在保存大文本快照：{done:,}/{total:,} 字符", False)

        def on_complete(total: int) -> None:
            self.saving_large_text = False
            tab.large_content = True
            tab.content_loaded = False
            tab.large_source_path = str(target)
            tab.content_size = total
            tab.content = ""
            self.save_session()
            callback = self.pending_after_large_save
            self.pending_after_large_save = None
            self.set_status("大文本快照已保存")
            if callback:
                callback()

        def on_error(exc: Exception) -> None:
            self.saving_large_text = False
            self.pending_after_large_save = None
            self.set_status(f"大文本快照保存失败：{exc}", error=True)

        self.editor.save_to_path_chunked(target, on_progress=on_progress, on_complete=on_complete, on_error=on_error)

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
        if self.active_tab_is_large():
            tab.content = ""
            tab.large_content = True
            tab.content_loaded = True
            tab.content_size = self.editor.char_count()
        else:
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
        if self.active_tab_is_large():
            self.editor.clear_syntax()
            return
        doc_type = self.current_document_type()
        if not doc_type.parse_on_change:
            self.editor.clear_syntax()
            return
        tokens = self.syntax_registry.get(doc_type.type_id).highlight(self.editor.get())
        self.editor.apply_syntax_tokens(tokens)

    def apply_document_view_mode(self) -> None:
        mode = self.effective_view_mode()
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
        self.pending_auto_detect_after_change = (
            self.pending_auto_detect_after_change
            or self.selection_covers_all_text()
            or self.editor.is_blank_for_detection()
        )

    def before_text_paste(self, _event=None):
        self.mark_auto_detect_if_content_will_be_replaced()
        try:
            content = self.root.clipboard_get()
        except Exception:
            return None
        if is_large_text_size(len(content)):
            self._insert_large_clipboard_text(content)
            return "break"
        return None

    def _insert_large_clipboard_text(self, content: str) -> None:
        if not self.active_tab_id:
            return
        if self.saving_large_text:
            self.set_status("正在保存大文本，稍后再粘贴", error=True)
            return
        self.loading_text = True
        self.set_status("正在分块粘贴大文本...")

        def on_progress(done: int, total: int) -> None:
            self.status.set_status(f"正在分块粘贴大文本：{done:,}/{total:,} 字符", False)

        def on_complete(total: int) -> None:
            self.loading_text = False
            tab = self.current_tab()
            tab.large_content = True
            tab.content_loaded = True
            tab.content_size = self.editor.char_count()
            tab.content = ""
            self.editor.text.edit_modified(True)
            self.editor._modified()
            self.set_status(large_text_status(total))

        def on_error(exc: Exception) -> None:
            self.loading_text = False
            self.set_status(f"大文本粘贴失败：{exc}", error=True)

        self.editor.insert_text_chunked(content, replace_selection=True, on_progress=on_progress, on_complete=on_complete, on_error=on_error)

    def _load_tabs(self) -> None:
        for meta in self.config.tabs:
            tab = self._tab_from_meta(meta)
            if tab:
                self.tabs.append(tab)
        if not self.tabs:
            content = self.config.legacy_text_content or ""
            self.tabs.append(self._new_tab_state("未命名", content=content))
        self._sync_untitled_counter()
        active = self.config.active_tab_id if any(t.id == self.config.active_tab_id for t in self.tabs) else self.tabs[0].id
        self.switch_tab(active)

    def _tab_from_meta(self, meta: dict) -> TabState | None:
        try:
            tab_id = str(meta.get("id") or uuid.uuid4().hex)
            file_path = str(meta.get("file_path") or "")
            autosave_path = str(meta.get("autosave_path") or "")
            large_source_path = str(meta.get("large_source_path") or "")
            large_content = bool(meta.get("large_content"))
            content_loaded = not large_content
            content_size = int(meta.get("content_size") or 0)
            if meta.get("document_type"):
                doc_type = self.document_registry.get(meta.get("document_type"))
            elif file_path:
                doc_type = self.document_registry.detect(Path(file_path))
            else:
                doc_type = self.document_registry.get("text")
            title = str(meta.get("title") or (Path(file_path).name if file_path else "未命名"))
            content = ""
            source_candidates = [
                Path(large_source_path) if large_source_path else None,
                Path(file_path) if file_path else None,
                Path(autosave_path) if autosave_path else None,
            ]
            source = next((path for path in source_candidates if path and path.exists()), None)
            if source and (large_content or is_large_file(source)):
                large_content = True
                content_loaded = False
                large_source_path = str(source)
                try:
                    content_size = source.stat().st_size
                except OSError:
                    pass
            elif source:
                content = self._read_text_file(source)
                content_loaded = True
                content_size = len(content)
            return TabState(
                tab_id,
                title,
                file_path,
                autosave_path,
                bool(meta.get("dirty")),
                content,
                doc_type.type_id,
                bool(meta.get("document_type_locked")),
                large_content,
                content_loaded,
                large_source_path,
                content_size,
            )
        except Exception:
            return None

    def _new_tab_state(self, title: str | None = None, content: str = "", document_type: DocumentType | None = None) -> TabState:
        doc_type = document_type or self.document_registry.get("text")
        if title is None:
            title = self._next_untitled_title()
        tab_id = uuid.uuid4().hex
        auto = autosave_dir() / f"{tab_id}{doc_type.default_extension}"
        large_content = is_large_text_size(len(content))
        return TabState(tab_id, title, "", str(auto), False, "" if large_content else content, doc_type.type_id, False, large_content, not large_content, "", len(content))

    def _sync_untitled_counter(self) -> None:
        used_numbers = set()
        for tab in self.tabs:
            title = tab.title.removesuffix(" *")
            if title.startswith("未命名") and title[3:].isdigit():
                used_numbers.add(int(title[3:]))
        self.untitled_counter = 1
        while self.untitled_counter in used_numbers:
            self.untitled_counter += 1

    def _next_untitled_title(self) -> str:
        used_titles = {tab.title.removesuffix(" *") for tab in self.tabs}
        while True:
            title = f"未命名{self.untitled_counter}"
            self.untitled_counter += 1
            if title not in used_titles:
                return title

    def current_tab(self) -> TabState:
        return next(t for t in self.tabs if t.id == self.active_tab_id)

    def active_tab_or_none(self) -> TabState | None:
        if not self.active_tab_id:
            return None
        return next((t for t in self.tabs if t.id == self.active_tab_id), None)

    def refresh_tabs(self) -> None:
        self.draw_tabs()

    def draw_tabs(self) -> None:
        self._hide_tab_tooltip()
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
            display_title = self._truncate_tab_title(title)
            title_w = self.tab_font.measure(display_title)
            tab_w = max(116, min(240, title_w + 48))
            bg = self.palette["panel"] if selected else self.palette["tab_inactive"]
            fg = self.palette["text"] if selected else self.palette["muted"]
            self.tab_bar.create_rectangle(x, y, x + tab_w, y + tab_h, fill=bg, outline="")
            self.tab_bar.create_text(x + 12, y + tab_h // 2, text=display_title, anchor="w", fill=fg, font=self.tab_font)
            close_x1 = x + tab_w - 32
            self.tab_bar.create_text(close_x1 + 14, y + tab_h // 2, text="×", anchor="center", fill=self.palette["muted"], font=self.tab_font)
            if selected:
                self.tab_bar.create_rectangle(x, y + tab_h - 2, x + tab_w, y + tab_h, fill=self.palette["accent"], outline="")
            self.tab_hotspots.append((x, y, close_x1, y + tab_h, "select", tab.id, title))
            self.tab_hotspots.append((close_x1, y, x + tab_w, y + tab_h, "close", tab.id, title))
            x += tab_w + 6
        add_w = 40
        self.tab_bar.create_rectangle(x, y, x + add_w, y + tab_h, fill=self.palette["panel2"], outline="")
        self.tab_bar.create_text(x + add_w // 2, y + tab_h // 2, text="+", anchor="center", fill=self.palette["accent"], font=self.tab_font)
        self.tab_hotspots.append((x, y, x + add_w, y + tab_h, "new", "", ""))

    def _truncate_tab_title(self, text: str) -> str:
        if len(text) <= TAB_TITLE_MAX_CHARS:
            return text
        return text[:TAB_TITLE_PREFIX_CHARS] + "..."

    def _tab_click(self, event) -> None:
        for x1, y1, x2, y2, action, tab_id, _title in self.tab_hotspots:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if action == "select":
                    self.switch_tab(tab_id)
                elif action == "close":
                    self.close_tab(tab_id)
                elif action == "new":
                    self.new_tab()
                return

    def _confirm_discard_or_save_tab(self, tab: TabState) -> bool:
        if not tab.dirty:
            return True
        result = self._ask_unsaved_tab_action(tab)
        if result == "cancel":
            return False
        if result == "discard":
            tab.dirty = False
            return True
        if tab.id != self.active_tab_id:
            self.switch_tab(tab.id)
        if tab.id == self.active_tab_id:
            return self.save_current_file()
        return False

    def _ask_unsaved_tab_action(self, tab: TabState) -> str:
        dialog = tk.Toplevel(self.root)
        dialog.title("未保存的更改")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(bg=self.palette["panel"])
        result = {"value": "cancel"}

        def choose(value: str) -> None:
            result["value"] = value
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        tk.Label(
            dialog,
            text=f"页签“{tab.title}”有未保存的更改，是否保存？",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=self.menu_font,
            padx=18,
            pady=16,
        ).pack(fill="x")
        buttons = tk.Frame(dialog, bg=self.palette["panel"])
        buttons.pack(fill="x", padx=18, pady=(0, 16))
        for label, value in (("保存", "save"), ("不保存", "discard"), ("取消", "cancel")):
            button = tk.Button(buttons, text=label, width=8, command=lambda v=value: choose(v))
            button.pack(side="right", padx=(8, 0))
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()
        self.root.wait_window(dialog)
        return result["value"]

    def _confirm_all_dirty_tabs(self) -> bool:
        for tab in list(self.tabs):
            if tab.dirty and not self._confirm_discard_or_save_tab(tab):
                return False
        return True

    def _tab_motion(self, event) -> None:
        self.tab_bar.configure(cursor="")
        hovered = None
        for x1, y1, x2, y2, action, tab_id, title in self.tab_hotspots:
            if action != "select":
                continue
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                hovered = (tab_id, title)
                break
        if hovered:
            tab_id, title = hovered
            self._show_tab_tooltip(tab_id, title, event.x_root + 12, event.y_root + 18)
        else:
            self._hide_tab_tooltip()

    def _tab_leave(self, _event=None) -> None:
        self.tab_bar.configure(cursor="")
        self._hide_tab_tooltip()

    def _show_tab_tooltip(self, tab_id: str, title: str, x: int, y: int) -> None:
        if self.tab_tooltip is not None and self.tab_tooltip.winfo_exists() and self.tab_tooltip_tab_id == tab_id:
            self.tab_tooltip.geometry(f"+{x}+{y}")
            return
        self._hide_tab_tooltip()
        tooltip = tk.Toplevel(self.root)
        tooltip.wm_overrideredirect(True)
        tooltip.configure(bg=self.palette["border"])
        label = tk.Label(
            tooltip,
            text=title,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            bd=0,
            padx=8,
            pady=4,
            font=self.menu_font,
        )
        label.pack()
        tooltip.geometry(f"+{x}+{y}")
        self.tab_tooltip = tooltip
        self.tab_tooltip_tab_id = tab_id

    def _hide_tab_tooltip(self) -> None:
        if self.tab_tooltip is not None:
            try:
                self.tab_tooltip.destroy()
            except tk.TclError:
                pass
        self.tab_tooltip = None
        self.tab_tooltip_tab_id = None

    def switch_tab(self, tab_id: str) -> None:
        if self.saving_large_text:
            return
        previous_tab = self.active_tab_or_none()
        if previous_tab and previous_tab.id != tab_id:
            if self._needs_large_snapshot_before_leave(previous_tab):
                self._snapshot_active_large_tab(lambda target=tab_id: self.switch_tab(target))
                return
            if self.editor.content_is_large():
                previous_tab.large_content = True
                previous_tab.content_loaded = False
                previous_tab.content_size = self.editor.char_count()
                previous_tab.content = ""
                if not previous_tab.large_source_path:
                    previous_tab.large_source_path = previous_tab.file_path or previous_tab.autosave_path
            else:
                self._capture_active_editor_metadata(previous_tab)
        if not any(t.id == tab_id for t in self.tabs):
            return
        self.active_tab_id = tab_id
        tab = self.current_tab()
        self._load_tab_into_editor(tab)
        self.refresh_tabs()
        self.update_title()
        self.save_session()
        self.editor.request_text_cursor_refresh()

    def _load_tab_into_editor(self, tab: TabState) -> None:
        self.editor.cancel_bulk_operation()
        self.loading_text = True
        self.apply_document_view_mode()
        source = self._large_source_for_tab(tab) if tab.large_content else None
        if source:
            self.current_tree = None
            self.position_index = EmptyPositionIndex()
            self.tree.set_tree(None)
            self.preview.clear()
            self.editor.clear_syntax()
            self.set_status(f"正在分块打开：{source.name}")

            def on_progress(chars: int) -> None:
                self.status.set_status(f"正在分块打开：{source.name}，已加载 {chars:,} 字符", False)

            def on_complete(chars: int) -> None:
                self.loading_text = False
                tab.large_content = True
                tab.content_loaded = True
                tab.large_source_path = str(source)
                tab.content_size = chars
                tab.content = ""
                self.apply_document_view_mode()
                self.parse_now()
                self.save_session()
                self.editor.request_text_cursor_refresh()

            def on_error(exc: Exception) -> None:
                self.loading_text = False
                self.editor.set("")
                tab.large_content = False
                tab.content_loaded = True
                tab.large_source_path = ""
                self.set_status(f"打开失败：{exc}", error=True)

            self.editor.load_file_chunked(source, on_progress=on_progress, on_complete=on_complete, on_error=on_error)
            return
        self.editor.set(tab.content)
        self.loading_text = False
        self.apply_document_view_mode()
        self.parse_now()

    def new_tab(self) -> None:
        tab = self._new_tab_state()
        self.tabs.append(tab)
        self.switch_tab(tab.id)
        self.set_status("已新增页签")

    def close_tab(self, tab_id: str) -> None:
        if not any(t.id == tab_id for t in self.tabs):
            self.refresh_tabs()
            return
        closing = next(t for t in self.tabs if t.id == tab_id)
        if not self._confirm_discard_or_save_tab(closing):
            return
        if closing.id == self.active_tab_id and self._needs_large_snapshot_before_leave(closing):
            self._snapshot_active_large_tab(lambda target=tab_id: self.close_tab(target))
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
            tab.large_content = False
            tab.content_loaded = True
            tab.large_source_path = ""
            tab.content_size = 0
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
            if self.editor.content_is_large():
                closing.large_content = True
                closing.content_loaded = False
                closing.content_size = self.editor.char_count()
                closing.content = ""
            else:
                self._capture_active_editor_metadata(closing)
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
        editor_is_large = self.editor.content_is_large()
        if editor_is_large:
            current_content = ""
            should_auto_detect, force_auto_detect = False, False
            tab.large_content = True
            tab.content_loaded = True
            tab.content_size = self.editor.char_count()
        else:
            previous_content = tab.content
            current_content = self.editor.get()
            should_auto_detect, force_auto_detect = self.should_detect_after_content_change(previous_content, current_content)
            tab.large_content = is_large_text_size(len(current_content))
            tab.content_loaded = True
            tab.content_size = len(current_content)
        self.pending_auto_detect_after_change = False
        tab.content = current_content
        tab.dirty = True
        self.refresh_tabs()
        self.update_title()
        if self.parse_job:
            self.root.after_cancel(self.parse_job)
        if self.autosave_job:
            self.root.after_cancel(self.autosave_job)
        if editor_is_large:
            self.current_tree = None
            self.position_index = EmptyPositionIndex()
            self.tree.set_tree(None)
            self.preview.clear()
            self.editor.clear_syntax()
            self.set_status(large_text_status(tab.content_size))
        elif self.current_document_type().parse_on_change or should_auto_detect:
            self.parse_job = self.root.after(
                PARSE_DELAY_MS,
                lambda detect=should_auto_detect, force=force_auto_detect: self.parse_now(auto_detect=detect, force_auto_detect=force),
            )
        delay = LARGE_TEXT_AUTOSAVE_DELAY_MS if editor_is_large else AUTOSAVE_DELAY_MS
        self.autosave_job = self.root.after(delay, self.autosave_current)

    def parse_now(self, auto_detect: bool = False, force_auto_detect: bool = False) -> None:
        self.parse_job = None
        if self.active_tab_id:
            tab = self.current_tab()
            if self.active_tab_is_large():
                if tab.content_loaded:
                    tab.content_size = self.editor.char_count()
                tab.large_content = True
                tab.content = ""
                self.current_tree = None
                self.position_index = EmptyPositionIndex()
                self.tree.set_tree(None)
                self.preview.clear()
                self.editor.clear_syntax()
                self.set_status(large_text_status(tab.content_size), False)
                return
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
        if self.active_tab_is_large():
            if tab.dirty and tab.content_loaded and not self.saving_large_text:
                self._snapshot_active_large_tab()
            else:
                self.save_session()
            return
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
        if self.active_tab_id and not self.loading_text:
            try:
                tab = self.current_tab()
                if not (tab.large_content and not tab.content_loaded):
                    self._capture_active_editor_metadata(tab)
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
                    "large_content": tab.large_content,
                    "content_loaded": tab.content_loaded,
                    "large_source_path": tab.large_source_path,
                    "content_size": tab.content_size,
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

    def show_about(self) -> None:
        messagebox.showinfo(
            "关于",
            f"{APP_VERSION_TEXT}\n{LATEST_VERSION_TEXT}: {LATEST_VERSION_URL}\n{BRAND_TEXT}",
            parent=self.root,
        )

    def set_occurrence_ignore_case(self, enabled: bool) -> None:
        self.config.occurrence_ignore_case = bool(enabled)
        self.editor.set_occurrence_ignore_case(self.config.occurrence_ignore_case)
        self.save_session()

    def set_sql_uppercase_keywords(self, enabled: bool) -> None:
        self.config.sql_uppercase_keywords = bool(enabled)
        self.save_session()

    def update_title(self) -> None:
        if not self.active_tab_id:
            self.root.title(APP_TITLE)
            return
        title = self.current_tab().title
        self.root.title(f"{APP_TITLE} - {title}" if title else APP_TITLE)

    def apply_theme(self) -> None:
        self.palette, effective_dark = effective_palette(self.config.theme)
        self.effective_dark = effective_dark
        p = self.palette
        self.root.configure(bg=p["bg"])
        self.toolbar.configure(bg=p.get("toolbar", p["panel"]))
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
        self._sync_tab_font()
        self.editor.set_occurrence_ignore_case(self.config.occurrence_ignore_case)
        self.tree.set_font_size(self.config.tree_font_size)
        self.preview.set_font_size(self.config.tree_font_size)
        self.apply_syntax_highlighting()
        self._apply_toolbar_palette()
        self.refresh_tabs()
        if self.settings_dialog is not None and self.settings_dialog.winfo_exists():
            self.settings_dialog.apply_palette(p, effective_dark)
        apply_titlebar_theme(self.root, effective_dark)

    def _apply_toolbar_palette(self) -> None:
        self.draw_toolbar()
        self.draw_tabs()

    def _sync_tab_font(self) -> None:
        self.tab_font.configure(size=TAB_TITLE_FONT_SIZE)

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
        self.config.sql_uppercase_keywords = defaults.sql_uppercase_keywords
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
        self._sync_tab_font()
        self.refresh_tabs()
        self.save_session()

    def adjust_tree_font(self, delta: int) -> None:
        self.config.tree_font_size = clamp_font_size(self.config.tree_font_size + delta)
        self.tree.set_font_size(self.config.tree_font_size)
        self.save_session()

    def show_text_menu(self, event):
        doc_type = self.current_document_type()
        large_mode = self.active_tab_is_large()
        sync_label = "✓ 同步" if self.config.sync_display else "同步"
        sync_enabled = self.effective_view_mode() == "split"
        items = [
            ("格式化", self.format_text, doc_type.supports_format and not large_mode),
            ("压缩", self.compact_text, doc_type.supports_compact and not large_mode),
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
        if self.active_tab_is_large():
            self.set_status("大文本模式下不执行全量格式化", error=True)
            return
        doc_type = self.current_document_type()
        try:
            if doc_type.type_id == "sql":
                self._format_sql_text()
                return
            content = doc_type.format_text(self.editor.get())
        except Exception as exc:
            self.set_status(f"格式化失败：{exc}", error=True)
            return
        self.editor.replace_all(content)

    def _format_sql_text(self) -> None:
        doc_type = self.current_document_type()
        uppercase_keywords = self.config.sql_uppercase_keywords
        try:
            start = self.editor.text.index("sel.first")
            end = self.editor.text.index("sel.last")
            selected = self.editor.text.get(start, end)
        except tk.TclError:
            start = end = ""
            selected = ""
        if selected:
            content = doc_type.format_text(selected, uppercase_keywords=uppercase_keywords)
            self.editor.text.edit_separator()
            self.editor.text.delete(start, end)
            self.editor.text.insert(start, content)
            self.editor.text.tag_remove("sel", "1.0", "end")
            self.editor.text.tag_add("sel", start, f"{start}+{len(content)}c")
            self.editor.text.mark_set("insert", f"{start}+{len(content)}c")
            self.editor.text.edit_separator()
            self.editor.text.edit_modified(True)
            self.editor._modified()
            return
        content = doc_type.format_text(self.editor.get(), uppercase_keywords=uppercase_keywords)
        self.editor.replace_all(content)

    def undo_text(self, _event=None) -> str:
        try:
            self.editor.text.edit_undo()
        except tk.TclError:
            return "break"
        self.editor._modified()
        self.on_cursor_move()
        return "break"

    def redo_text(self, _event=None) -> str:
        try:
            self.editor.text.edit_redo()
        except tk.TclError:
            return "break"
        self.editor._modified()
        self.on_cursor_move()
        return "break"

    def compact_text(self) -> None:
        if self.active_tab_is_large():
            self.set_status("大文本模式下不执行全量压缩", error=True)
            return
        try:
            content = self.current_document_type().compact_text(self.editor.get())
        except Exception as exc:
            self.set_status(f"压缩失败：{exc}", error=True)
            return
        self.editor.replace_all(content)

    def copy_text(self) -> None:
        try:
            selected_chars = self.editor.selection_char_count()
            if is_large_text_size(selected_chars):
                self.set_status("选中文本过大，已取消复制以避免卡顿", error=True)
                return
            content = self.editor.text.get("sel.first", "sel.last")
        except tk.TclError:
            if self.active_tab_is_large():
                self.set_status("大文本模式下请先选择较小范围再复制", error=True)
                return
            content = self.editor.get()
        self.clipboard_set(content)

    def paste_text(self) -> None:
        try:
            content = self.root.clipboard_get()
        except Exception:
            return
        self.mark_auto_detect_if_content_will_be_replaced()
        if is_large_text_size(len(content)):
            self._insert_large_clipboard_text(content)
            return
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
            tab.large_content = False
            tab.content_loaded = True
            tab.large_source_path = ""
            tab.content_size = 0
        self.parse_now()

    def show_tree_menu(self, x: int, y: int, node: TreeNode | None) -> None:
        root = self.current_tree
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
            filetypes=self.document_registry.text_filetypes(),
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
                if is_large_file(file_path):
                    tab = self._new_tab_state(file_path.name, "", doc_type)
                    tab.large_content = True
                    tab.content_loaded = False
                    tab.large_source_path = resolved
                    try:
                        tab.content_size = file_path.stat().st_size
                    except OSError:
                        tab.content_size = 0
                else:
                    content = self._read_text_file(file_path)
                    tab = self._new_tab_state(file_path.name, content, doc_type)
                tab.file_path = resolved
                tab.dirty = False
                self.tabs.append(tab)
                self.switch_tab(tab.id)
                self.set_status(f"已打开：{file_path.name}")
            except Exception as exc:
                self.set_status(f"打开失败：{exc}", error=True)

    def save_current_file(self) -> bool:
        if not self.active_tab_id:
            return False
        tab = self.current_tab()
        doc_type = self.current_document_type()
        path = tab.file_path
        if not path:
            selected = filedialog.asksaveasfilename(
                title="保存文件",
                defaultextension=doc_type.default_extension,
                filetypes=self.document_registry.save_filetypes(doc_type.type_id),
            )
            if not selected:
                return False
            path = str(self._path_with_default_extension(Path(selected), doc_type))
        try:
            if self.active_tab_is_large():
                self._save_large_current_file(Path(path))
                return False
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
            return True
        except Exception as exc:
            self.set_status(f"保存失败：{exc}", error=True)
            return False

    def _save_large_current_file(self, path: Path) -> None:
        if self.saving_large_text:
            return
        tab = self.current_tab()
        self.saving_large_text = True
        self.set_status("正在分块保存大文本...")

        def on_progress(done: int, total: int) -> None:
            self.status.set_status(f"正在分块保存：{done:,}/{total:,} 字符", False)

        def on_complete(total: int) -> None:
            self.saving_large_text = False
            saved_path = path.resolve()
            tab.file_path = str(saved_path)
            tab.document_type = self.document_registry.detect(saved_path).type_id
            tab.title = saved_path.name
            tab.dirty = False
            tab.content = ""
            tab.large_content = True
            tab.content_loaded = True
            tab.large_source_path = str(saved_path)
            tab.content_size = total
            if tab.autosave_path and Path(tab.autosave_path).exists() and Path(tab.autosave_path) != saved_path:
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

        def on_error(exc: Exception) -> None:
            self.saving_large_text = False
            self.set_status(f"保存失败：{exc}", error=True)

        self.editor.save_to_path_chunked(path, on_progress=on_progress, on_complete=on_complete, on_error=on_error)

    def _path_with_default_extension(self, path: Path, doc_type: DocumentType) -> Path:
        if path.suffix:
            return path
        return path.with_suffix(doc_type.default_extension)

    def close(self) -> None:
        if not self._confirm_all_dirty_tabs():
            return
        tab = self.active_tab_or_none()
        if tab and self._needs_large_snapshot_before_leave(tab):
            self._snapshot_active_large_tab(self._finish_close)
            return
        self._finish_close()

    def _finish_close(self) -> None:
        self.autosave_current()
        self.save_session()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
