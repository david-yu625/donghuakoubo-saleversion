"""Chinese-friendly text measurement and fit decisions."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .models import TextMeasure, Theme


COMMON_FONTS = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)


@lru_cache(maxsize=128)
def _resolve_font_cached(font_path: str, font_size: int):
    """Load a font once per path/size pair during a process run."""
    candidates = [font_path] if font_path else []
    candidates.extend(COMMON_FONTS)
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        try:
            return ImageFont.truetype(candidate, font_size)
        except OSError:
            continue
    return ImageFont.load_default()


def resolve_font(font_path: str | None, font_size: int):
    return _resolve_font_cached(font_path or "", font_size)


def text_width(text: str, font) -> int:
    if not text:
        return 0
    if hasattr(font, "getlength"):
        return round(font.getlength(text))
    box = font.getbbox(text)
    return box[2] - box[0]


def wrap_text(text: str, font, max_width: int) -> tuple[str, ...]:
    if not text:
        return ()
    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + char
        if current and text_width(candidate, font) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return tuple(lines)


def measure_text(text: str, font_size: int, max_width: int, theme: Theme) -> TextMeasure:
    font = resolve_font(theme.font_path, font_size)
    lines = wrap_text(text, font, max_width)
    line_height = max(font_size, round(font_size * theme.line_height))
    width = max((text_width(line, font) for line in lines), default=0)
    return TextMeasure(text, lines, width, line_height * len(lines), font_size)


def fit_text(
    text: str,
    *,
    max_width: int,
    max_height: int,
    initial_size: int,
    min_size: int,
    max_lines: int,
    theme: Theme,
) -> tuple[TextMeasure, str | None]:
    for size in range(initial_size, min_size - 1, -2):
        measured = measure_text(text, size, max_width, theme)
        if len(measured.lines) <= max_lines and measured.height <= max_height:
            return measured, None
    measured = measure_text(text, min_size, max_width, theme)
    if len(measured.lines) <= max_lines:
        return measured, "字号已降至最小值"
    clipped_lines = measured.lines[:max_lines]
    clipped = "".join(clipped_lines).rstrip("，。！？；、") + "…"
    clipped_measure = measure_text(clipped, min_size, max_width, theme)
    return clipped_measure, "文字超出区域，已截断为省略号"
