from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ..application import jianying_automation
from ..application.jianying_automation import (
    JianyingAutomationError,
    find_timestamp_matching_draft,
    validate_draft_path,
)


class JianyingAutomationTest(unittest.TestCase):
    def test_find_named_control_matches_windows_full_description(self):
        class FakeControl:
            Name = ""

            def GetChildren(self):
                return []

            def GetPropertyValue(self, property_id):
                self.test_case.assertEqual(property_id, 30159)
                return "ExportOkBtn"

        control = FakeControl()
        control.test_case = self
        self.assertIs(
            jianying_automation._find_named_control(
                control,
                ("ExportOkBtn",),
                timeout=1,
            ),
            control,
        )

    def test_windows_export_button_includes_internal_qt_identifier(self):
        self.assertIn("MainWindowTitleBarExportBtn", jianying_automation.EXPORT_BUTTON_NAMES)

    def test_parse_export_path_accepts_windows_drive_path(self):
        self.assertEqual(
            jianying_automation._parse_export_path("D:/8月19日.mp4"),
            Path("D:/8月19日.mp4"),
        )

    def test_open_draft_windows_clicks_parent_of_home_page_title(self):
        class FakeAuto:
            @staticmethod
            def ControlFromHandle(_hwnd):
                return object()

        class FakeCard:
            click_args = None

            def Click(self, **kwargs):
                self.click_args = kwargs

        class FakeTitle:
            def __init__(self, parent):
                self.parent = parent

            def GetParentControl(self):
                return self.parent

        card = FakeCard()
        title = FakeTitle(card)
        draft_path = Path("C:/drafts/topic_landscape(1)")

        with (
            patch.object(
                jianying_automation,
                "_windows_helpers",
                return_value=(FakeAuto(), object()),
            ),
            patch.object(jianying_automation, "_window_handles", return_value=[123]),
            patch.object(
                jianying_automation,
                "_find_named_control",
                return_value=title,
            ) as find_control,
            patch.object(jianying_automation, "_activate_window"),
        ):
            result = jianying_automation._open_draft_windows(
                draft_path,
                "topic_landscape",
                timeout=1,
            )

        self.assertEqual(result, draft_path)
        self.assertEqual(
            find_control.call_args.args[1],
            (
                "HomePageDraftTitle:topic_landscape(1)",
                "HomePageDraftTitle:topic_landscape",
            ),
        )
        self.assertEqual(card.click_args, {"simulateMove": False})

    def test_validate_draft_path_requires_an_existing_child_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = root / "demo_landscape"
            draft.mkdir()

            self.assertEqual(validate_draft_path(root, draft.name), draft.resolve())
            with self.assertRaisesRegex(JianyingAutomationError, "找不到剪映草稿"):
                validate_draft_path(root, "missing")

    def test_validate_draft_path_rejects_nested_names(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(JianyingAutomationError, "不能包含目录路径"):
                validate_draft_path(directory, "nested\\draft")

    def test_validate_draft_path_accepts_jianying_numeric_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suffixed = root / "demo_landscape(1)"
            suffixed.mkdir()

            self.assertEqual(
                validate_draft_path(root, "demo_landscape"),
                suffixed.resolve(),
            )

    def test_timestamp_match_recovers_draft_when_topic_changed_in_ui(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual = root / "新主题_20260818_210021_landscape_master_landscape(1)"
            actual.mkdir()

            self.assertEqual(
                find_timestamp_matching_draft(
                    root,
                    "旧主题_20260818_210021_landscape_master_landscape",
                ),
                actual.resolve(),
            )

    def test_timestamp_match_does_not_guess_between_multiple_drafts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "主题一_20260818_210021_landscape").mkdir()
            (root / "主题二_20260818_210021_landscape").mkdir()

            self.assertIsNone(
                find_timestamp_matching_draft(
                    root,
                    "旧主题_20260818_210021_landscape",
                )
            )

    def test_macos_export_button_rect_parses_accessibility_position(self):
        with patch.object(
            jianying_automation,
            "_run_macos_osascript",
            return_value="1049,824,72,20",
        ):
            self.assertEqual(
                jianying_automation._macos_export_button_rect(timeout=1),
                (1049.0, 824.0, 72.0, 20.0),
            )

    def test_macos_home_search_uses_exact_draft_name(self):
        with patch.object(
            jianying_automation,
            "_run_macos_osascript",
            return_value="ok",
        ) as run_script:
            self.assertTrue(jianying_automation._macos_search_home_drafts("8月19日", timeout=1))

        script = run_script.call_args.args[0]
        self.assertIn('set value of item 1 of fields to "8月19日"', script)
        self.assertIn("keystroke return", script)

    def test_macos_export_clicks_editor_and_final_export_buttons(self):
        clicks = []
        with (
            patch.object(jianying_automation, "_macos_focus_process"),
            patch.object(
                jianying_automation,
                "_macos_front_window_rect",
                side_effect=(
                    (497.0, 198.0, 1200.0, 800.0),
                    (497.0, 316.0, 640.0, 428.0),
                    (92.0, 232.0, 1449.0, 595.0),
                    # Current macOS builds reuse the editor window geometry
                    # after returning to the home page.
                    (92.0, 232.0, 1449.0, 595.0),
                ),
            ),
            patch.object(
                jianying_automation,
                "_macos_post_mouse_click",
                side_effect=lambda x, y, **kwargs: clicks.append((x, y, kwargs)),
            ),
            patch.object(
                jianying_automation,
                "_macos_export_panel_open",
                return_value=True,
            ),
            patch.object(
                jianying_automation,
                "_macos_export_state",
                side_effect=(
                    jianying_automation.JianyingAutomationError("temporary AX timeout"),
                    "complete",
                ),
            ),
            patch.object(
                jianying_automation,
                "_macos_confirm_exit_button_rect",
                return_value=(964.0, 500.0, 76.0, 22.0),
            ),
            patch.object(
                jianying_automation,
                "_macos_export_button_rect",
                return_value=(1049.0, 824.0, 72.0, 20.0),
            ),
            patch.object(
                jianying_automation,
                "_macos_export_path",
                return_value=Path("/tmp/topic_landscape.mp4"),
            ),
            patch.object(jianying_automation, "_macos_quit_application") as quit_application,
            patch.object(jianying_automation.time, "sleep"),
        ):
            jianying_automation._click_export_macos(timeout=1)

        self.assertEqual(clicks[0], (1652.0, 218.0, {}))
        self.assertEqual(clicks[1], (1085.0, 834.0, {}))
        self.assertEqual(clicks[2], (1085.0, 717.0, {}))
        self.assertEqual(clicks[3], (108.0, 248.0, {}))
        self.assertEqual(clicks[4], (108.0, 248.0, {}))
        self.assertEqual(clicks[5], (1002.0, 511.0, {}))
        quit_application.assert_called_once_with(timeout=10.0)

    def test_macos_export_path_reads_top_level_static_text(self):
        export_path = "/Users/test/Desktop/videos/topic.mp4"
        with patch.object(
            jianying_automation,
            "_run_macos_osascript",
            return_value=export_path,
        ) as run_script:
            self.assertEqual(
                jianying_automation._macos_export_path(timeout=1),
                Path(export_path),
            )

        script = run_script.call_args.args[0]
        self.assertIn("static texts of w", script)
        self.assertNotIn("entire contents of w", script)

    def test_parse_export_path_rejects_non_path_accessibility_values(self):
        self.assertEqual(
            jianying_automation._parse_export_path("/Users/me/Desktop/video.mp4"),
            Path("/Users/me/Desktop/video.mp4"),
        )
        self.assertIsNone(jianying_automation._parse_export_path("missing"))

    def test_macos_quit_uses_process_state_when_jianying_reports_cancel(self):
        with (
            patch.object(
                jianying_automation,
                "_macos_process_running",
                side_effect=(True, False),
            ),
            patch.object(
                jianying_automation,
                "_run_macos_osascript",
                side_effect=JianyingAutomationError("用户已取消 (-128)"),
            ),
        ):
            jianying_automation._macos_quit_application(timeout=1)
