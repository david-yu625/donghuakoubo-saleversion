from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ..application.draft_builder import build_project_draft
from ..core.models import Canvas, LayoutResult


class DraftBuilderTest(unittest.TestCase):
    def test_landscape_layout_omits_global_title_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            result = build_project_draft(
                project,
                layout=LayoutResult("test", Canvas(width=1920, height=1080), []),
                draft_folder=root / "drafts",
                draft_name="landscape",
                project_title="横版标题",
                include_audio=False,
                include_background_music=False,
                include_background=False,
                include_sound_effects=False,
                orientation="landscape",
                replace=True,
            )

            content = json.loads((result.path / "draft_content.json").read_text(encoding="utf-8"))
            track_names = {track["name"] for track in content["tracks"]}
            self.assertNotIn("global_title", track_names)
            self.assertNotIn("global_title_bar", track_names)

    def test_portrait_layout_keeps_global_title_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            result = build_project_draft(
                project,
                layout=LayoutResult("test", Canvas(), []),
                draft_folder=root / "drafts",
                draft_name="portrait",
                project_title="竖版标题",
                include_audio=False,
                include_background_music=False,
                include_background=False,
                include_sound_effects=False,
                orientation="portrait",
                replace=True,
            )

            content = json.loads((result.path / "draft_content.json").read_text(encoding="utf-8"))
            track_names = {track["name"] for track in content["tracks"]}
            self.assertIn("global_title", track_names)
            self.assertIn("global_title_bar", track_names)


if __name__ == "__main__":
    unittest.main()
