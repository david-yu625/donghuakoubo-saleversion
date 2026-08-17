from __future__ import annotations

import base64
import io
import tempfile
import unittest
from urllib.error import HTTPError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

from ..prepare.image_generation import (
    OPENAI_COMPATIBLE_HEADERS,
    generate_image,
    generate_openai_image_bytes,
    background_content_bottom_ratio,
    record_background_content_bounds,
    is_shot_background_prompt,
    normalize_base_url,
    original_image_path,
    is_valid_image_file,
    uses_white_background_prompt,
)


class FakeVisualService:
    def cv_process(self, form):
        self.form = form
        image = Image.new("RGB", (128, 128), "#ffffff")
        ImageDraw.Draw(image).rectangle((32, 24, 96, 104), fill="#ffffff", outline="#111111", width=4)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return {
            "code": 10000,
            "data": {"binary_data_base64": [base64.b64encode(buffer.getvalue()).decode()]},
        }


class FlakyVisualService(FakeVisualService):
    def __init__(self):
        self.attempts = 0

    def cv_process(self, form):
        self.attempts += 1
        if self.attempts < 3:
            raise TimeoutError("temporary timeout")
        return super().cv_process(form)


class FakeWhiteVisualService(FakeVisualService):
    def cv_process(self, form):
        self.form = form
        image = Image.new("RGB", (128, 128), "#ffffff")
        ImageDraw.Draw(image).rectangle((32, 24, 96, 104), fill="#ff6b6b", outline="#111111", width=4)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return {
            "code": 10000,
            "data": {"binary_data_base64": [base64.b64encode(buffer.getvalue()).decode()]},
        }


class ImageGenerationTest(unittest.TestCase):
    def test_invalid_or_empty_asset_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "partial.png"
            invalid.write_bytes(b"partial")

            self.assertFalse(is_valid_image_file(invalid))
            self.assertFalse(is_valid_image_file(root / "missing.png"))

            valid = root / "valid.png"
            Image.new("RGB", (8, 8), "white").save(valid)
            self.assertTrue(is_valid_image_file(valid))

    def test_background_content_bounds_records_actual_nonwhite_bottom(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated_assets_plus" / "s1_bg01.png"
            output.parent.mkdir(parents=True)
            image = Image.new("RGB", (100, 100), "white")
            ImageDraw.Draw(image).line((10, 31, 90, 31), fill="#111111", width=2)
            image.save(output)

            record_background_content_bounds(output)

            self.assertAlmostEqual(background_content_bottom_ratio(output), 0.33, places=2)
            manifest = output.parent / "background_content_bounds.json"
            self.assertTrue(manifest.exists())
    def test_generated_image_is_saved_to_requested_asset_path(self):
        service = FakeVisualService()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated_assets_plus" / "image.png"
            with patch("src.prepare.image_generation.visual_service", return_value=service):
                result = generate_image(
                    prompt="一个白色背景知识图标",
                    output_path=output,
                    width=1024,
                    height=1536,
                    req_key="test-key",
                )
            self.assertEqual(result, output)
            original = original_image_path(output)
            self.assertTrue(original.exists())
            with Image.open(original) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (128, 128))
                self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGB")
            self.assertEqual(service.form["width"], 1024)
            self.assertEqual(service.form["height"], 1536)
            self.assertFalse(service.form["watermark"])

    def test_generation_retries_transient_request_failures(self):
        service = FlakyVisualService()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "image.png"
            with (
                patch("src.prepare.image_generation.visual_service", return_value=service),
                patch("src.prepare.image_generation.time.sleep"),
            ):
                generate_image(
                    prompt="一个白色背景知识图标",
                    output_path=output,
                    width=1024,
                    height=1536,
                    req_key="test-key",
                )
            self.assertEqual(service.attempts, 3)
            self.assertTrue(output.exists())

    def test_white_theme_crops_unused_white_canvas_without_removing_background(self):
        service = FakeWhiteVisualService()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "image.png"
            with patch("src.prepare.image_generation.visual_service", return_value=service):
                generate_image(
                    prompt="一个白色背景知识图标",
                    output_path=output,
                    width=1024,
                    height=1536,
                    req_key="test-key",
                    visual_theme="white",
                )
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertLess(image.width, 128)
                self.assertLess(image.height, 128)
                self.assertLessEqual(image.width, 70)
                self.assertLessEqual(image.height, 86)
                self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
                self.assertIn((255, 107, 107), image.getdata())
            with Image.open(original_image_path(output)) as original:
                self.assertEqual(original.size, (128, 128))
                self.assertEqual(original.getpixel((0, 0)), (255, 255, 255))

    def test_neutral_paper_tint_is_whitened_without_bleaching_color(self):
        from ..prepare.image_generation import normalize_near_white_background

        image = Image.new("RGB", (3, 1), (247, 245, 242))
        image.putpixel((1, 0), (220, 240, 250))
        image.putpixel((2, 0), (20, 20, 20))

        normalized = normalize_near_white_background(image)

        self.assertEqual(normalized.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(normalized.getpixel((1, 0)), (220, 240, 250))
        self.assertEqual(normalized.getpixel((2, 0)), (20, 20, 20))

    def test_legacy_theme_value_still_preserves_opaque_white_insert_image(self):
        service = FakeWhiteVisualService()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "insert.png"
            with patch("src.prepare.image_generation.visual_service", return_value=service):
                generate_image(
                    prompt="请生成一张 MG 动画风格的图片。图片背景是纯白色背景。",
                    output_path=output,
                    width=1024,
                    height=1536,
                    req_key="test-key",
                    visual_theme="brown",
                )

            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))

    def test_shot_background_keeps_its_full_white_canvas(self):
        service = FakeWhiteVisualService()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "background.png"
            with patch("src.prepare.image_generation.visual_service", return_value=service):
                generate_image(
                    prompt="请生成一张 MG 动画风格的背景图。图片背景是纯白色背景。",
                    output_path=output,
                    width=1024,
                    height=1536,
                    req_key="test-key",
                    visual_theme="brown",
                )

            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (1024, 1536))
                self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(image.getpixel((512, 768)), (255, 107, 107))

    def test_current_prompt_templates_are_classified_for_post_processing(self):
        background_prompt = (
            "请生成适合抖音科普短视频的 MG 动画风格图片，整体像 Excalidraw 手绘白板图解。\n"
            "画笔线条稍微粗一些，背景保持纯白色。\n"
            "#目标\n"
            "1. 根据下面的分镜设计生成背景图。\n"
            "分镜设计：分镜标题：测试；背景画面：测试；背景文字：测试"
        )
        element_prompt = (
            "请生成适合抖音科普短视频的 MG 动画风格图片，整体像 Excalidraw 手绘白板图解。\n"
            "画笔线条稍微粗一些，背景保持纯白色。\n"
            "#目标\n"
            "1. 根据下面的图片元素设计生成元素图。\n"
            "图片元素设计：一个灯泡"
        )

        self.assertTrue(is_shot_background_prompt(background_prompt))
        self.assertFalse(is_shot_background_prompt(element_prompt))
        self.assertTrue(uses_white_background_prompt(background_prompt))
        self.assertTrue(uses_white_background_prompt(element_prompt))

    def test_scene_background_prompt_is_not_misclassified_as_insert_image(self):
        prompt = "根据下面的背景内容设计生成 16:9 横屏场景背景图。\n背景内容设计：板书分区"

        self.assertTrue(is_shot_background_prompt(prompt))

    def test_openai_compatible_model_uses_images_api_parameters(self):
        image = Image.new("RGB", (128, 128), "#ffffff")
        ImageDraw.Draw(image).rectangle((32, 24, 96, 104), fill="#ff0000")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode()
        images_api = SimpleNamespace()
        images_api.generate = unittest.mock.Mock(return_value=SimpleNamespace(
            data=[SimpleNamespace(b64_json=encoded, url=None)],
        ))
        client = SimpleNamespace(images=images_api)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "image.png"
            with patch("src.prepare.image_generation.OpenAI", return_value=client) as openai_factory:
                generate_image(
                    prompt="一个白色背景知识图标",
                    output_path=output,
                    width=1024,
                    height=1536,
                    model="gpt-image-2",
                    api_key="test-key",
                    base_url="https://example.com/api",
                    quality="high",
                )
            with Image.open(output) as generated:
                self.assertEqual(generated.mode, "RGB")
                self.assertEqual(generated.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(generated.getpixel((64, 64)), (255, 0, 0))

        openai_factory.assert_called_once_with(
            api_key="test-key",
            base_url="https://example.com/api/v1",
            timeout=180.0,
            default_headers=OPENAI_COMPATIBLE_HEADERS,
        )
        images_api.generate.assert_called_once_with(
            model="gpt-image-2",
            prompt="一个白色背景知识图标",
            size="1024x1536",
            n=1,
            quality="high",
        )

    def test_image_url_download_uses_browser_headers_without_regenerating(self):
        images_api = SimpleNamespace(generate=unittest.mock.Mock(return_value=SimpleNamespace(
            data=[SimpleNamespace(b64_json=None, url="https://cdn.example.com/generated.png")],
        )))
        client = SimpleNamespace(images=images_api)
        download = MagicMock()
        download.__enter__.return_value.read.return_value = b"image-bytes"
        forbidden = HTTPError("https://cdn.example.com/generated.png", 403, "Forbidden", {}, None)

        with (
            patch("src.prepare.image_generation.OpenAI", return_value=client),
            patch("src.prepare.image_generation.urlopen", side_effect=[forbidden, download]) as mocked_urlopen,
            patch("src.prepare.image_generation.time.sleep"),
        ):
            result = generate_openai_image_bytes(
                prompt="test",
                width=1536,
                height=864,
                model="gpt-image-2",
                api_key="key",
                base_url="https://example.com/v1",
                quality="low",
                max_attempts=3,
                retry_delay_seconds=2,
            )

        self.assertEqual(result, b"image-bytes")
        images_api.generate.assert_called_once()
        self.assertEqual(mocked_urlopen.call_count, 2)
        request = mocked_urlopen.call_args_list[0].args[0]
        self.assertEqual(request.get_header("User-agent"), OPENAI_COMPATIBLE_HEADERS["User-Agent"])
        self.assertIn("image/", request.get_header("Accept"))

    def test_image_base_url_is_normalized(self):
        self.assertEqual(normalize_base_url("https://example.com"), "https://example.com/v1")
        self.assertEqual(normalize_base_url("https://example.com/v1/"), "https://example.com/v1")


if __name__ == "__main__":
    unittest.main()
