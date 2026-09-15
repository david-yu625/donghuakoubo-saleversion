from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ..app_settings import save_app_settings
from ..settings import default_background_image, load_render_settings, resolve_visual_theme


class VisualThemeSettingsTest(unittest.TestCase):
    def test_legacy_theme_values_resolve_to_white_board_assets(self):
        self.assertEqual(resolve_visual_theme("brown").label, "白色主题")
        self.assertEqual(resolve_visual_theme("白色主题").key, "white")
        root = Path("/project")
        self.assertEqual(
            default_background_image(root, "brown"),
            root / "picturies/background/background_2.png",
        )

    def test_current_theme_accepts_saved_color_overrides(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VISUAL_THEME": "white",
            "TITLE_COLOR": "#123456",
            "TITLE_BACKGROUND_COLOR": "#000000",
            "SUBTITLE_COLOR": "#FF0000",
            "SUBTITLE_BACKGROUND_COLOR": "#654321",
        }):
            settings = load_render_settings(settings_path=Path(directory) / "missing.json")

        self.assertEqual(settings.visual_theme.key, "white")
        self.assertEqual(settings.title_color, "#123456")
        self.assertEqual(settings.title_background_color, "#000000")
        self.assertEqual(settings.subtitle_color, "#FF0000")
        self.assertEqual(settings.subtitle_background_color, "#654321")

    def test_legacy_theme_environment_still_uses_white_theme_overrides(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VISUAL_THEME": "brown",
            "TITLE_COLOR": "#123456",
            "SUBTITLE_BACKGROUND_COLOR": "#654321",
        }):
            settings = load_render_settings("white", settings_path=Path(directory) / "missing.json")

        self.assertEqual(settings.title_color, "#123456")
        self.assertEqual(settings.subtitle_background_color, "#654321")

    def test_structured_settings_override_legacy_render_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_app_settings({
                "VISUAL_THEME": "white",
                "TITLE_FONT": "雅酷黑简",
                "TITLE_COLOR": "#ABCDEF",
                "SUBTITLE_BACKGROUND_COLOR": "#123456",
            }, path)
            with patch.dict(os.environ, {
                "TITLE_COLOR": "#000000",
                "SUBTITLE_BACKGROUND_COLOR": "#000000",
            }):
                settings = load_render_settings(settings_path=path)

        self.assertEqual(settings.title_color, "#ABCDEF")
        self.assertEqual(settings.subtitle_background_color, "#123456")

if __name__ == "__main__":
    unittest.main()
