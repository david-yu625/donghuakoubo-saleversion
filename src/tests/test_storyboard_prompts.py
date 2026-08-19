from __future__ import annotations

import unittest
from unittest.mock import patch

from ..prepare import storyboard_prompts as planner


class StoryboardPromptsTest(unittest.TestCase):
    def setUp(self):
        self.shots = [{
            "shot_id": "1",
            "分镜标题": "一句话说清",
            "开始时间ms": "100",
            "结束时间ms": "3100",
            "分镜对应原始文案内容": "云计算就是把电脑的能力像水电一样租给你用。",
        }]

    def complete_plan(self):
        return [{
            "header": "【标题1】",
            "background": "把电脑能力像水电一样按需使用",
            "elements": [
                "一台服务器与水龙头、电源插座并列，表现可按需取得的能力",
                "服务器资源经过管线流向用户电脑，呈现资源从供应方交付给使用者",
            ],
        }]

    def test_prompt_uses_title_content_separator(self):
        prompt = planner.build_user_prompt(self.shots, "横屏")
        self.assertIn("#输入", prompt)
        self.assertIn("标题1（元素图数量要求：恰好 2 张）：一句话说清|||云计算就是把电脑的能力像水电一样租给你用。", prompt)

    def test_contract_requires_background_and_at_least_two_elements(self):
        for section in ("#目标", "#背景", "#要求", "#初始化", "#输出格式"):
            self.assertIn(section, planner.SYSTEM_PROMPT)
        self.assertIn("1920*1080", planner.SYSTEM_PROMPT)
        self.assertIn("输入中指定的 N 条“元素图：”", planner.SYSTEM_PROMPT)
        self.assertIn("文案相关内容在背景图中体现，就不需要在图片元素中体现", planner.SYSTEM_PROMPT)
        self.assertIn("文案在图片元素中体现，就不要在背景元素中体现", planner.SYSTEM_PROMPT)
        self.assertIn("禁止绘制任何具体对象", planner.SYSTEM_PROMPT)
        self.assertIn("纯白空白区域", planner.SYSTEM_PROMPT)

    def test_rows_are_normalized_and_staged(self):
        rows = planner.prepare_rows_from_content_plans(self.complete_plan(), self.shots)
        self.assertEqual([row["element_id"] for row in rows], ["s1_bg01", "s1_img01", "s1_img02"])
        self.assertEqual(rows[0]["start_ms"], "100")
        self.assertGreater(int(rows[2]["start_ms"]), 100)

    def test_fewer_than_two_elements_is_rejected(self):
        plan = self.complete_plan()
        plan[0]["elements"] = plan[0]["elements"][:1]
        with self.assertRaisesRegex(ValueError, "至少需要 2 条元素图内容"):
            planner.parse_model_content("【标题1】\n背景图：一句话\n元素图：步骤一", self.shots)

    def test_long_shot_requires_more_element_images(self):
        shot = dict(self.shots[0], **{
            "分镜对应原始文案内容": "这是一个很长的技术解释，包含输入、处理、结果、限制和应用场景五个独立的视觉信息。" * 3,
            "结束时间ms": "36000",
        })
        self.assertEqual(planner.required_element_count(shot), 5)
        raw = "【标题1】\n背景图：核心要点\n" + "\n".join(
            f"元素图：独立视觉步骤{i}" for i in range(1, 5)
        )
        with self.assertRaisesRegex(ValueError, "至少需要 5 条元素图内容"):
            planner.parse_model_content(raw, [shot])

    def test_element_count_scales_from_two_to_five(self):
        cases = (
            ("简短说明" * 4, 5000, 2),
            ("中等长度说明" * 12, 14000, 3),
            ("较长技术说明" * 20, 22000, 4),
            ("超长流程说明" * 30, 30000, 5),
        )
        for narration, duration_ms, expected in cases:
            with self.subTest(expected=expected):
                shot = dict(self.shots[0], **{
                    "分镜对应原始文案内容": narration,
                    "开始时间ms": "0",
                    "结束时间ms": str(duration_ms),
                })
                self.assertEqual(planner.required_element_count(shot), expected)

    def test_background_must_include_original_title(self):
        rows = planner.prepare_rows_from_content_plans(self.complete_plan(), self.shots)
        self.assertIn("标题“一句话说清”", rows[0]["content"])
        self.assertIn("1920*1080", rows[0]["content"])

    def test_model_returns_content_not_csv(self):
        raw = (
            "【标题1】\n"
            "背景图：把电脑能力像水电一样按需使用\n"
            "元素图：一台服务器与水龙头、电源插座并列，表现可按需取得的能力\n"
            "元素图：服务器资源经过管线流向用户电脑，呈现资源从供应方交付给使用者\n"
        )
        plan = planner.parse_model_content(raw, self.shots)
        rows = planner.prepare_rows_from_content_plans(plan, self.shots)
        self.assertEqual(rows[0]["element_id"], "s1_bg01")
        self.assertEqual(rows[1]["shot_id"], "1")
        self.assertEqual(rows[1]["type"], "image")
        self.assertEqual(rows[1]["role"], "element")

    def test_invalid_output_is_retried(self):
        invalid = "【标题1】\n背景图：按需使用\n元素图：步骤一"
        valid = (
            "【标题1】\n背景图：把电脑能力像水电一样按需使用\n"
            "元素图：一台服务器与水龙头、电源插座并列，表现可按需取得的能力\n"
            "元素图：服务器资源经过管线流向用户电脑，呈现资源从供应方交付给使用者"
        )
        outputs = [invalid, valid]
        with patch.object(planner, "generate_with_model", side_effect=outputs) as generate:
            rows = planner.generate_validated_rows(
                shots=self.shots, system_prompt="system", user_prompt="user", api_key="key",
                model="model", base_url="url", max_tokens=1000, max_attempts=2,
            )
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(len(rows), 3)

    def test_dry_run_obeys_new_shape(self):
        rows = planner.prepare_rows_from_content_plans(planner.generate_dry_run(self.shots), self.shots)
        self.assertEqual([row["role"] for row in rows], ["background", "element", "element"])


if __name__ == "__main__":
    unittest.main()
