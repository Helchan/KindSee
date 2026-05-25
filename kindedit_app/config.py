from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .constants import APP_TITLE, LEGACY_APP_TITLES, MAX_FONT_SIZE, MIN_FONT_SIZE
from .platforms import is_macos, is_windows


def clamp_font_size(value: int) -> int:
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, int(value)))


def default_tree_font_size() -> int:
    return 10


def default_text_font_size() -> int:
    return 10


def _app_config_dir(app_title: str) -> Path:
    if is_windows():
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        return Path(base, app_title) if base else Path.home() / app_title
    if is_macos():
        return Path.home() / "Library" / "Application Support" / app_title
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / app_title


def config_dir() -> Path:
    return _app_config_dir(APP_TITLE)


def legacy_config_dirs() -> list[Path]:
    return [_app_config_dir(title) for title in LEGACY_APP_TITLES]


def settings_path() -> Path:
    return config_dir() / "settings.json"


def legacy_settings_path() -> Path:
    for legacy_dir in legacy_config_dirs():
        path = legacy_dir / "settings.json"
        if path.exists():
            return path
    return legacy_config_dirs()[0] / "settings.json"


def autosave_dir() -> Path:
    return config_dir() / "tabs"


@dataclass
class AppConfig:
    tree_font_size: int = field(default_factory=default_tree_font_size)
    text_font_size: int = field(default_factory=default_text_font_size)
    theme: str = "system"
    sync_display: bool = True
    occurrence_ignore_case: bool = False
    tabs: list[dict] = field(default_factory=list)
    active_tab_id: str | None = None
    legacy_text_content: str = ""


def load_config() -> AppConfig:
    path = settings_path()
    if not path.exists():
        path = legacy_settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return AppConfig()

    cfg = AppConfig()
    cfg.tree_font_size = clamp_font_size(data.get("tree_font_size", cfg.tree_font_size))
    cfg.text_font_size = clamp_font_size(data.get("text_font_size", cfg.text_font_size))
    if is_macos():
        if cfg.tree_font_size == 13:
            cfg.tree_font_size = default_tree_font_size()
        if cfg.text_font_size == 11:
            cfg.text_font_size = default_text_font_size()
    elif is_windows() and cfg.text_font_size == 9:
        cfg.text_font_size = default_text_font_size()
    cfg.theme = data.get("theme") if data.get("theme") in {"system", "light", "dark"} else "system"
    cfg.sync_display = bool(data.get("sync_display", True))
    cfg.occurrence_ignore_case = bool(data.get("occurrence_ignore_case", False))
    cfg.tabs = data.get("tabs") if isinstance(data.get("tabs"), list) else []
    cfg.active_tab_id = data.get("active_tab_id") if isinstance(data.get("active_tab_id"), str) else None
    cfg.legacy_text_content = data.get("text_content", "") if isinstance(data.get("text_content"), str) else ""
    return cfg


def save_config(cfg: AppConfig) -> None:
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        payload = {
            "tree_font_size": clamp_font_size(cfg.tree_font_size),
            "text_font_size": clamp_font_size(cfg.text_font_size),
            "theme": cfg.theme,
            "sync_display": bool(cfg.sync_display),
            "occurrence_ignore_case": bool(cfg.occurrence_ignore_case),
            "tabs": cfg.tabs,
            "active_tab_id": cfg.active_tab_id,
        }
        settings_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def clear_persistence() -> None:
    try:
        if settings_path().exists():
            settings_path().unlink()
    except Exception:
        pass
    try:
        if autosave_dir().exists():
            shutil.rmtree(autosave_dir())
    except Exception:
        pass
    try:
        if legacy_settings_path().exists():
            legacy_settings_path().unlink()
    except Exception:
        pass
    try:
        for legacy_dir in legacy_config_dirs():
            legacy_autosave = legacy_dir / "tabs"
            if legacy_autosave.exists():
                shutil.rmtree(legacy_autosave)
    except Exception:
        pass
