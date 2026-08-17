from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ..app_settings import (
    load_app_settings,
    migrate_legacy_app_settings,
    save_app_settings,
)


class AppSettingsTest(unittest.TestCase):
    def test_structured_settings_round_trip_only_known_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_app_settings({
                "VISUAL_THEME": "white",
                "TITLE_COLOR": "#123456",
                "UNKNOWN": "ignored",
            }, path)

            values = load_app_settings(path)

        self.assertEqual(values, {
            "VISUAL_THEME": "white",
            "TITLE_COLOR": "#123456",
        })

    def test_legacy_app_values_move_out_of_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_path = root / ".env"
            settings_path = root / "settings.json"
            env_path.write_text(
                "DEEPSEEK_API_KEY=dummy\n"
                "VISUAL_THEME=white\n"
                "TITLE_COLOR=#112233\n"
                "VIDEO_ORIENTATION=横屏\n",
                encoding="utf-8",
            )

            values = migrate_legacy_app_settings(env_path, settings_path)

            self.assertEqual(values["TITLE_COLOR"], "#112233")
            self.assertEqual(values["VIDEO_ORIENTATION"], "横屏")
            self.assertEqual(load_app_settings(settings_path), values)
            self.assertEqual(env_path.read_text(encoding="utf-8"), "DEEPSEEK_API_KEY=dummy\n")

    def test_existing_structured_value_wins_during_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_path = root / ".env"
            settings_path = root / "settings.json"
            env_path.write_text("TITLE_COLOR=#111111\n", encoding="utf-8")
            save_app_settings({"TITLE_COLOR": "#ABCDEF"}, settings_path)

            values = migrate_legacy_app_settings(env_path, settings_path)

        self.assertEqual(values["TITLE_COLOR"], "#ABCDEF")


if __name__ == "__main__":
    unittest.main()
