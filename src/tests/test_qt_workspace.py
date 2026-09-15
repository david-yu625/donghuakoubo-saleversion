from __future__ import annotations

import os
import unittest
from unittest.mock import ANY, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ..qt_app import (
    PipelineWindow,
    WORKFLOW_COVER,
    WORKFLOW_LANDSCAPE,
    WORKFLOW_PORTRAIT_PACKAGE,
    WORKFLOW_PUBLISH,
)


class QtWorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = PipelineWindow()

    def tearDown(self):
        self.window.close()

    def test_theme_workspace_uses_three_visible_stages(self):
        self.assertEqual(
            list(self.window.workflow_stage_buttons),
            ["视频制作", "作品资产", "作品发布"],
        )
        self.assertNotIn("workflow_group", self.window.project_labels)
        self.assertNotIn("workflow_mode", self.window.project_labels)
        self.assertTrue(self.window.workflow_mode.isHidden())

    def test_workspace_starts_roomy_with_topic_details_collapsed(self):
        self.assertEqual((self.window.width(), self.window.height()), (1440, 900))
        self.assertFalse(self.window.project_settings_expanded)
        self.assertTrue(self.window.project_panel_body.isHidden())

    def test_stage_navigation_maps_to_existing_workflow_modes(self):
        self.window._select_workflow_stage("作品资产")
        self.assertEqual(self.window.workflow_mode.currentText(), WORKFLOW_COVER)
        self.assertEqual(self.window.workflow_tabs.currentIndex(), 2)
        self.assertTrue(self.window.inputs["topic"].isVisibleTo(self.window.project_panel))
        self.assertTrue(self.window.workflow_actions.isHidden())

        self.window._select_workflow_stage("作品发布")
        self.assertEqual(self.window.workflow_mode.currentText(), WORKFLOW_PUBLISH)
        self.assertEqual(self.window.workflow_tabs.currentIndex(), 3)
        self.assertTrue(self.window.workflow_actions.isHidden())

        self.window._select_workflow_stage("视频制作")
        self.assertEqual(self.window.workflow_mode.currentText(), WORKFLOW_LANDSCAPE)
        combo_index = self.window.video_mode_combo.findData(WORKFLOW_PORTRAIT_PACKAGE)
        self.window.video_mode_combo.setCurrentIndex(combo_index)
        self.assertEqual(self.window.workflow_mode.currentText(), WORKFLOW_PORTRAIT_PACKAGE)

    def test_idle_video_toolbar_hides_irrelevant_stop_action(self):
        self.window._select_workflow_stage("视频制作")
        self.assertTrue(self.window.stop_button.isHidden())
        self.assertFalse(self.window.batch_button.isHidden())
        self.assertFalse(self.window.continue_button.isHidden())
        self.assertFalse(self.window.start_button.isHidden())

    def test_batch_topic_generation_allows_empty_direction(self):
        class ImmediateThread:
            def __init__(self, *, target, daemon):
                self.target = target
                self.daemon = daemon

            def start(self):
                self.target()

        self.window.inputs["topic_direction"].clear()
        self.window.inputs["topic"].setText("当前主题")
        self.window.context_input.setPlainText("补充要求")
        self.window.batch_topics.setPlainText("用户自己填写的批量主题")

        with (
            patch("src.qt_app.QInputDialog.getInt", return_value=(3, True)),
            patch("src.qt_app.generate_unique_topics", return_value=["主题一", "主题二", "主题三"]) as generate,
            patch("src.qt_app.threading.Thread", ImmediateThread),
            patch("src.qt_app.QMessageBox.information") as information,
        ):
            self.window.generate_batch_topics()

        generate.assert_called_once_with(
            3,
            direction="",
            context="补充要求",
            current_topic="当前主题",
            progress_callback=ANY,
        )
        information.assert_not_called()
        self.assertIn("批量生成主题开始：计划生成 3 个主题", self.window.log.toPlainText())
        self.assertIn("批量生成主题完成：新增 3 个主题", self.window.log.toPlainText())
        self.assertEqual(self.window.batch_topics.toPlainText(), "用户自己填写的批量主题")


if __name__ == "__main__":
    unittest.main()
