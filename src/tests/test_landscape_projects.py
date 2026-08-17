from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ..application.landscape_projects import (
    LandscapeProject,
    PortraitPackageState,
    discover_landscape_projects,
    find_matching_landscape_video,
    load_portrait_package_state,
    save_portrait_package_state,
)


class LandscapeProjectsTest(unittest.TestCase):
    def test_discovers_scoped_and_legacy_projects_newest_first(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy topic"
            scoped = root / "new topic" / "landscape"
            legacy.mkdir()
            scoped.mkdir(parents=True)
            legacy_timeline = legacy / "timeline.csv"
            scoped_timeline = scoped / "timeline.csv"
            legacy_timeline.write_text("legacy", encoding="utf-8")
            scoped_timeline.write_text("new", encoding="utf-8")
            os.utime(legacy_timeline, ns=(100, 100))
            os.utime(scoped_timeline, ns=(200, 200))
            os.utime(legacy, ns=(100, 100))
            os.utime(scoped, ns=(200, 200))

            projects = discover_landscape_projects(root)

        self.assertEqual([project.topic for project in projects], ["new topic", "legacy topic"])
        self.assertEqual(projects[0].project_dir, scoped.resolve())
        self.assertEqual(projects[1].project_dir, legacy.resolve())

    def test_scoped_project_wins_when_both_layouts_exist(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            topic = root / "topic"
            scoped = topic / "landscape"
            scoped.mkdir(parents=True)
            (topic / "timeline.csv").write_text("legacy", encoding="utf-8")
            (scoped / "timeline.csv").write_text("scoped", encoding="utf-8")

            projects = discover_landscape_projects(root)

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].project_dir, scoped.resolve())

    def test_state_round_trip_keeps_project_specific_video(self):
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "ui_state.json"
            state = PortraitPackageState(
                selected_project="D:/output/topic/landscape",
                source_videos={"D:/output/topic/landscape": "D:/exports/topic.mp4"},
            )

            save_portrait_package_state(state_path, state)
            restored = load_portrait_package_state(state_path)

            self.assertEqual(restored, state)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("portrait_package", payload)
            self.assertFalse((state_path.parent / ".ui_state.json.tmp").exists())

    def test_invalid_state_falls_back_to_empty(self):
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "ui_state.json"
            state_path.write_text("not-json", encoding="utf-8")

            restored = load_portrait_package_state(state_path)

        self.assertEqual(restored, PortraitPackageState())

    def test_matching_video_prefers_topic_match_and_newest_export(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project_dir = root / "output" / "what is comfyui" / "landscape"
            project_dir.mkdir(parents=True)
            timeline = project_dir / "timeline.csv"
            timeline.write_text("timeline", encoding="utf-8")
            exports = root / "exports"
            exports.mkdir()
            old = exports / "what is comfyui_old.mp4"
            newest = exports / "what is comfyui_final.mp4"
            unrelated = exports / "another topic.mp4"
            for path in (old, newest, unrelated):
                path.write_bytes(b"video")
            os.utime(old, ns=(100, 100))
            os.utime(newest, ns=(200, 200))
            os.utime(unrelated, ns=(300, 300))
            project = LandscapeProject(
                topic="what is comfyui",
                project_dir=project_dir.resolve(),
                timeline_path=timeline.resolve(),
                modified_ns=0,
            )

            result = find_matching_landscape_video(
                project,
                project_root=root,
                home=root / "home",
            )

        self.assertEqual(result, newest.resolve())


if __name__ == "__main__":
    unittest.main()
