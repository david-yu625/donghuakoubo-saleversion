from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from ..core.models import Box, Canvas, ElementLayout, LayoutResult
from ..core.text_measure import resolve_font, text_width
from ..renderers.jianying_renderer import (
    FINAL_HOLD_MS,
    SCENE_TRANSITION_RESOURCE_IDS,
    JianyingRenderer,
    TITLE_TEXT_STYLE_SIZE,
    TITLE_BAR_HORIZONTAL_PADDING,
    TITLE_FONT_SIZE,
    TITLE_LETTER_SPACING,
    LANDSCAPE_TITLE_BAR_MIN_WIDTH_RATIO,
    SUBTITLE_BACKGROUND_HEIGHT,
    SUBTITLE_BACKGROUND_WIDTH,
    cached_font_path,
    draft,
    fitted_animation_duration,
    global_title_bar_scale,
    global_title_presentation,
    image_scale_multiplier,
    normalize_scene_backgrounds,
    scene_transition_for_index,
    title_bar_width,
    stabilize_final_element,
    text_style_size,
)


class RendererTypographyTest(unittest.TestCase):
    def test_render_sets_richest_image_as_draft_cover(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            plain = project / "plain.png"
            rich = project / "rich.png"
            Image.new("RGB", (320, 180), "white").save(plain)
            image = Image.new("RGB", (320, 180), "black")
            draw = ImageDraw.Draw(image)
            for x in range(0, 320, 8):
                draw.line((x, 0, 320 - x, 180), fill=(255, (x * 3) % 255, 40), width=4)
            image.save(rich)
            result = LayoutResult(
                "cover_test",
                Canvas(width=320, height=180),
                [
                    ElementLayout("background", "image", str(plain), Box(0, 0, 320, 180), 0, 1000, 1, "background"),
                    ElementLayout("rich", "image", str(rich), Box(0, 0, 320, 180), 0, 1000, 2, "element"),
                ],
            )

            draft_path = JianyingRenderer(project_root=root).render(
                result,
                draft_folder=root / "drafts",
                draft_name="cover_test",
            )

            content = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))
            metadata = json.loads((draft_path / "draft_meta_info.json").read_text(encoding="utf-8"))
            self.assertEqual(content["cover"]["type"], "image")
            self.assertEqual(metadata["draft_cover"], "draft_cover.jpg")
            with Image.open(draft_path / "draft_cover.jpg") as cover:
                self.assertEqual(cover.size, (320, 180))
            with Image.open(draft_path / "draft_local_cover.jpg") as local_cover:
                self.assertEqual(local_cover.size, (80, 45))

    def test_scene_backgrounds_are_adjacent_and_use_safe_native_transitions(self):
        elements = [
            ElementLayout(
                "s1_bg", "image", "a.png", Box(0, 0, 1920, 1080),
                0, 2800, 1, "background", metadata={"video_intro": "intro"},
            ),
            ElementLayout(
                "s2_bg", "image", "b.png", Box(0, 0, 1920, 1080),
                3000, 6000, 1, "background",
                metadata={"video_intro": "intro", "scene_transition": "background_intro"},
            ),
        ]
        normalized = normalize_scene_backgrounds(elements, content_end_ms=6000, final_end_ms=6800)

        self.assertEqual(normalized[0].end_ms, normalized[1].start_ms)
        self.assertEqual(normalized[1].end_ms, 6800)
        self.assertEqual(normalized[0].metadata["video_intro"], "intro")
        self.assertNotIn("video_intro", normalized[1].metadata)
        self.assertNotIn("scene_transition", normalized[1].metadata)
        for index, resource_id in enumerate(SCENE_TRANSITION_RESOURCE_IDS):
            transition = scene_transition_for_index(index)
            self.assertEqual(str(transition.value.resource_id), resource_id)
            self.assertFalse(transition.value.is_vip)

    def test_image_scale_depends_on_material_role(self):
        background = ElementLayout(
            "background", "image", "background.png", Box(0, 0, 1920, 1080),
            0, 3000, 10, "background",
        )
        overlay = ElementLayout(
            "overlay", "image", "overlay.png", Box(200, 200, 600, 400),
            0, 3000, 20, "overlay",
        )
        main = ElementLayout(
            "main", "image", "main.png", Box(200, 200, 600, 400),
            0, 3000, 20, "main",
        )
        self.assertEqual(image_scale_multiplier(background), 1.0)
        self.assertEqual(image_scale_multiplier(overlay), 1.0)
        self.assertGreater(image_scale_multiplier(main), 1.0)

    def test_image_segment_rejects_directory_as_material(self):
        result = LayoutResult("test", Canvas(), [])
        with tempfile.TemporaryDirectory() as directory:
            element = ElementLayout(
                "bad_image", "image", directory, Box(72, 400, 500, 500),
                0, 2000, 10, "main",
            )
            with self.assertRaisesRegex(FileNotFoundError, "缺少图片素材"):
                JianyingRenderer()._make_segment(element, result)

    def test_final_element_holds_without_outro_animation(self):
        element = ElementLayout(
            "final_label",
            "text",
            "人人可用",
            Box(72, 400, 500, 120),
            1000,
            3000,
            30,
            "label",
            82,
            ("人人可用",),
            metadata={"text_intro": "渐显", "text_outro": "轻微放大", "text_loop": "波浪"},
        )
        held = stabilize_final_element(
            element,
            content_end_ms=3000,
            final_end_ms=3000 + FINAL_HOLD_MS,
        )
        self.assertEqual(held.end_ms, 3800)
        self.assertEqual(held.metadata["text_intro"], "渐显")
        self.assertNotIn("text_outro", held.metadata)
        self.assertNotIn("text_loop", held.metadata)

    def test_role_sizes_preserve_hierarchy(self):
        self.assertLess(text_style_size(44, "subtitle"), 8.0)
        self.assertGreaterEqual(text_style_size(72, "label"), 13.0)
        self.assertGreaterEqual(text_style_size(92, "number"), 16.0)
        self.assertGreaterEqual(text_style_size(108, "title"), 19.0)

    def test_animation_duration_is_visible_and_bounded(self):
        duration = fitted_animation_duration(
            draft.IntroType.钱币遮罩,
            requested_ms=360,
            total_ms=800,
            max_fraction=0.45,
            cap_ms=900,
        )
        self.assertEqual(duration, 360)

    def test_keywords_use_warm_text_and_thick_outline_without_background(self):
        result = LayoutResult("test", Canvas(), [])
        renderer = JianyingRenderer()
        for role in ("label", "number"):
            with self.subTest(role=role):
                element = ElementLayout("keyword", "text", "常规内容", Box(72, 400, 500, 120), 0, 2000, 30, role, 82, ("常规内容",))
                segment = renderer._make_segment(element, result)
                self.assertIsNotNone(segment.border)
                self.assertIsNone(segment.shadow)
                self.assertEqual(segment.font, draft.FontType.得意黑.value)
                material = segment.export_material()
                style = json.loads(material["content"])["styles"][0]
                self.assertEqual(style["fill"]["content"]["solid"]["color"], [244 / 255, 197 / 255, 66 / 255])
                self.assertEqual(len(style["strokes"]), 1)
                self.assertAlmostEqual(style["strokes"][0]["width"], 0.024)
                self.assertNotIn("background_color", material)

    def test_keyword_material_uses_one_warm_fill_without_background(self):
        result = LayoutResult("test", Canvas(), [])
        element = ElementLayout(
            "keyword", "text", "很夸张", Box(72, 400, 500, 120), 0, 2000, 30, "label", 82, ("很夸张",)
        )
        segment = JianyingRenderer()._make_segment(element, result)
        material = segment.export_material()
        styles = json.loads(material["content"])["styles"]

        self.assertEqual(len(styles), 1)
        self.assertEqual(styles[0]["range"], [0, 3])
        self.assertEqual(styles[0]["fill"]["content"]["solid"]["color"], [244 / 255, 197 / 255, 66 / 255])
        self.assertNotIn("background_color", material)

    def test_old_keyword_font_metadata_is_replaced_by_unified_font(self):
        result = LayoutResult("test", Canvas(), [])
        for font_name in ("站酷酷黑体", "古印宋简"):
            with self.subTest(font_name=font_name):
                element = ElementLayout(
                    "keyword",
                    "text",
                    "人人可用",
                    Box(72, 400, 500, 120),
                    0,
                    2000,
                    30,
                    "label",
                    82,
                    ("人人可用",),
                    metadata={"font_name": font_name},
                )
                segment = JianyingRenderer()._make_segment(element, result)

                self.assertEqual(segment.font, draft.FontType.得意黑.value)

    def test_old_hollow_keyword_metadata_is_ignored(self):
        result = LayoutResult("test", Canvas(), [])
        element = ElementLayout(
            "keyword",
            "text",
            "重点关键词",
            Box(72, 400, 500, 120),
            0,
            2000,
            30,
            "label",
            82,
            ("重点关键词",),
            metadata={"text_color": "#1864AB", "hollow_outline": True},
        )
        segment = JianyingRenderer()._make_segment(element, result)
        material = segment.export_material()
        style = json.loads(material["content"])["styles"][0]

        self.assertEqual(style["fill"]["alpha"], 1.0)
        self.assertEqual(style["fill"]["content"]["solid"]["alpha"], 1.0)
        self.assertEqual(len(style["strokes"]), 1)
        self.assertIsNone(segment.shadow)

    def test_regular_emphasis_keyword_stays_filled_and_readable(self):
        result = LayoutResult("test", Canvas(), [])
        element = ElementLayout(
            "keyword",
            "text",
            "为何不造多核",
            Box(72, 400, 500, 120),
            0,
            2000,
            30,
            "label",
            82,
            ("为何不造多核",),
            metadata={"text_color": "#D9480F", "text_loop": "漂浮"},
        )
        segment = JianyingRenderer()._make_segment(element, result)
        style = json.loads(segment.export_material()["content"])["styles"][0]

        self.assertEqual(style["fill"]["alpha"], 1.0)
        self.assertEqual(style["fill"]["content"]["solid"]["alpha"], 1.0)
        self.assertEqual(len(style["strokes"]), 1)

    def test_subtitle_uses_theme_background_color_from_layout_metadata(self):
        result = LayoutResult("test", Canvas(), [])
        element = ElementLayout(
            "subtitle",
            "text",
            "字幕",
            Box(72, 1400, 936, 100),
            0,
            2000,
            1000,
            "subtitle",
            56,
            ("字幕",),
            metadata={
                "text_color": "#FFFFFF",
                "subtitle_background_color": "#222222",
            },
        )

        segment = JianyingRenderer()._make_segment(element, result)

        self.assertIsNotNone(segment.background)
        self.assertEqual(segment.background.color, "#222222")

    def test_global_title_bar_tracks_measured_title_width(self):
        short = global_title_bar_scale("云计算")
        long = global_title_bar_scale("一口气理清魏晋南北朝")

        self.assertLess(short, long)
        self.assertLess(long, 1.0)

    def test_compact_title_is_smaller_and_uses_a_shorter_decoration_area(self):
        regular = global_title_presentation("What is ComfyUI", 1080, 1920)
        compact = global_title_presentation("What is ComfyUI", 1080, 1920, variant="compact")

        self.assertLess(compact.style_size, regular.style_size)
        self.assertLess(compact.bar_height, regular.bar_height)

    def test_global_title_bar_accounts_for_title_letter_spacing(self):
        title = "什么云计算"
        font_path = cached_font_path(draft.FontType.雅酷黑简)
        unspaced_width = text_width(title, resolve_font(font_path, TITLE_FONT_SIZE))
        expected_spacing = round((len(title) - 1) * TITLE_FONT_SIZE * TITLE_LETTER_SPACING * 0.05)

        self.assertEqual(
            title_bar_width(title),
            unspaced_width + expected_spacing + TITLE_BAR_HORIZONTAL_PADDING * 2,
        )

    def test_landscape_title_bar_has_a_stable_colored_band(self):
        presentation = global_title_presentation("ComfyUI为啥火出圈？", 1920, 1080)

        self.assertGreaterEqual(presentation.bar_width, round(1920 * LANDSCAPE_TITLE_BAR_MIN_WIDTH_RATIO))
        portrait = global_title_presentation("ComfyUI为啥火出圈？", 1080, 1920)
        self.assertLess(presentation.style_size, portrait.style_size)

    def test_subtitle_background_has_enough_coverage(self):
        result = LayoutResult("test", Canvas(), [])
        element = ElementLayout(
            "subtitle",
            "text",
            "字幕",
            Box(72, 1400, 936, 100),
            0,
            2000,
            1000,
            "subtitle",
            56,
            ("字幕",),
            metadata={"text_color": "#FFFFFF", "subtitle_background_color": "#222222"},
        )
        segment = JianyingRenderer()._make_segment(element, result)

        self.assertEqual(segment.background.width, SUBTITLE_BACKGROUND_WIDTH)
        self.assertEqual(segment.background.height, SUBTITLE_BACKGROUND_HEIGHT)

    def test_subtitle_can_override_jianying_text_size(self):
        result = LayoutResult("test", Canvas(width=1920, height=1080), [])
        element = ElementLayout(
            "subtitle", "text", "横版字幕", Box(64, 980, 1792, 40), 0, 1000,
            1000, "subtitle", 32, ("横版字幕",),
            metadata={"jianying_text_size": 5.0},
        )

        segment = JianyingRenderer()._make_segment(element, result)

        self.assertEqual(segment.style.size, 5.0)

    def test_long_global_title_wraps_and_fits_inside_bar(self):
        presentation = global_title_presentation("GPU为什么适合训练AI？它和CPU到底差在哪")

        self.assertEqual(presentation.text.count("\n"), 1)
        self.assertIn("？\n", presentation.text)
        self.assertLess(presentation.style_size, TITLE_TEXT_STYLE_SIZE)
        self.assertLessEqual(presentation.bar_width, 936)
        self.assertGreater(presentation.bar_height, 180)

    def test_global_title_starts_in_final_state_without_keyframes(self):
        result = LayoutResult("test", Canvas(), [])
        with tempfile.TemporaryDirectory() as directory:
            path = JianyingRenderer().render(
                result,
                draft_folder=Path(directory),
                draft_name="static_title",
                global_title="什么是测试",
            )
            content = json.loads((path / "draft_content.json").read_text(encoding="utf-8"))
            self.assertTrue((path / "Resources" / "title_bar_yellow_adaptive.png").exists())
        tracks = {
            track["name"]: track
            for track in content["tracks"]
            if track["name"] in {"global_title", "global_title_bar"}
        }
        self.assertEqual(set(tracks), {"global_title", "global_title_bar"})
        self.assertTrue(all(not track["segments"][0]["common_keyframes"] for track in tracks.values()))
        title_material_id = tracks["global_title"]["segments"][0]["material_id"]
        title_material = next(item for item in content["materials"]["texts"] if item["id"] == title_material_id)
        title_style = json.loads(title_material["content"])["styles"][0]
        self.assertEqual(title_style["size"], TITLE_TEXT_STYLE_SIZE)
        self.assertEqual(title_style["font"]["id"], draft.FontType.雅酷黑简.value.resource_id)

    def test_global_title_uses_theme_text_color(self):
        result = LayoutResult("test", Canvas(), [])
        with tempfile.TemporaryDirectory() as directory:
            path = JianyingRenderer().render(
                result,
                draft_folder=Path(directory),
                draft_name="theme_title",
                global_title="白色主题",
                title_color="#112233",
            )
            content = json.loads((path / "draft_content.json").read_text(encoding="utf-8"))
        title_track = next(track for track in content["tracks"] if track["name"] == "global_title")
        material_id = title_track["segments"][0]["material_id"]
        material = next(item for item in content["materials"]["texts"] if item["id"] == material_id)
        style = json.loads(material["content"])["styles"][0]

        self.assertEqual(style["fill"]["content"]["solid"]["color"], [17 / 255, 34 / 255, 51 / 255])


if __name__ == "__main__":
    unittest.main()
