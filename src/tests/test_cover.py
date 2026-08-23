from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ..pipeline_runtime import build_cover_command, cover_output_path
from ..prepare.cover import (
    COVER_HEIGHT,
    COVER_SIZE_OPTIONS,
    DEFAULT_COVER_SIZE_KEY,
    COVER_WIDTH,
    build_cover_prompt,
    default_cover_path,
    enforce_cover_dimensions,
    generate_cover,
    resolve_cover_size,
)
from ..prepare.image_generation import is_shot_background_prompt


class CoverWorkflowTest(unittest.TestCase):
    def test_cover_prompt_defaults_to_1080x1440_requirements(self):
        prompt = build_cover_prompt("计算机的组成", "突出 CPU、内存和存储的关系")

        self.assertIn("1080×1440", prompt)
        self.assertIn("3:4", prompt)
        self.assertIn("主题文字：计算机的组成", prompt)
        self.assertIn("准确、完整、清晰", prompt)
        self.assertIn("黑色手绘圆角矩形边框", prompt)
        self.assertIn("向内缩约 3%", prompt)
        self.assertIn("不能压住或越过边框", prompt)
        self.assertIn("CPU、内存和存储", prompt)
        self.assertIn("#封面图生成", prompt)
        self.assertTrue(is_shot_background_prompt(prompt))

    def test_cover_output_is_separate_from_orientation_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                default_cover_path("测试主题", root),
                (root / "测试主题" / "cover" / "测试主题_cover_1080x1440.png").resolve(),
            )
            self.assertEqual(
                cover_output_path("测试主题", output_root=root),
                (root / "测试主题" / "cover" / "测试主题_cover_1080x1440.png").resolve(),
            )

    def test_cover_sizes_and_commands(self):
        self.assertEqual(
            [item[0] for item in COVER_SIZE_OPTIONS],
            ["portrait", "landscape", "square", "portrait_1440"],
        )
        self.assertEqual(resolve_cover_size("landscape")[2:5], (1920, 1080, "16:9"))
        self.assertEqual(resolve_cover_size("1080*1920")[2:5], (1080, 1920, "9:16"))
        self.assertEqual(resolve_cover_size("1080×1080（正方形）")[2:5], (1080, 1080, "1:1"))
        self.assertEqual(resolve_cover_size("1080*1440")[2:5], (1080, 1440, "3:4"))

        command, output = build_cover_command(
            "测试主题",
            context="强调核心结构",
            image_model="gpt-image-2",
            image_quality="high",
            visual_theme="白色主题",
            cover_size="landscape",
            output_path=Path("/tmp/test_cover.png"),
        )

        self.assertEqual(DEFAULT_COVER_SIZE_KEY, "portrait_1440")
        self.assertEqual((COVER_WIDTH, COVER_HEIGHT), (1080, 1440))
        self.assertIn("src.generate_cover", command)
        self.assertEqual(command[command.index("--output") + 1], str(output))
        self.assertEqual(command[command.index("--model") + 1], "gpt-image-2")
        self.assertEqual(command[command.index("--quality") + 1], "high")
        self.assertEqual(command[command.index("--size") + 1], "landscape")
        self.assertIn("--overwrite", command)
        self.assertNotIn("src.01_generate_copywriting", command)
        self.assertNotIn("src.08_generate_jianying_draft", command)

    def test_cover_generation_disables_general_postprocessing_and_enforces_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cover.png"
            def fake_generate_image(**_kwargs):
                Image.new("RGB", (864, 1152), "white").save(output)
                return output

            with patch("src.prepare.cover.generate_image", side_effect=fake_generate_image) as generate:
                result = generate_cover(
                    topic="测试主题",
                    output_path=output,
                    model="gpt-image-2",
                    api_key="test-key",
                    cover_size="portrait_1440",
                )

            self.assertEqual(result, output)
            self.assertFalse(generate.call_args.kwargs["postprocess"])
            with Image.open(output) as image:
                self.assertEqual(image.size, (1080, 1440))

    def test_exact_cover_dimensions_are_left_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cover.png"
            Image.new("RGB", (1080, 1440), "white").save(output)

            result = enforce_cover_dimensions(output, 1080, 1440)

            self.assertEqual(result, output)
            with Image.open(output) as image:
                self.assertEqual(image.size, (1080, 1440))


if __name__ == "__main__":
    unittest.main()
