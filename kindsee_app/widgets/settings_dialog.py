from __future__ import annotations

import tkinter as tk


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
        self._build()
        self.apply_palette(app.palette)
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
        self.theme_button = tk.Button(self.container, text="切换明暗", command=self._toggle_theme, width=12)
        self.theme_button.grid(row=3, column=0, sticky="w", pady=(0, 12))
        self.reset_button = tk.Button(self.container, text="重置设置", command=self._reset_settings, width=12)
        self.reset_button.grid(row=3, column=1, sticky="e", padx=(24, 0), pady=(0, 12))
        self.close_button = tk.Button(self.container, text="关闭", command=self.destroy, width=10)
        self.close_button.grid(row=4, column=1, sticky="e", padx=(24, 0))
        self._update_theme_label()

    def apply_palette(self, palette: dict) -> None:
        self.palette = palette
        self.configure(bg=palette["panel"])
        self.container.configure(bg=palette["panel"])
        self.title_label.configure(bg=palette["panel"], fg=palette["text"])
        self.theme_label.configure(bg=palette["panel"], fg=palette["text"])
        self.ignore_case.configure(
            bg=palette["panel"],
            fg=palette["text"],
            activebackground=palette["panel"],
            activeforeground=palette["text"],
            selectcolor=palette["input"],
        )
        for button in (self.theme_button, self.reset_button, self.close_button):
            button.configure(
                bg=palette["panel2"],
                fg=palette["text"],
                activebackground=palette["hover"],
                activeforeground=palette["text"],
                relief="flat",
                bd=1,
                highlightthickness=1,
                highlightbackground=palette["border"],
            )

    def _toggle_ignore_case(self) -> None:
        self.app.set_occurrence_ignore_case(self.ignore_case_var.get())

    def _toggle_theme(self) -> None:
        self.app.toggle_theme()
        self.apply_palette(self.app.palette)
        self._update_theme_label()

    def _reset_settings(self) -> None:
        self.app.reset_settings()
        self.ignore_case_var.set(self.app.config.occurrence_ignore_case)
        self.apply_palette(self.app.palette)
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
