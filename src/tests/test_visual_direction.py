from __future__ import annotations

import unittest

from ..core.models import Box, Canvas, ElementLayout, LayoutResult, SceneElement, SceneFacts
from ..renderers.jianying_renderer import draft
from ..settings import DEFAULT_KEYWORD_COLOR, DEFAULT_KEYWORD_FONT, KEYWORD_TEXT_COLORS
from ..keyword_style import semantic_keyword_runs, semantic_keyword_style
from ..visual_direction.apply import apply_visual_plan, distributed_choices, distributed_keyword_text_colors
from ..visual_direction.director import VisualDirector
from ..visual_direction.presets import (
    EMPHASIS_TEXT_LOOPS,
    LABEL_TEXT_INTROS,
    MOTION_PRESETS,
    TEXT_OUTROS,
    TITLE_TEXT_INTROS,
    TYPOGRAPHY_PRESETS,
    SCENE_TRANSITION_INTROS,
    VIDEO_EFFECTS,
    VIDEO_INTROS,
    VIDEO_OUTROS,
)


class VisualDirectorTest(unittest.TestCase):
    def test_single_image_scenes_rotate_layouts(self):
        director = VisualDirector()
        templates = [director.plan(scene(index, image_count=1)).layout.template for index in range(3)]
        self.assertEqual(len(set(templates)), 3)

    def test_multi_image_scenes_do_not_repeat_immediately(self):
        director = VisualDirector()
        templates = [director.plan(scene(index, image_count=3)).layout.template for index in range(6)]
        for previous, current in zip(templates, templates[1:]):
            self.assertNotEqual(previous, current)

    def test_sequence_uses_timeline_flow(self):
        facts = scene(1, image_count=3, semantic_role="sequence")
        self.assertEqual(VisualDirector().plan(facts).layout.template, "timeline_flow")

    def test_background_and_overlay_images_use_background_stack(self):
        facts = scene(1, image_count=0)
        facts = SceneFacts(
            **{**facts.__dict__, "elements": (
                SceneElement("s1_bg01", "image", "background.png", 0, 3000, role="background"),
                SceneElement("s1_img01", "image", "overlay.png", 800, 3000, role="overlay"),
            )},
        )

        self.assertEqual(VisualDirector().plan(facts).layout.template, "background_stack")

    def test_background_stays_stable_while_overlay_gets_visual_directives(self):
        facts = scene(1, image_count=0)
        facts = SceneFacts(**{**facts.__dict__, "elements": (
            SceneElement("s1_bg01", "image", "background.png", 0, 3000, role="background"),
            SceneElement("s1_img01", "image", "overlay.png", 800, 3000, role="overlay"),
        )})
        result = LayoutResult(
            "background_stack",
            Canvas(),
            [
                ElementLayout("bg", "image", "background.png", Box(0, 0, 1080, 1920), 0, 3000, 10, "background", metadata={"stack_role": "background"}),
                ElementLayout("overlay", "image", "overlay.png", Box(100, 400, 600, 600), 800, 3000, 20, "overlay", metadata={"stack_role": "overlay"}),
            ],
        )

        styled = apply_visual_plan(result, VisualDirector().plan(facts))
        background, overlay = styled.elements

        self.assertIn(background.metadata["video_intro"], SCENE_TRANSITION_INTROS)
        self.assertEqual(background.metadata["hold_motion"], "static")
        self.assertNotIn("video_effect", background.metadata)
        self.assertEqual(background.metadata["scene_transition"], "background_intro")
        self.assertIn(overlay.metadata["video_intro"], VIDEO_INTROS)
        self.assertIn(overlay.metadata["video_outro"], VIDEO_OUTROS)
        self.assertNotIn("video_effect", overlay.metadata)
        self.assertEqual(VIDEO_EFFECTS, ())

    def test_overview_scene_uses_board_overview_layout(self):
        facts = scene(0, image_count=0, semantic_role="overview")
        facts = SceneFacts(**{**facts.__dict__, "elements": (
            SceneElement("s1_bg01", "image", "background.png", 0, 3000, role="background"),
            SceneElement("s1_img01", "image", "relation.png", 0, 3000, role="overlay"),
            SceneElement("s1_txt01", "text", "1. 第一层", 0, 3000),
        )})
        self.assertEqual(VisualDirector().plan(facts).layout.template, "board_overview")

    def test_board_text_roles_use_dark_ink_on_white_board(self):
        facts = scene(0, image_count=0, semantic_role="overview")
        plan = VisualDirector().plan(facts)
        result = LayoutResult(
            "board_overview",
            Canvas(),
            [ElementLayout(
                "major", "text", "1. 大点", Box(0, 0, 400, 100), 0, 2000,
                40, "board_major_point", 90, ("1. 大点",),
            )],
        )

        styled = apply_visual_plan(result, plan)

        self.assertEqual(styled.elements[0].metadata["text_color"], "#111111")

    def test_numbered_section_uses_board_section_layout(self):
        facts = scene(1, image_count=0, semantic_role="board_section")
        facts = SceneFacts(**{**facts.__dict__, "elements": (
            SceneElement("s2_bg01", "image", "background.png", 0, 3000, role="background"),
            SceneElement("s2_img01", "image", "diagram.png", 0, 3000, role="overlay"),
            SceneElement("s2_txt01", "text", "1.1 小点", 0, 3000),
        )})
        self.assertEqual(VisualDirector().plan(facts).layout.template, "board_section")

    def test_compare_requires_explicit_compare_role(self):
        facts = scene(1, image_count=2, semantic_role="compare", label_count=2)
        self.assertEqual(VisualDirector().plan(facts).layout.template, "split_compare")

    def test_compare_with_one_image_uses_single_image_layout(self):
        facts = scene(1, image_count=1, semantic_role="compare", label_count=2)
        self.assertNotEqual(VisualDirector().plan(facts).layout.template, "split_compare")

    def test_typography_rotates_across_scenes(self):
        director = VisualDirector()
        plans = [director.plan(scene(index, image_count=1)) for index in range(len(TYPOGRAPHY_PRESETS))]
        self.assertEqual(len({plan.typography.preset for plan in plans}), len(TYPOGRAPHY_PRESETS))
        self.assertEqual(plans[0].typography.subtitle_font, "ResourceHanRoundedCN_Nl")

    def test_all_preset_resources_exist_in_jianying_metadata(self):
        for typography in TYPOGRAPHY_PRESETS:
            for font_name in (
                typography.title_font,
                typography.label_font,
                typography.number_font,
                typography.subtitle_font,
            ):
                self.assertIsNotNone(getattr(draft.FontType, font_name, None), font_name)
        for motion in MOTION_PRESETS:
            self.assertIsNotNone(getattr(draft.TextIntro, motion.title_enter, None), motion.title_enter)
            self.assertIsNotNone(getattr(draft.TextIntro, motion.label_enter, None), motion.label_enter)
            self.assertIsNotNone(getattr(draft.IntroType, motion.image_enter, None), motion.image_enter)
            self.assertIsNotNone(getattr(draft.OutroType, motion.image_exit, None), motion.image_exit)
            self.assertIsNotNone(getattr(draft.TextIntro, motion.subtitle_enter, None), motion.subtitle_enter)
            self.assertIsNotNone(getattr(draft.TextOutro, motion.text_exit, None), motion.text_exit)
        for name in TITLE_TEXT_INTROS + LABEL_TEXT_INTROS:
            self.assertIsNotNone(getattr(draft.TextIntro, name, None), name)
        for name in TEXT_OUTROS:
            self.assertIsNotNone(getattr(draft.TextOutro, name, None), name)
        for name in EMPHASIS_TEXT_LOOPS:
            self.assertIsNotNone(getattr(draft.TextLoopAnim, name, None), name)
        for name in VIDEO_INTROS:
            self.assertIsNotNone(getattr(draft.IntroType, name, None), name)
        for name in VIDEO_OUTROS:
            self.assertIsNotNone(getattr(draft.OutroType, name, None), name)

    def test_typography_presets_do_not_use_dotted_keyword_font(self):
        self.assertTrue(
            all(typography.label_font != "古印宋简" for typography in TYPOGRAPHY_PRESETS)
        )

    def test_distributed_choices_are_random_without_adjacent_repeats(self):
        first = distributed_choices(VIDEO_INTROS, 40, "scene_001")
        second = distributed_choices(VIDEO_INTROS, 40, "scene_001")
        self.assertTrue(set(first).issubset(set(VIDEO_INTROS)))
        self.assertTrue(set(second).issubset(set(VIDEO_INTROS)))
        self.assertTrue(all(previous != current for previous, current in zip(first, first[1:])))
        self.assertTrue(all(previous != current for previous, current in zip(second, second[1:])))

    def test_video_motion_presets_exclude_wipes_flips_and_scan_light(self):
        all_motion = (*VIDEO_INTROS, *VIDEO_OUTROS, *VIDEO_EFFECTS)
        forbidden = ("雨刷", "翻入", "翻出", "旋转", "折叠", "扫描光条")
        self.assertFalse(any(token in name for name in all_motion for token in forbidden))

    def test_keywords_use_stable_varied_colors_without_backgrounds(self):
        plan = VisualDirector().plan(scene(2, image_count=1, label_count=2))
        result = LayoutResult(
            "test",
            Canvas(),
            [
                ElementLayout("label_0", "text", "GPU并行计算", Box(72, 400, 400, 100), 0, 3000, 30, "label", 82),
                ElementLayout("label_1", "text", "消耗惊人", Box(72, 520, 400, 100), 0, 3000, 30, "label", 82),
            ],
        )
        applied = apply_visual_plan(result, plan)
        labels = [element for element in applied.elements if element.element_type == "text"]
        self.assertTrue(all(element.metadata["font_name"] == DEFAULT_KEYWORD_FONT for element in labels))
        self.assertTrue(all(element.metadata["text_color"] in KEYWORD_TEXT_COLORS for element in labels))
        self.assertNotEqual(labels[0].metadata["text_color"], labels[1].metadata["text_color"])
        self.assertTrue(all("keyword_color_role" not in element.metadata for element in labels))
        self.assertTrue(all("keyword_background_color" not in element.metadata for element in labels))
        self.assertTrue(all(element.metadata["text_intro"] in LABEL_TEXT_INTROS for element in labels))
        self.assertTrue(all("text_outro" not in element.metadata for element in labels))
        self.assertTrue(all("text_loop" not in element.metadata for element in labels))
        self.assertTrue(all("hollow_outline" not in element.metadata for element in labels))

    def test_keyword_colors_are_stable_and_avoid_previous_scene_color(self):
        first = distributed_keyword_text_colors(8, "scene_001", avoid="#F4C542")
        second = distributed_keyword_text_colors(8, "scene_001", avoid="#F4C542")

        self.assertEqual(first, second)
        self.assertNotEqual(first[0], "#F4C542")
        self.assertTrue(all(color in KEYWORD_TEXT_COLORS for color in first))
        self.assertTrue(all(previous != current for previous, current in zip(first, first[1:])))

    def test_semantic_keyword_colors_are_meaningful_and_deterministic(self):
        cases = {
            "耗电少很多": ("positive", "#F4C542"),
            "训练成本惊人": ("risk", "#EE7A7A"),
            "数万亿次每秒": ("quantity", "#F28C28"),
            "GPU并行计算": ("technology", "#252525"),
            "训练的本质": ("technology", "#252525"),
            "常规内容": ("neutral", DEFAULT_KEYWORD_COLOR),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(semantic_keyword_style(text), expected)

    def test_semantic_keyword_runs_split_one_phrase_by_meaning(self):
        self.assertEqual(
            [(run.start, run.end, run.category) for run in semantic_keyword_runs("很夸张")],
            [(0, 1, "neutral"), (1, 3, "risk")],
        )
        self.assertEqual(
            [(run.start, run.end, run.category) for run in semantic_keyword_runs("数十亿个参数")],
            [(0, 3, "quantity"), (3, 4, "neutral"), (4, 6, "technology")],
        )

    def test_visual_plan_assigns_semantic_sound_cues(self):
        plan = VisualDirector().plan(scene(2, image_count=1, label_count=1))
        result = LayoutResult(
            "test",
            Canvas(),
            [
                ElementLayout("image", "image", "image.png", Box(72, 400, 400, 400), 0, 2000, 20, "main"),
                ElementLayout("label", "text", "关键词", Box(500, 400, 400, 120), 0, 2000, 30, "label", 82),
            ],
        )
        applied = apply_visual_plan(result, plan)
        cues = {element.element_id: element.metadata.get("sound_cue") for element in applied.elements}
        self.assertIn(cues["image"], {"pop", "swish", "reveal"})
        self.assertIn(cues["label"], {"pop", "swish", "chime"})


def scene(index: int, *, image_count: int, semantic_role: str = "explain", label_count: int = 0) -> SceneFacts:
    elements = tuple(
        SceneElement(f"image_{item}", "image", f"image_{item}.png", 0, 3000)
        for item in range(image_count)
    ) + tuple(
        SceneElement(f"label_{item}", "text", f"标签 {item}", 0, 3000)
        for item in range(label_count)
    )
    return SceneFacts(
        scene_id=f"scene_{index}",
        scene_index=index,
        start_ms=0,
        end_ms=3000,
        duration_ms=3000,
        title=f"场景 {index}",
        source_text=f"场景 {index}",
        elements=elements,
        semantic_role=semantic_role,
    )


if __name__ == "__main__":
    unittest.main()
