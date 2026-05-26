from __future__ import annotations

import ctypes
import subprocess
import sys


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def text_edit_cursor_name() -> str:
    if is_macos():
        return "ibeam"
    return "xterm"


def is_dark_mode() -> bool:
    try:
        if is_macos():
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
            )
            return out.stdout.strip().lower() == "dark"
        if is_windows():
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return int(value) == 0
    except Exception:
        return False
    return False


def apply_titlebar_theme(root, dark: bool) -> None:
    try:
        if is_windows():
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        elif is_macos():
            root.update_idletasks()
            window = str(root)
            appearance = "darkaqua" if dark else "aqua"
            try:
                root.tk.call("tk::unsupported::MacWindowStyle", "appearance", window, appearance)
            except Exception:
                pass
    except Exception:
        pass
