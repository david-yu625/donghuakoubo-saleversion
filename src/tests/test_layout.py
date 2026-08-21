from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from ..core.geometry import inside, overlaps
from ..core.models import Box, SceneContent, SceneElement, Theme, canvas_for_orientation
from ..layouts.engine import LayoutEngine
from ..layouts.regions import subtitle_area, visual_stage
from ..layouts.templates import (
    balanced_keyword_text,
    emphasis_font_size,
    keyword_font_size,
    mixed_phase_slots,
    stack_slots,
)


class LayoutEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = LayoutEngine()
        self.content = SceneContent(
            title="真正决定效率的，不是工具，而是流程",
            subtitle="先优化工作方式，再增加工具",
            images=("missing-a.png", "missing-b.png", "missing-c.png"),
        )

    def test_auto_selects_history_for_multiple_images(self):
        result = self.engine.auto_build(self.content)
        self.assertEqual(result.template, "focus_history")
        self.assertEqual(len(result.elements), 4)

    def test_landscape_focus_history_uses_side_history_rail(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("focus_history", SceneContent(
            images=("missing-a.png", "missing-b.png"),
            duration_ms=3000,
        ))
        focus = next(element for element in result.elements if element.element_id == "focus_image")
        history = next(element for element in result.elements if element.role == "history")

        self.assertGreater(focus.box.height, 500)
        self.assertGreater(history.box.height, 240)
        self.assertGreater(history.box.height, result.canvas.height * 0.2)
        self.assertGreater(history.box.x, focus.box.right)
        self.assertFalse(overlaps(focus.box, history.box))

    def test_background_stack_keeps_board_visible_while_elements_enter(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("background_stack", SceneContent(
            elements=(
                SceneElement("s1_bg01", "image", "background.png", 0, 4000, role="background"),
                SceneElement("s1_img01", "image", "first.png", 800, 4000, role="overlay"),
                SceneElement("s1_img02", "image", "second.png", 1600, 4000, role="overlay"),
            ),
            duration_ms=4000,
        ))
        by_id = {element.element_id: element for element in result.elements}
        background = by_id["s1_bg01"]
        first = by_id["s1_img01"]
        second = by_id["s1_img02"]

        self.assertEqual(background.role, "background")
        self.assertEqual((background.start_ms, background.end_ms), (0, 4000))
        self.assertEqual(first.metadata["stage_background"], "whiteboard_background")
        self.assertEqual(second.metadata["stage_background"], "whiteboard_background")
        self.assertGreater(background.end_ms, first.start_ms)
        self.assertGreaterEqual(first.start_ms, 800)
        self.assertGreater(second.start_ms, first.start_ms)
        self.assertGreater(first.z_index, background.z_index)
        self.assertGreater(second.z_index, first.z_index)
        self.assertGreater(background.end_ms, second.start_ms)
        self.assertIn("layout_keyframes", first.metadata)
        self.assertGreater(first.metadata["layout_keyframes"][0]["offset_ms"], 0)
        first_target = Box(*first.metadata["layout_keyframes"][0]["box"])
        self.assertGreater(first.box.width, first_target.width)
        self.assertFalse(overlaps(first_target, second.box))
        self.assertLess(first_target.center_x, result.canvas.width / 2)
        self.assertGreater(second.box.center_x, result.canvas.width / 2)

    def test_landscape_stack_slots_have_product_recipes_for_one_to_six_images(self):
        region = Box(64, 318, 1792, 638)
        for variant in range(3):
            with self.subTest(variant=variant):
                single = stack_slots(1, region, landscape=True, gap=18, variant=variant)
                self.assertEqual(len(single), 1)
                self.assertAlmostEqual(single[0].center_x, region.center_x, delta=1)
                self.assertAlmostEqual(single[0].center_y, region.center_y, delta=1)

                pair = stack_slots(2, region, landscape=True, gap=18, variant=variant)
                self.assertEqual(len(pair), 2)
                self.assertLess(pair[0].center_x, region.center_x)
                self.assertGreater(pair[1].center_x, region.center_x)

                triple = stack_slots(3, region, landscape=True, gap=18, variant=variant)
                self.assertEqual(len(triple), 3)
                self.assertGreaterEqual(max(item.width for item in triple), round(region.width * 0.54))

                quad = stack_slots(4, region, landscape=True, gap=18, variant=variant)
                self.assertEqual(len(quad), 4)
                self.assertGreaterEqual(max(item.width for item in quad), round(region.width * 0.49))
                self.assertGreater(len({item.center_y for item in quad}), 1)

                for count in (5, 6):
                    slots = stack_slots(count, region, landscape=True, gap=18, variant=variant)
                    self.assertEqual(len(slots), count)
                    self.assertTrue(all(
                        item.x >= region.x and item.y >= region.y
                        and item.right <= region.right and item.bottom <= region.bottom
                        for item in slots
                    ))
                    for first_index, first in enumerate(slots):
                        for second in slots[first_index + 1:]:
                            self.assertFalse(overlaps(first, second))

                for slots in (pair, quad):
                    self.assertEqual(min(item.x for item in slots), region.x)
                    self.assertEqual(max(item.right for item in slots), region.right)

                # The first three-image recipe uses a deliberate 3% outer
                # margin so its two support images do not feel pinned to the
                # canvas edge. The dominant image still reaches the far edge.
                self.assertLessEqual(
                    min(item.x for item in triple),
                    region.x + round(region.width * 0.04),
                )
                self.assertEqual(max(item.right for item in triple), region.right)

                for slots in (pair, triple, quad):
                    for index, first in enumerate(slots):
                        self.assertGreater(first.width, 0)
                        self.assertGreater(first.height, 0)
                        self.assertGreaterEqual(first.x, region.x)
                        self.assertGreaterEqual(first.y, region.y)
                        self.assertLessEqual(first.right, region.right)
                        self.assertLessEqual(first.bottom, region.bottom)
                        for second in slots[index + 1:]:
                            self.assertFalse(overlaps(first, second))

    def test_single_background_stack_element_is_centered_before_reflow(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("background_stack", SceneContent(
            elements=(
                SceneElement("s2_bg01", "image", "background.png", 0, 4000, role="background"),
                SceneElement("s2_img01", "image", "first.png", 0, 4000, role="overlay"),
            ),
            duration_ms=4000,
        ))
        overlay = next(item for item in result.elements if item.role == "overlay")
        region_center = (result.canvas.content_left + result.canvas.content_right) / 2
        self.assertAlmostEqual(overlay.box.center_x, region_center, delta=1)
        # A lone asset keeps its aspect ratio, so a 4:3 illustration fills the
        # available stage by height rather than being distorted to full width.
        stage_height = round(result.canvas.height * 0.20)
        subtitle_height = subtitle_area(result.canvas).y
        self.assertGreater(overlay.box.height, (subtitle_height - stage_height) * 0.85)

    def test_background_stack_reserves_top_fifth_for_background_text(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("background_stack", SceneContent(
            elements=(
                SceneElement("s1_bg01", "image", "background.png", 0, 4000, role="background"),
                SceneElement("s1_img01", "image", "first.png", 0, 4000, role="overlay"),
                SceneElement("s1_img02", "image", "second.png", 1000, 4000, role="overlay"),
            ),
            duration_ms=4000,
        ))
        top_boundary = round(result.canvas.height * 0.20)
        for element in result.elements:
            if element.role != "overlay":
                continue
            self.assertGreaterEqual(element.box.y, top_boundary)
            for keyframe in element.metadata.get("layout_keyframes", []):
                self.assertGreaterEqual(keyframe["box"][1], top_boundary)

    def test_background_stack_moves_elements_below_measured_background_content(self):
        with tempfile.TemporaryDirectory() as directory:
            background = Path(directory) / "s1_bg01.png"
            background.write_bytes(b"placeholder")
            (Path(directory) / "background_content_bounds.json").write_text(
                '{"s1_bg01.png": {"content_bottom_ratio": 0.31}}', encoding="utf-8"
            )
            engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
            result = engine.build("background_stack", SceneContent(
                elements=(
                    SceneElement("s1_bg01", "image", str(background), 0, 4000, role="background"),
                    SceneElement("s1_img01", "image", "first.png", 0, 4000, role="overlay"),
                ),
                duration_ms=4000,
            ))
        overlay = next(item for item in result.elements if item.role == "overlay")
        self.assertGreaterEqual(overlay.box.y, round(result.canvas.height * 0.31) + 28)

    def test_background_stack_falls_back_when_measured_content_fills_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            background = Path(directory) / "s3_bg01.png"
            background.write_bytes(b"placeholder")
            (Path(directory) / "background_content_bounds.json").write_text(
                '{"s3_bg01.png": {"content_bottom_ratio": 0.996528}}', encoding="utf-8"
            )
            engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
            result = engine.build("background_stack", SceneContent(
                elements=(
                    SceneElement("s3_bg01", "image", str(background), 0, 4000, role="background"),
                    SceneElement("s3_img01", "image", "first.png", 0, 4000, role="overlay"),
                ),
                duration_ms=4000,
            ))
        overlay = next(item for item in result.elements if item.role == "overlay")
        self.assertGreaterEqual(overlay.box.y, round(result.canvas.height * 0.20))

    def test_background_stack_rotates_landscape_compositions_by_shot(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        results = []
        for shot_id in ("s1", "s2", "s3"):
            result = engine.build("background_stack", SceneContent(
                elements=(
                    SceneElement(f"{shot_id}_bg01", "image", "background.png", 0, 6000, role="background"),
                    SceneElement(f"{shot_id}_img01", "image", "first.png", 0, 6000, role="overlay"),
                    SceneElement(f"{shot_id}_img02", "image", "second.png", 0, 6000, role="overlay"),
                    SceneElement(f"{shot_id}_img03", "image", "third.png", 0, 6000, role="overlay"),
                ),
                duration_ms=6000,
            ))
            by_id = {item.element_id: item for item in result.elements}
            results.append((by_id[f"{shot_id}_img01"], by_id[f"{shot_id}_img02"]))
        # The first visual intentionally starts centered in every shot. Its
        # final/reflow position is what varies after later visuals arrive.
        final_positions = {
            tuple(item[0].metadata.get("layout_keyframes", [])[-1]["box"])
            for item in results
        }
        self.assertEqual(len(final_positions), 3)
        self.assertEqual(len({item[0].animation.enter for item in results}), 3)

    def test_first_landscape_variant_places_two_supporting_images_left_of_main_image(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("background_stack", SceneContent(
            elements=(
                SceneElement("s1_bg01", "image", "background.png", 0, 6000, role="background"),
                SceneElement("s1_img01", "image", "first.png", 0, 6000, role="overlay"),
                SceneElement("s1_img02", "image", "second.png", 0, 6000, role="overlay"),
                SceneElement("s1_img03", "image", "third.png", 0, 6000, role="overlay"),
            ),
            duration_ms=6000,
        ))
        by_id = {item.element_id: item for item in result.elements}
        first = Box(*by_id["s1_img01"].metadata["layout_keyframes"][-1]["box"])
        second = Box(*by_id["s1_img02"].metadata.get("layout_keyframes", [{"box": list(by_id["s1_img02"].box.__dict__.values())}])[-1]["box"])
        third = by_id["s1_img03"].box
        self.assertLess(first.right, third.x)
        self.assertLess(second.right, third.x)
        self.assertLess(first.y, second.y)

    def test_second_landscape_variant_clears_pair_before_result_image(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("background_stack", SceneContent(
            elements=(
                SceneElement("s2_bg01", "image", "background.png", 0, 7000, role="background"),
                SceneElement("s2_img01", "image", "first.png", 0, 7000, role="overlay"),
                SceneElement("s2_img02", "image", "second.png", 0, 7000, role="overlay"),
                SceneElement("s2_img03", "image", "result.png", 0, 7000, role="overlay"),
            ),
            duration_ms=7000,
        ))
        by_id = {item.element_id: item for item in result.elements}
        self.assertEqual(by_id["s2_img01"].end_ms, by_id["s2_img02"].end_ms)
        self.assertEqual(by_id["s2_img03"].start_ms, by_id["s2_img01"].end_ms)
        self.assertEqual(by_id["s2_img03"].end_ms, 7000)

    def test_third_landscape_variant_relays_images_instead_of_accumulating(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("background_stack", SceneContent(
            elements=(
                SceneElement("s3_bg01", "image", "background.png", 0, 7000, role="background"),
                SceneElement("s3_img01", "image", "first.png", 0, 7000, role="overlay"),
                SceneElement("s3_img02", "image", "second.png", 0, 7000, role="overlay"),
                SceneElement("s3_img03", "image", "third.png", 0, 7000, role="overlay"),
            ),
            duration_ms=7000,
        ))
        overlays = sorted((item for item in result.elements if item.role == "overlay"), key=lambda item: item.start_ms)
        self.assertLess(overlays[0].end_ms, 7000)
        self.assertLess(overlays[1].end_ms, 7000)
        self.assertEqual(overlays[-1].end_ms, 7000)

    def test_background_stack_rejects_separate_text_elements(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        with self.assertRaisesRegex(ValueError, "只接受背景图和元素图"):
            engine.build("background_stack", SceneContent(
                elements=(
                    SceneElement("s1_bg01", "image", "background.png", 0, 4000, role="background"),
                    SceneElement("s1_img01", "image", "first.png", 0, 4000, role="overlay"),
                    SceneElement("s1_txt01", "text", "体积膨胀", 800, 4000),
                ),
                duration_ms=4000,
            ))

    def test_background_stack_sequences_elements_that_share_the_same_start_time(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("background_stack", SceneContent(
            elements=(
                SceneElement("s1_bg01", "image", "background.png", 0, 6000, role="background"),
                SceneElement("s1_img01", "image", "first.png", 0, 6000, role="overlay"),
                SceneElement("s1_img02", "image", "second.png", 0, 6000, role="overlay"),
                SceneElement("s1_img03", "image", "third.png", 0, 6000, role="overlay"),
            ),
            duration_ms=6000,
        ))
        overlays = sorted(
            (element for element in result.elements if element.role == "overlay"),
            key=lambda item: item.start_ms,
        )
        self.assertEqual(len({element.start_ms for element in overlays}), 3)
        self.assertTrue(all(
            first.start_ms < second.start_ms
            for first, second in zip(overlays, overlays[1:])
        ))
        final_boxes = [
            Box(*element.metadata["layout_keyframes"][-1]["box"])
            if element.metadata.get("layout_keyframes") else element.box
            for element in overlays
        ]
        self.assertGreater(final_boxes[-1].width, final_boxes[0].width)
        self.assertNotEqual(overlays[1].box.y, overlays[2].box.y)

    def test_landscape_board_overview_places_three_major_points_in_order(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("board_overview", SceneContent(
            elements=(
                SceneElement("s1_bg01", "image", "background.png", 0, 4000, role="background"),
                SceneElement("s1_img01", "image", "relation.png", 0, 4000, role="overlay"),
                SceneElement("s1_txt01", "text", "1. 看到现象", 200, 4000),
                SceneElement("s1_txt02", "text", "2. 解释原因", 500, 4000),
                SceneElement("s1_txt03", "text", "3. 得出结果", 800, 4000),
                SceneElement("s1_txt04", "text", "4. 开始行动", 1100, 4000),
            ),
            duration_ms=4000,
            semantic_role="overview",
        ))
        labels = sorted((item for item in result.elements if item.role == "board_major_point"), key=lambda item: item.box.x)

        self.assertEqual(result.template, "board_overview")
        self.assertEqual([item.content for item in labels], ["1. 看到现象", "2. 解释原因", "3. 得出结果", "4. 开始行动"])
        self.assertTrue(all(inside(item.box, result.canvas) for item in result.elements if item.role != "background"))
        self.assertFalse(any(overlaps(first.box, second.box) for first, second in zip(labels, labels[1:])))

    def test_landscape_board_section_pairs_each_label_above_its_diagram(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("board_section", SceneContent(
            elements=(
                SceneElement("s2_bg01", "image", "background.png", 0, 4000, role="background"),
                SceneElement("s2_img01", "image", "first.png", 0, 4000, role="overlay"),
                SceneElement("s2_txt01", "text", "1.1 常态下沉", 0, 4000),
                SceneElement("s2_img02", "image", "second.png", 1400, 4000, role="overlay"),
                SceneElement("s2_txt02", "text", "1.2 冰是例外", 1400, 4000),
            ),
            duration_ms=4000,
            semantic_role="board_section",
        ))
        by_id = {item.element_id: item for item in result.elements}

        self.assertEqual(result.template, "board_section")
        self.assertLessEqual(by_id["s2_txt01"].box.bottom, by_id["s2_img01"].box.y)
        self.assertLessEqual(by_id["s2_txt02"].box.bottom, by_id["s2_img02"].box.y)
        self.assertLess(by_id["s2_img01"].box.right, by_id["s2_img02"].box.x)
        self.assertEqual(result.warnings, [])

    def test_board_section_reserves_a_fixed_major_title_band(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("board_section", SceneContent(
            elements=(
                SceneElement("s2_bg01", "image", "background.png", 0, 4000, role="background"),
                SceneElement("s2_title01", "text", "1. 提问方向错了", 0, 4000, role="major_title"),
                SceneElement("s2_img01", "image", "first.png", 300, 4000, role="subpoint_diagram"),
                SceneElement("s2_txt01", "text", "1.1 问题太空", 300, 4000, role="subpoint_label"),
                SceneElement("s2_img02", "image", "second.png", 1600, 4000, role="subpoint_diagram"),
                SceneElement("s2_txt02", "text", "1.2 没有约束", 1600, 4000, role="subpoint_label"),
            ),
            duration_ms=4000,
            semantic_role="board_section",
        ))
        by_id = {item.element_id: item for item in result.elements}

        self.assertEqual(by_id["s2_title01"].role, "board_major_title")
        self.assertLess(by_id["s2_title01"].box.bottom, by_id["s2_txt01"].box.y)
        self.assertLessEqual(by_id["s2_txt01"].box.bottom, by_id["s2_img01"].box.y)
        self.assertEqual(result.warnings, [])

    def test_landscape_regions_have_a_non_overlapping_bottom_subtitle_lane(self):
        canvas = canvas_for_orientation("横屏")
        stage = visual_stage(canvas)
        subtitles = subtitle_area(canvas)

        self.assertEqual(stage, Box(64, 254, 1792, 702))
        self.assertEqual(subtitles.center_y, 1017)
        self.assertGreaterEqual(subtitles.y, stage.bottom)
        self.assertEqual(canvas.height - subtitles.bottom, 32)

    def test_landscape_timeline_flow_keeps_keywords_in_side_rail(self):
        engine = LayoutEngine(canvas=canvas_for_orientation("横屏"))
        result = engine.build("timeline_flow", SceneContent(
            elements=(
                SceneElement("main", "image", "missing-main.png", 0, 4000),
                SceneElement("support", "image", "missing-support.png", 0, 4000),
                SceneElement("keyword", "text", "核心关键词", 0, 4000),
            ),
            duration_ms=4000,
            semantic_role="sequence",
        ))
        by_id = {element.element_id: element for element in result.elements}

        self.assertGreater(by_id["main"].box.height, 440)
        self.assertGreater(by_id["keyword"].box.height, 200)
        self.assertFalse(overlaps(by_id["main"].box, by_id["keyword"].box))
        self.assertFalse(overlaps(by_id["support"].box, by_id["keyword"].box))

    def test_keywords_are_smaller_and_single_images_receive_more_space(self):
        theme = Theme()
        self.assertEqual(keyword_font_size(theme), 99)
        self.assertEqual(emphasis_font_size(theme), 126)

        region = Box(72, 396, 936, 1084)
        side_images, side_keywords = mixed_phase_slots(1, 1, region, 0)
        vertical_images, vertical_keywords = mixed_phase_slots(1, 1, region, 1)
        vertical_top_images, vertical_top_keywords = mixed_phase_slots(1, 1, region, 3)
        self.assertGreaterEqual(side_images[0].width, side_keywords[0].width * 2)
        self.assertGreater(vertical_images[0].height, vertical_keywords[0].height * 2)
        self.assertGreater(vertical_top_images[0].height, vertical_top_keywords[0].height * 2)

    def test_split_compare_does_not_create_empty_image_elements(self):
        result = self.engine.build("split_compare", SceneContent(
            labels=("主动使用", "不断提问"),
            images=("one-image.png",),
            duration_ms=3000,
            semantic_role="compare",
        ))

        images = [element for element in result.elements if element.element_type == "image"]
        self.assertEqual([element.content for element in images], ["one-image.png"])
        self.assertTrue(any("没有图片" in warning for warning in result.warnings))

    def test_all_boxes_stay_inside_safe_area(self):
        result = self.engine.build("title_image", self.content)
        self.assertTrue(all(inside(item.box, result.canvas) for item in result.elements))

    def test_title_falls_back_for_long_text(self):
        content = SceneContent(title="这是一段很长很长很长很长很长很长很长很长很长很长的动画知识标题")
        result = self.engine.build("title_image", content)
        title = next(item for item in result.elements if item.element_id == "title")
        self.assertLessEqual(len(title.lines), 3)
        self.assertTrue(title.font_size <= self.engine.theme.title_font_size)

    def test_geometry_overlap(self):
        self.assertTrue(overlaps(Box(0, 0, 100, 100), Box(90, 90, 100, 100)))
        self.assertFalse(overlaps(Box(0, 0, 100, 100), Box(100, 0, 100, 100)))

    def test_timeline_flow_preserves_all_source_times(self):
        content = SceneContent(
            elements=(
                SceneElement("first", "image", "missing-a.png", 0, 1200),
                SceneElement("second", "image", "missing-b.png", 1200, 2800),
                SceneElement("label", "text", "第二阶段", 1200, 2800),
            ),
            duration_ms=2800,
            semantic_role="sequence",
        )
        result = self.engine.build("timeline_flow", content)
        by_id = {element.element_id: element for element in result.elements}
        self.assertEqual(set(by_id), {"first", "second", "label"})
        self.assertEqual((by_id["first"].start_ms, by_id["first"].end_ms), (0, 1200))
        self.assertEqual((by_id["second"].start_ms, by_id["second"].end_ms), (1200, 2800))
        self.assertFalse(overlaps(by_id["second"].box, by_id["label"].box))
        self.assertGreaterEqual(by_id["label"].font_size, 99)

    def test_keyword_remains_visible_until_related_image_ends(self):
        content = SceneContent(
            elements=(
                SceneElement("image", "image", "missing.png", 0, 3000),
                SceneElement("label", "text", "云计算", 400, 1500),
            ),
            duration_ms=3000,
            semantic_role="sequence",
        )
        result = self.engine.build("timeline_flow", content)
        label = next(element for element in result.elements if element.element_id == "label")
        self.assertEqual((label.start_ms, label.end_ms), (400, 3000))

    def test_single_image_gets_visual_priority_over_keyword(self):
        content = SceneContent(
            elements=(
                SceneElement("d", "image", "missing.png", 0, 3000),
                SceneElement("label", "text", "云计算", 0, 3000),
            ),
            duration_ms=3000,
            semantic_role="sequence",
        )
        result = self.engine.build("timeline_flow", content)
        by_id = {element.element_id: element for element in result.elements}
        self.assertGreater(by_id["d"].box.width, by_id["label"].box.width)
        self.assertGreaterEqual(by_id["d"].box.width, 500)
        self.assertFalse(overlaps(by_id["d"].box, by_id["label"].box))

    def test_timeline_flow_three_image_slots_do_not_overlap(self):
        content = SceneContent(
            elements=tuple(
                SceneElement(f"image_{index}", "image", f"missing-{index}.png", 0, 2000)
                for index in range(3)
            ),
            duration_ms=2000,
        )
        images = self.engine.build("timeline_flow", content).elements
        for index, first in enumerate(images):
            for second in images[index + 1:]:
                self.assertFalse(overlaps(first.box, second.box))

    def test_timeline_flow_arranges_number_and_tag_as_peers(self):
        content = SceneContent(
            elements=(
                SceneElement("tag", "image", "missing-tag.png", 0, 2000, "价格标签牌 一百两"),
                SceneElement("amount", "text", "一百两", 0, 2000, "一百两"),
            ),
            duration_ms=2000,
        )
        result = self.engine.build("timeline_flow", content)
        tag = next(element for element in result.elements if element.element_id == "tag")
        amount = next(element for element in result.elements if element.element_id == "amount")
        self.assertFalse(overlaps(amount.box, tag.box))
        self.assertEqual(amount.role, "number")
        self.assertGreaterEqual(amount.font_size, 126)

    def test_timeline_flow_reuses_stable_slots_for_sequential_elements(self):
        elements = []
        for index in range(4):
            start_ms = index * 1000
            end_ms = start_ms + 900
            elements.extend((
                SceneElement(f"image_{index}", "image", f"missing-{index}.png", start_ms, end_ms),
                SceneElement(f"label_{index}", "text", f"关键词{index}", start_ms, end_ms),
            ))
        result = self.engine.build("timeline_flow", SceneContent(elements=tuple(elements), duration_ms=4000))
        by_id = {element.element_id: element for element in result.elements}
        keyword_boxes = []
        for index in range(4):
            image = by_id[f"image_{index}"]
            label = by_id[f"label_{index}"]
            self.assertFalse(overlaps(image.box, label.box))
            keyword_boxes.append((label.box.x, label.box.y, label.box.width, label.box.height))
        self.assertEqual(len(set(keyword_boxes)), 1)

    def test_timeline_flow_separates_elements_with_staggered_overlapping_times(self):
        content = SceneContent(
            elements=(
                SceneElement("main", "image", "missing-main.png", 0, 4000),
                SceneElement("support", "image", "missing-support.png", 1500, 4000),
                SceneElement("keyword", "text", "核心关键词", 1800, 4000),
            ),
            duration_ms=4000,
            semantic_role="sequence",
        )
        result = self.engine.build("timeline_flow", content)
        by_id = {element.element_id: element for element in result.elements}
        main_target = Box(*by_id["main"].metadata["layout_keyframes"][0]["box"])
        self.assertFalse(overlaps(main_target, by_id["support"].box))
        self.assertFalse(overlaps(by_id["main"].box, by_id["keyword"].box))
        self.assertFalse(overlaps(by_id["support"].box, by_id["keyword"].box))
        self.assertEqual(by_id["main"].role, "main")
        self.assertEqual(by_id["support"].role, "support")

    def test_timeline_flow_centers_main_image_until_late_support_appears(self):
        content = SceneContent(
            elements=(
                SceneElement("main", "image", "missing-main.png", 0, 5000),
                SceneElement("support", "image", "missing-support.png", 2400, 5000),
                SceneElement("keyword", "text", "核心区别", 400, 5000),
            ),
            duration_ms=5000,
            semantic_role="sequence",
        )
        result = self.engine.build("timeline_flow", content)
        by_id = {element.element_id: element for element in result.elements}
        main = by_id["main"]
        support = by_id["support"]
        keyframe = main.metadata["layout_keyframes"][0]
        target = Box(*keyframe["box"])

        self.assertEqual(keyframe["offset_ms"], 2400)
        self.assertGreater(main.box.width, target.width)
        self.assertAlmostEqual(main.box.center_x, self.engine.canvas.width / 2, delta=20)
        self.assertFalse(overlaps(target, support.box))

    def test_timeline_flow_progressively_reflows_three_images(self):
        content = SceneContent(
            elements=(
                SceneElement("main", "image", "missing-main.png", 0, 5000),
                SceneElement("second", "image", "missing-second.png", 1500, 5000),
                SceneElement("third", "image", "missing-third.png", 3000, 5000),
                SceneElement("keyword", "text", "三个阶段", 300, 5000),
            ),
            duration_ms=5000,
            semantic_role="sequence",
        )
        by_id = {item.element_id: item for item in self.engine.build("timeline_flow", content).elements}
        main = by_id["main"]
        second = by_id["second"]
        third = by_id["third"]
        main_targets = [Box(*item["box"]) for item in main.metadata["layout_keyframes"]]
        second_target = Box(*second.metadata["layout_keyframes"][0]["box"])

        self.assertEqual([item["offset_ms"] for item in main.metadata["layout_keyframes"]], [1500, 3000])
        self.assertGreater(main.box.width, main_targets[0].width)
        self.assertGreater(main_targets[1].width, second_target.width)
        self.assertFalse(overlaps(main_targets[1], second_target))
        self.assertFalse(overlaps(main_targets[1], third.box))
        self.assertFalse(overlaps(second_target, third.box))

    def test_timeline_flow_four_images_gives_main_full_height(self):
        content = SceneContent(
            elements=tuple(
                SceneElement(f"image_{index}", "image", f"missing-{index}.png", index * 1000, 5000)
                for index in range(4)
            ),
            duration_ms=5000,
            semantic_role="sequence",
        )
        by_id = {item.element_id: item for item in self.engine.build("timeline_flow", content).elements}
        main_final = Box(*by_id["image_0"].metadata["layout_keyframes"][-1]["box"])
        support_final = Box(*by_id["image_1"].metadata["layout_keyframes"][-1]["box"])

        self.assertGreater(by_id["image_0"].box.width, main_final.width)
        self.assertGreater(main_final.height, support_final.height)

    def test_large_keywords_wrap_without_splitting_numbers(self):
        content = SceneContent(
            elements=(
                SceneElement("image_1", "image", "missing-1.png", 0, 2000),
                SceneElement("image_2", "image", "missing-2.png", 0, 2000),
                SceneElement("image_3", "image", "missing-3.png", 0, 2000),
                SceneElement("label_1", "text", "借1个果子", 0, 2000),
                SceneElement("label_2", "text", "卖得100两", 0, 2000),
            ),
            duration_ms=2000,
        )
        result = self.engine.build("timeline_flow", content)
        first = next(element for element in result.elements if element.element_id == "label_1")
        second = next(element for element in result.elements if element.element_id == "label_2")
        self.assertEqual(first.lines, ("借1个果子",))
        self.assertEqual(second.lines, ("卖得100两",))
        self.assertEqual(first.font_size, second.font_size)
        self.assertLessEqual(first.font_size, 99)

    def test_large_keyword_wrapping_prefers_semantic_boundaries(self):
        theme = Theme()
        self.assertEqual(
            balanced_keyword_text("价格高 会跌", max_width=570, max_height=1100, font_size=163, max_lines=3, theme=theme),
            "价格高\n会跌",
        )
        self.assertEqual(
            balanced_keyword_text("风险 上涨亏损", max_width=570, max_height=1100, font_size=163, max_lines=3, theme=theme),
            "风险\n上涨\n亏损",
        )
        self.assertEqual(
            balanced_keyword_text("三个月后还", max_width=896, max_height=550, font_size=211, max_lines=3, theme=theme),
            "三个月\n后还",
        )
        self.assertEqual(
            balanced_keyword_text("还1个果子", max_width=570, max_height=1100, font_size=163, max_lines=3, theme=theme),
            "还1个\n果子",
        )


if __name__ == "__main__":
    unittest.main()
