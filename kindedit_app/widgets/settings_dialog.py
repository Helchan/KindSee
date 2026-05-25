from __future__ import annotations

import tkinter as tk

from ..platforms import apply_titlebar_theme


class DialogButton(tk.Frame):
    def __init__(self, master, text: str, command, width: int = 96):
        super().__init__(master, bd=0, highlightthickness=1)
        self.command = command
        self.palette = {}
        self.hovered = False
        self.label = tk.Label(self, text=text, bd=0, padx=12, pady=5, anchor="center")
        self.label.pack(fill="both", expand=True)
        self.configure(width=width, height=28)
        self.pack_propagate(False)
        for widget in (self, self.label):
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            widget.bind("<Button-1>", self._click)

    def set_palette(self, palette: dict) -> None:
        self.palette = palette
        self._apply()

    def _apply(self) -> None:
        if not self.palette:
            return
        bg = self.palette["hover"] if self.hovered else self.palette["panel2"]
        fg = self.palette["text"]
        self.configure(bg=bg, highlightbackground=self.palette["border"])
        self.label.configure(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)

    def _enter(self, _event=None) -> None:
        self.hovered = True
        self._apply()

    def _leave(self, _event=None) -> None:
        self.hovered = False
        self._apply()

    def _click(self, _event=None) -> str:
        self.command()
        return "break"


class SettingsDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.palette = app.palette
        self.title("设置")
        self.resizable(False, False)
        self.transient(app.root)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.ignore_case_var = tk.BooleanVar(value=app.config.occurrence_ignore_case)
        self.theme_var = tk.StringVar(value="dark" if app.effective_dark else "light")
        self._build()
        self.apply_palette(app.palette, app.effective_dark)
        self._center()
        self.focus_force()

    def _build(self) -> None:
        self.container = tk.Frame(self, padx=18, pady=16, bd=0, highlightthickness=0)
        self.container.grid(row=0, column=0, sticky="nsew")
        self.title_label = tk.Label(self.container, text="设置", font=("", 14, "bold"), anchor="w")
        self.title_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.ignore_case = tk.Checkbutton(
            self.container,
            text="选中高亮忽略大小写",
            variable=self.ignore_case_var,
            command=self._toggle_ignore_case,
            anchor="w",
            padx=0,
        )
        self.ignore_case.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.theme_label = tk.Label(self.container, text="", anchor="w")
        self.theme_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.theme_group = tk.Frame(self.container, bd=0, highlightthickness=0)
        self.theme_group.grid(row=3, column=0, sticky="w", pady=(0, 12))
        self.theme_light = tk.Radiobutton(
            self.theme_group,
            text="明",
            value="light",
            variable=self.theme_var,
            command=self._select_theme,
            padx=0,
            anchor="w",
        )
        self.theme_light.grid(row=0, column=0, sticky="w")
        self.theme_dark = tk.Radiobutton(
            self.theme_group,
            text="暗",
            value="dark",
            variable=self.theme_var,
            command=self._select_theme,
            padx=0,
            anchor="w",
        )
        self.theme_dark.grid(row=0, column=1, sticky="w", padx=(18, 0))
        self.reset_button = DialogButton(self.container, text="重置设置", command=self._reset_settings)
        self.reset_button.grid(row=3, column=1, sticky="e", padx=(24, 0), pady=(0, 12))
        self.close_button = DialogButton(self.container, text="关闭", command=self.destroy, width=84)
        self.close_button.grid(row=4, column=1, sticky="e", padx=(24, 0))
        self._update_theme_label()

    def apply_palette(self, palette: dict, dark: bool | None = None) -> None:
        self.palette = palette
        self.configure(bg=palette["panel"])
        self.container.configure(bg=palette["panel"])
        self.title_label.configure(bg=palette["panel"], fg=palette["text"])
        self.theme_label.configure(bg=palette["panel"], fg=palette["text"])
        self.theme_group.configure(bg=palette["panel"])
        self.ignore_case.configure(
            bg=palette["panel"],
            fg=palette["text"],
            activebackground=palette["panel"],
            activeforeground=palette["text"],
            selectcolor=palette["input"],
        )
        self.theme_var.set("dark" if dark else "light")
        for radio in (self.theme_light, self.theme_dark):
            radio.configure(
                bg=palette["panel"],
                fg=palette["text"],
                activebackground=palette["panel"],
                activeforeground=palette["text"],
                selectcolor=palette["input"],
                highlightthickness=0,
            )
        for button in (self.reset_button, self.close_button):
            button.set_palette(palette)
        if dark is not None:
            apply_titlebar_theme(self, dark)

    def _toggle_ignore_case(self) -> None:
        self.app.set_occurrence_ignore_case(self.ignore_case_var.get())

    def _select_theme(self) -> None:
        selected = self.theme_var.get()
        if selected not in {"light", "dark"}:
            return
        if self.app.config.theme != selected:
            self.app.config.theme = selected
            self.app.apply_theme()
            self.app.save_session()
        self.apply_palette(self.app.palette, self.app.effective_dark)
        self._update_theme_label()

    def _reset_settings(self) -> None:
        self.app.reset_settings()
        self.ignore_case_var.set(self.app.config.occurrence_ignore_case)
        self.apply_palette(self.app.palette, self.app.effective_dark)
        self._update_theme_label()

    def _update_theme_label(self) -> None:
        names = {"system": "跟随系统", "light": "明亮", "dark": "暗色"}
        self.theme_label.configure(text=f"当前主题：{names.get(self.app.config.theme, self.app.config.theme)}")

    def _center(self) -> None:
        self.update_idletasks()
        parent_x = self.app.root.winfo_rootx()
        parent_y = self.app.root.winfo_rooty()
        parent_w = self.app.root.winfo_width()
        parent_h = self.app.root.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        x = parent_x + max(0, (parent_w - w) // 2)
        y = parent_y + max(0, (parent_h - h) // 2)
        self.geometry(f"+{x}+{y}")
