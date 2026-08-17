from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from ..application.project_compiler import compile_project, without_opening_title_subtitle
from ..pipeline import build_scene_facts, load_project
from ..renderers.jianying_renderer import text_style_size


class ProjectPipelineTest(unittest.TestCase):
    def test_opening_narration_is_not_mistaken_for_the_project_title(self):
        rows = [
            ("第一次打开ComfyUI的人，十有八九会被吓退", 0, 2760),
            ("满屏的节点和连线", 2760, 4100),
        ]

        self.assertEqual(without_opening_title_subtitle(rows, "什么是ComfyUI"), rows)
        self.assertEqual(without_opening_title_subtitle(rows, rows[0][0]), rows[1:])

    def test_pipeline_preserves_timing_assets_and_cleans_subtitle_punctuation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            asset = project / "asset.png"
            image = Image.new("RGBA", (200, 300), (0, 0, 0, 0))
            ImageDraw.Draw(image).ellipse((40, 30, 160, 270), fill="#ffcc66")
            image.save(asset)
            (project / "wenan.txt").write_text("什么是测试\n第一句话。\n第二句话！\n", encoding="utf-8")
            (project / "timeline.csv").write_text(
                "index,text,time\n"
                "1,什么是测试,[0.100,1.000,0.900]\n"
                "2,第一句话,[1.200,2.000,0.800]\n"
                "3,第二句话,[2.200,3.000,0.800]\n",
                encoding="utf-8",
            )
            write_csv(project / "shot_timeline_source_time.csv", [
                "shot_id", "分镜标题", "开始时间ms", "结束时间ms", "分镜对应原始文案内容",
            ], [
                ["1", "什么是测试", "100", "1000", "什么是测试"],
                ["2", "解释过程", "1200", "3000", "第一句话第二句话"],
            ])
            write_csv(project / "element_timeline_with_assets.csv", [
                "element_id", "shot_id", "type", "content", "start_ms", "end_ms", "asset_path",
            ], [
                ["s1_img01", "1", "image", "标题图", "100", "1000", str(asset)],
                ["s1_txt01", "1", "text", "什么是测试", "100", "1000", ""],
                ["s2_img01", "2", "image", "第一阶段", "1200", "2000", str(asset)],
                ["s2_txt01", "2", "text", "第一阶段", "1200", "2000", ""],
                ["s2_img02", "2", "image", "第二阶段", "2200", "3000", str(asset)],
                ["s2_txt02", "2", "text", "第二阶段", "2200", "3000", ""],
            ])

            source = load_project(project)
            facts = build_scene_facts(source)
            self.assertEqual(facts[1].semantic_role, "sequence")
            self.assertEqual((facts[1].elements[2].start_ms, facts[1].elements[2].end_ms), (1000, 1800))
            self.assertEqual(source.subtitle_rows[-1][0], "第二句话！")

            result = compile_project(project, project_title="什么是测试")
            image_ids = {element.element_id for element in result.elements if element.element_type == "image"}
            self.assertIn("scene_002_s2_img01", image_ids)
            self.assertIn("scene_002_s2_img02", image_ids)
            second = next(element for element in result.elements if element.element_id == "scene_002_s2_img02")
            self.assertEqual((second.start_ms, second.end_ms), (2200, 3000))
            subtitles = [element for element in result.elements if element.role == "subtitle"]
            self.assertEqual([element.content for element in subtitles], ["什么是测试", "第一句话", "第二句话"])
            self.assertTrue(all(element.metadata["font_name"] == "未光体" for element in subtitles))
            self.assertTrue(all(element.box.center_y == 1534 for element in subtitles))
            emphasized = [element for element in result.elements if element.element_type == "text" and element.role != "subtitle"]
            for element in emphasized:
                estimated_height = round(text_style_size(element.font_size or 40, element.role) * 5.5)
                self.assertLessEqual(estimated_height, element.box.height)

            white_result = compile_project(
                project,
                project_title="什么是测试",
                visual_theme="white",
            )
            white_subtitles = [element for element in white_result.elements if element.role == "subtitle"]
            self.assertTrue(all(element.metadata["text_color"] == "#FFFFFF" for element in white_subtitles))
            self.assertTrue(all(
                element.metadata["subtitle_background_color"] == "#222222"
                for element in white_subtitles
            ))

            landscape_result = compile_project(
                project,
                project_title="什么是测试",
                orientation="横屏",
            )
            self.assertEqual((landscape_result.canvas.width, landscape_result.canvas.height), (1920, 1080))
            for element in landscape_result.elements:
                self.assertGreaterEqual(element.box.x, 0)
                self.assertGreaterEqual(element.box.y, 0)
                self.assertLessEqual(element.box.right, landscape_result.canvas.width)
                self.assertLessEqual(element.box.bottom, landscape_result.canvas.height)
            landscape_subtitles = [element for element in landscape_result.elements if element.role == "subtitle"]
            self.assertEqual(landscape_subtitles, [])


def write_csv(path: Path, fieldnames: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(fieldnames)
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
