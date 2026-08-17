"""User-configurable rendering and project defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .app_settings import APP_SETTINGS_PATH, load_app_settings


DEFAULT_VISUAL_THEME = "white"
VISUAL_THEME_CHOICES = ("白色主题",)
DEFAULT_TITLE_FONT = "雅酷黑简"
DEFAULT_TITLE_COLOR = "#000000"
DEFAULT_TITLE_BACKGROUND_COLOR = "#FFDE00"
DEFAULT_KEYWORD_FONT = "得意黑"
DEFAULT_KEYWORD_COLOR = "#252525"
DEFAULT_KEYWORD_TEXT_COLOR = "#F4C542"
# Keep keyword fills colorful; black is reserved for structural outlines.
KEYWORD_TEXT_COLORS = ("#F4C542", "#EE7A7A", "#F28C28", "#2F80ED")
DEFAULT_KEYWORD_BORDER_COLOR = "#FFFFFF"
DEFAULT_KEYWORD_BORDER_WIDTH = 12.0
DEFAULT_SUBTITLE_FONT = "未光体"
DEFAULT_SUBTITLE_COLOR = "#FFFFFF"
DEFAULT_SUBTITLE_BACKGROUND_COLOR = "#A84663"


@dataclass(frozen=True)
class VisualThemeProfile:
    key: str
    label: str
    title_color: str
    title_background_color: str
    subtitle_color: str
    subtitle_background_color: str
    background_path: str


VISUAL_THEMES = {
    "white": VisualThemeProfile(
        key="white",
        label="白色主题",
        title_color="#111111",
        title_background_color="#FFD84D",
        subtitle_color="#FFFFFF",
        subtitle_background_color="#222222",
        background_path="picturies/background/background_2.png",
    ),
}


@dataclass(frozen=True)
class RenderSettings:
    visual_theme: VisualThemeProfile = VISUAL_THEMES[DEFAULT_VISUAL_THEME]
    title_font: str = DEFAULT_TITLE_FONT
    title_color: str = DEFAULT_TITLE_COLOR
    title_background_color: str = DEFAULT_TITLE_BACKGROUND_COLOR
    subtitle_font: str = DEFAULT_SUBTITLE_FONT
    subtitle_color: str = DEFAULT_SUBTITLE_COLOR
    subtitle_background_color: str = DEFAULT_SUBTITLE_BACKGROUND_COLOR


def resolve_visual_theme(
    value: str = "",
    *,
    settings_path: Path = APP_SETTINGS_PATH,
) -> VisualThemeProfile:
    saved = load_app_settings(settings_path)
    selected = (
        value.strip()
        or saved.get("VISUAL_THEME", "").strip()
        or os.getenv("VISUAL_THEME", "").strip()
        or DEFAULT_VISUAL_THEME
    )
    selected_lower = selected.lower()
    for profile in VISUAL_THEMES.values():
        if selected_lower == profile.key or selected == profile.label:
            return profile
    return VISUAL_THEMES[DEFAULT_VISUAL_THEME]


def load_render_settings(
    visual_theme: str = "",
    *,
    settings_path: Path = APP_SETTINGS_PATH,
) -> RenderSettings:
    saved = load_app_settings(settings_path)
    saved_theme_value = saved.get("VISUAL_THEME", "") or os.getenv("VISUAL_THEME", "")
    theme = resolve_visual_theme(visual_theme or saved_theme_value, settings_path=settings_path)
    configured_theme = resolve_visual_theme(saved_theme_value, settings_path=settings_path)
    use_color_overrides = not visual_theme.strip() or configured_theme.key == theme.key

    def setting_value(key: str, default: str) -> str:
        return saved.get(key, "").strip() or os.getenv(key, "").strip() or default

    return RenderSettings(
        visual_theme=theme,
        title_font=setting_value("TITLE_FONT", DEFAULT_TITLE_FONT),
        title_color=(
            normalize_hex_color(setting_value("TITLE_COLOR", theme.title_color), theme.title_color)
            if use_color_overrides
            else theme.title_color
        ),
        title_background_color=(
            normalize_hex_color(
                setting_value("TITLE_BACKGROUND_COLOR", theme.title_background_color),
                theme.title_background_color,
            )
            if use_color_overrides
            else theme.title_background_color
        ),
        subtitle_font=setting_value("SUBTITLE_FONT", DEFAULT_SUBTITLE_FONT),
        subtitle_color=(
            normalize_hex_color(setting_value("SUBTITLE_COLOR", theme.subtitle_color), theme.subtitle_color)
            if use_color_overrides
            else theme.subtitle_color
        ),
        subtitle_background_color=(
            normalize_hex_color(
                setting_value("SUBTITLE_BACKGROUND_COLOR", theme.subtitle_background_color),
                theme.subtitle_background_color,
            )
            if use_color_overrides
            else theme.subtitle_background_color
        ),
    )


def normalize_hex_color(value: str, default: str) -> str:
    value = value.strip().upper()
    if not value.startswith("#"):
        value = f"#{value}"
    if len(value) != 7 or any(character not in "0123456789ABCDEF" for character in value[1:]):
        return default
    return value


def read_hex_color(key: str, default: str) -> str:
    return normalize_hex_color(os.getenv(key, default), default)


def default_background_image(project_root: Path, visual_theme: str = "") -> Path:
    return project_root / resolve_visual_theme(visual_theme).background_path
