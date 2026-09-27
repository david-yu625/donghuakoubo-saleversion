from __future__ import annotations

import unittest

from ..prepare.image_prompts import (
    MAX_PROMPT_CHARS,
    build_prompt,
    collapse_remotion_rows,
    default_image_size,
    is_background_element,
    is_background_prompt,
    safe_filename,
    visual_only_content,
)


class ImagePromptStyleTest(unittest.TestCase):
    def test_remotion_collapses_each_shot_to_one_composite_row(self):
        rows = [
            {"element_id": "s1_bg01", "shot_id": "1", "type": "image", "role": "background", "content": "标题和背景", "start_ms": "0", "end_ms": "5000"},
            {"element_id": "s1_img01", "shot_id": "1", "type": "image", "role": "element", "content": "输入对象", "start_ms": "0", "end_ms": "5000"},
            {"element_id": "s1_img02", "shot_id": "1", "type": "image", "role": "element", "content": "处理结果", "start_ms": "0", "end_ms": "5000"},
            {"element_id": "s2_bg01", "shot_id": "2", "type": "image", "role": "background", "content": "第二场景", "start_ms": "5000", "end_ms": "9000"},
            {"element_id": "s2_img01", "shot_id": "2", "type": "image", "role": "element", "content": "第二主体", "start_ms": "5000", "end_ms": "9000"},
        ]

        collapsed = collapse_remotion_rows(rows)

        self.assertEqual([row["element_id"] for row in collapsed], ["s1_img01", "s2_img01"])
        self.assertEqual([row["shot_id"] for row in collapsed], ["1", "2"])
        self.assertTrue(all(row["role"] == "element" for row in collapsed))
        self.assertIn("输入对象", collapsed[0]["content"])
        self.assertIn("处理结果", collapsed[0]["content"])

    def test_background_prompt_keeps_hash_sections_and_title_rules(self):
        design = "1920*1080白板背景，顶部中间显示标题“总结丢了什么”，禁止具体插图/对象，下方和右侧保留纯白空白区域。"
        prompt = build_prompt(
            element_id="s1_bg01", role="background", content=design,
            shot_text="不会进入提示词", width=1536, height=864, orientation="横屏",
        )

        for section in ("#画布", "#背景图生成", "#图片内容", "#背景", "#目标", "#要求"):
            self.assertIn(section, prompt)
        self.assertIn(design, prompt)
        self.assertIn("标题的最后几个字可以蓝色、黄色交叉", prompt)
        self.assertIn("前面的字是黑色，不要加粗", prompt)
        self.assertIn("图片中不要出现 Excalidraw 字样", prompt)
        self.assertIn("严禁绘制任何具体对象或插图", prompt)
        self.assertIn("供后续元素图独立播放", prompt)
        self.assertIn("只能在顶部 1/5", prompt)
        self.assertIn("下方 4/5 必须是纯白空白", prompt)
        self.assertIn("以画布水平中心为轴居中对齐", prompt)
        self.assertNotIn("不会进入提示词", prompt)
        self.assertTrue(is_background_prompt(prompt))

    def test_element_prompt_keeps_hash_sections_without_title_rules(self):
        design = (
            "一组简约、线条风格的手绘图标，包括：一个闪电符号代表“电”、一个水滴代表“水”、"
            "一个带有光标箭头和齿轮的电脑显示器代表“算力”。三个图标之间用虚线箭头连接，"
            "表示“转化”和“提供”的关系"
        )
        prompt = build_prompt(
            element_id="s2_img01", role="element", content=design,
            shot_text="这段旁白不会进入图片提示词", width=1024, height=1536,
        )

        for section in ("#画布", "#元素图生成", "#图片内容", "#背景", "#目标", "#要求"):
            self.assertIn(section, prompt)
        self.assertIn(design, prompt)
        self.assertIn("图片是纯白色背景", prompt)
        self.assertIn("画笔线条稍微粗一些", prompt)
        self.assertIn("元素图生成要在图中合适位置增加关键字", prompt)
        self.assertNotIn("标题设计成一个醒目的大标题", prompt)
        self.assertNotIn("这段旁白不会进入图片提示词", prompt)
        self.assertFalse(is_background_prompt(prompt))

    def test_long_dynamic_content_is_rejected_instead_of_truncated(self):
        with self.assertRaisesRegex(ValueError, "不会截断第04步生成的图片内容"):
            build_prompt(
                element_id="s1_bg01", role="background", content="背景内容。" * 300,
                shot_text="", width=1536, height=864, orientation="横屏",
            )

    def test_landscape_uses_wide_size(self):
        prompt = build_prompt(
            element_id="s1_bg01", role="background", content="标题“测试”，1920*1080，禁止具体插图/对象，下方保留纯白空白区域。",
            shot_text="", width=1536, height=864, orientation="横屏",
        )
        self.assertEqual(default_image_size("横屏"), (1536, 864))
        self.assertIn("16:9 横屏", prompt)

    def test_element_identifiers_drive_roles_and_asset_names(self):
        self.assertTrue(is_background_element("s3_bg01"))
        self.assertFalse(is_background_element("s3_img01"))
        self.assertEqual(safe_filename("1", "s1_img02", "很长很长的图片描述"), "s1_img02.png")

    def test_visual_design_is_not_rewritten(self):
        self.assertEqual(
            visual_only_content("AI总结器把四张报告压缩成一张摘要卡"),
            "AI总结器把四张报告压缩成一张摘要卡",
        )
        self.assertEqual(visual_only_content("  一只手掌\n按下按钮  "), "一只手掌 按下按钮")

if __name__ == "__main__":
    unittest.main()
