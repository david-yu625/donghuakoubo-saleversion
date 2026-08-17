from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ..application.portrait_package import PORTRAIT_PACKAGE_TITLE_CENTER_RATIO, build_portrait_package
from ..layouts.regions import subtitle_area
from ..renderers.jianying_renderer import title_transform_y


class PortraitPackageTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_exported_landscape_video_becomes_one_portrait_media_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "topic" / "landscape"
            project.mkdir(parents=True)
            (project / "wenan.txt").write_text(
                "Topic\nThe packaged subtitle.\n",
                encoding="utf-8",
            )
            (project / "timeline.csv").write_text(
                "index,text,time\n"
                "1,Topic,[0.000,0.400,0.400]\n"
                "2,The packaged subtitle.,[0.500,1.800,1.300]\n",
                encoding="utf-8",
            )
            source = root / "landscape.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=white:s=1920x1080:d=2:r=30",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(source),
                ],
                check=True,
            )

            result = build_portrait_package(
                project,
                source_video=source,
                draft_folder=root / "drafts",
                draft_name="topic_portrait_package",
                project_title="Topic",
                visual_theme="white",
                replace=True,
            )

            content = json.loads((result.path / "draft_content.json").read_text(encoding="utf-8"))
            tracks = {track["name"]: track for track in content["tracks"]}
            self.assertEqual((result.layout.canvas.width, result.layout.canvas.height), (1080, 1920))
            self.assertIn("background", tracks)
            self.assertIn("foreground_video", tracks)
            self.assertIn("global_title", tracks)
            self.assertIn("global_title_bar", tracks)
            self.assertIn("narration_subtitles", tracks)
            self.assertNotIn("narration", tracks)
            self.assertNotIn("background_music", tracks)

            foreground = tracks["foreground_video"]["segments"][0]
            self.assertAlmostEqual(foreground["clip"]["scale"]["x"], 1.15)
            self.assertEqual(foreground["clip"]["transform"], {"x": 0.0, "y": 0.0})
            mask_id = next(
                reference
                for reference in foreground["extra_material_refs"]
                if any(mask["id"] == reference for mask in content["materials"]["masks"])
            )
            mask = next(mask for mask in content["materials"]["masks"] if mask["id"] == mask_id)
            self.assertEqual(mask["resource_type"], "rectangle")
            self.assertEqual(mask["config"]["width"], 1.0)
            self.assertEqual(mask["config"]["height"], 1.0)
            self.assertEqual(mask["config"]["roundCorner"], 0.1)
            prepared_background = result.package_dir / "prepared_assets" / "background_1080x1920.png"
            with Image.open(prepared_background) as image:
                self.assertEqual(image.size, (1080, 1920))
            subtitles = [element for element in result.layout.elements if element.role == "subtitle"]
            self.assertEqual([element.content for element in subtitles], ["The packaged subtitle"])
            self.assertTrue(all(
                element.box.center_y == subtitle_area(result.layout.canvas).center_y
                for element in subtitles
            ))
            title_track = tracks["global_title"]
            self.assertEqual(
                title_track["segments"][0]["clip"]["transform"]["y"],
                title_transform_y(1080, 1920, PORTRAIT_PACKAGE_TITLE_CENTER_RATIO),
            )
            title_material_id = title_track["segments"][0]["material_id"]
            title_material = next(
                item for item in content["materials"]["texts"] if item["id"] == title_material_id
            )
            title_style = json.loads(title_material["content"])["styles"][0]
            self.assertFalse(title_style["underline"])
            self.assertLess(title_style["size"], 17.0)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_black_portrait_package_omits_the_background_track(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "topic" / "landscape"
            project.mkdir(parents=True)
            (project / "wenan.txt").write_text("Topic\n", encoding="utf-8")
            source = root / "landscape.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=white:s=1920x1080:d=1:r=30",
                    "-c:v", "mpeg4", str(source),
                ],
                check=True,
            )

            result = build_portrait_package(
                project,
                source_video=source,
                draft_folder=root / "drafts",
                draft_name="black_portrait_package",
                include_subtitles=False,
                include_background=False,
                replace=True,
            )

            content = json.loads((result.path / "draft_content.json").read_text(encoding="utf-8"))
            track_names = {track["name"] for track in content["tracks"]}
            self.assertNotIn("background", track_names)
            self.assertIn("foreground_video", track_names)
            self.assertFalse((result.package_dir / "prepared_assets" / "background_1080x1920.png").exists())


if __name__ == "__main__":
    unittest.main()
