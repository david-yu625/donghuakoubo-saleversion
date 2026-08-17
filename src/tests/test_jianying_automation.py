from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ..application.jianying_automation import JianyingAutomationError, validate_draft_path


class JianyingAutomationTest(unittest.TestCase):
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

