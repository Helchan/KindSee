from __future__ import annotations

from pathlib import Path


# 200M 是明确目标场景；这里用更早的阈值进入保护模式，避免在接近
# 目标规模前 UI 已经因为全量字符串复制、解析或语法渲染出现明显停顿。
LARGE_TEXT_CHAR_THRESHOLD = 5_000_000
LARGE_TEXT_FILE_BYTES = 20 * 1024 * 1024
LARGE_TEXT_CHUNK_CHARS = 256_000
LARGE_TEXT_TIME_BUDGET_MS = 12
LARGE_TEXT_AUTOSAVE_DELAY_MS = 2_000
LARGE_TEXT_SAMPLE_CHARS = 500_000


def is_large_text_size(char_count: int) -> bool:
    return char_count >= LARGE_TEXT_CHAR_THRESHOLD


def is_large_file(path: Path) -> bool:
    try:
        return path.stat().st_size >= LARGE_TEXT_FILE_BYTES
    except OSError:
        return False


def large_text_status(char_count: int | None = None) -> str:
    if char_count is None:
        return "大文本模式：已暂停全量解析和语法渲染，编辑、滚动和保存使用分块流程"
    return f"大文本模式：约 {char_count:,} 字符，已暂停全量解析和语法渲染"
