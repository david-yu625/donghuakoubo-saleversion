from __future__ import annotations

import unittest
from unittest.mock import patch

from ..prepare import shot_timeline as planner


class ShotTimelineTest(unittest.TestCase):
    def setUp(self):
        self.timeline = [
            planner.TimelineRow(1, "看得见的现象", 0, 900, 900),
            planner.TimelineRow(2, "现象留下的问题", 900, 1800, 900),
            planner.TimelineRow(3, "问题的直接原因", 1800, 3000, 1200),
            planner.TimelineRow(4, "原因背后的机制", 3000, 4300, 1300),
            planner.TimelineRow(5, "机制导致的结果", 4300, 5200, 900),
        ]

    def test_step_03_only_groups_timeline_indices(self):
        self.assertIn("把配音时间线划分成语义 Shot", planner.SYSTEM_PROMPT)
        self.assertIn("不要设计图片、背景、元素", planner.SYSTEM_PROMPT)
        self.assertIn("完全服从原始文案已有的组织方式", planner.SYSTEM_PROMPT)
        self.assertEqual(
            planner.MODEL_FIELDS,
            ["shot_id", "timeline_start_index", "timeline_end_index", "shot_title"],
        )
        self.assertEqual(
            planner.SHOT_FIELDS,
            ["shot_id", "分镜标题", "开始时间ms", "结束时间ms", "分镜对应原始文案内容"],
        )

    def test_program_derives_time_and_source_text_from_timeline(self):
        shots = planner.build_shots([
            {"shot_id": "9", "timeline_start_index": "1", "timeline_end_index": "2", "shot_title": "现象与问题"},
            {"shot_id": "20", "timeline_start_index": "3", "timeline_end_index": "5", "shot_title": "原因与结果"},
        ], self.timeline)

        self.assertEqual(shots[0], {
            "shot_id": "1",
            "分镜标题": "现象与问题",
            "开始时间ms": "0",
            "结束时间ms": "1800",
            "分镜对应原始文案内容": "看得见的现象现象留下的问题",
        })
        self.assertEqual((shots[1]["开始时间ms"], shots[1]["结束时间ms"]), ("1800", "5200"))

    def test_gap_or_overlap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "遗漏、重叠或顺序错误"):
            planner.build_shots([
                {"shot_id": "1", "timeline_start_index": "1", "timeline_end_index": "2", "shot_title": "前半段"},
                {"shot_id": "2", "timeline_start_index": "2", "timeline_end_index": "5", "shot_title": "后半段"},
            ], self.timeline)

    def test_last_group_must_cover_the_full_timeline(self):
        with self.assertRaisesRegex(ValueError, "全部句子"):
            planner.build_shots([
                {"shot_id": "1", "timeline_start_index": "1", "timeline_end_index": "4", "shot_title": "未覆盖结尾"},
            ], self.timeline)

    def test_invalid_model_partition_is_sent_back_for_correction(self):
        invalid = (
            "shot_id,timeline_start_index,timeline_end_index,shot_title\n"
            "1,1,2,前半段\n"
            "2,4,5,后半段\n"
        )
        valid = (
            "shot_id,timeline_start_index,timeline_end_index,shot_title\n"
            "1,1,2,前半段\n"
            "2,3,5,后半段\n"
        )
        with patch.object(planner, "generate_with_model", side_effect=[invalid, valid]) as generate:
            shots = planner.generate_validated_shots(
                timeline=self.timeline,
                user_prompt="user",
                api_key="key",
                model="model",
                base_url="url",
                max_tokens=100,
                max_attempts=3,
            )

        self.assertEqual(generate.call_count, 2)
        self.assertEqual(len(shots), 2)
        self.assertIn("遗漏、重叠或顺序错误", generate.call_args_list[1].kwargs["validation_error"])

    def test_dry_run_covers_every_timeline_row_once(self):
        shots = planner.build_shots(planner.generate_dry_run(self.timeline), self.timeline)
        self.assertGreaterEqual(len(shots), 1)
        self.assertEqual(shots[0]["开始时间ms"], "0")
        self.assertEqual(shots[-1]["结束时间ms"], "5200")

    def test_single_semantic_stage_is_allowed_when_it_covers_everything(self):
        shots = planner.build_shots([
            {"shot_id": "1", "timeline_start_index": "1", "timeline_end_index": "5", "shot_title": "完整解释"},
        ], self.timeline)

        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["分镜对应原始文案内容"], "".join(row.text for row in self.timeline))


if __name__ == "__main__":
    unittest.main()
