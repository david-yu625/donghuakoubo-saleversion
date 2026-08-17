from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ..application.project_compiler import (
    build_subtitle_elements,
    distribute_subtitle_timing,
    split_subtitle_text,
    subtitle_display_width,
    without_opening_title_subtitle,
)
from ..core.models import LayoutResult
from ..layouts.engine import LayoutEngine
from ..renderers.jianying_renderer import JianyingRenderer, NARRATION_SUBTITLE_TRACK


class SemanticSubtitleTest(unittest.TestCase):
    def test_split_prefers_punctuation_and_semantic_actions(self):
        cases = {
            "唐僧取经路上，听说人参果能长生不老。": [
                "唐僧取经路上",
                "听说人参果能长生不老",
            ],
            "于是他找镇元大仙，先借一个果子卖掉，拿到一百两。": [
                "于是他找镇元大仙",
                "先借一个果子卖掉",
                "拿到一百两",
            ],
            "唐僧用六十两买回一个果子还给大仙。": [
                "唐僧用六十两买回一个果子",
                "还给大仙",
            ],
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(split_subtitle_text(source), expected)

    def test_split_chunks_stay_within_one_line_width(self):
        chunks = split_subtitle_text("这就是做空：先借来卖掉，等跌了再买回还掉。")
        self.assertEqual(chunks, ["这就是做空", "先借来卖掉", "等跌了再买回还掉"])
        self.assertTrue(all(subtitle_display_width(chunk) <= 14 for chunk in chunks))
        self.assertTrue(all("\n" not in chunk for chunk in chunks))

    def test_short_lead_in_is_kept_with_its_time_phrase(self):
        self.assertEqual(
            split_subtitle_text("果然，两个月后果子价格跌到六十两。"),
            ["果然两个月后", "果子价格跌到六十两"],
        )

    def test_timing_is_contiguous_and_preserves_source_range(self):
        chunks = ["于是他找镇元大仙", "先借一个果子卖掉", "拿到一百两。"]
        timings = distribute_subtitle_timing(chunks, 10580, 14520)
        self.assertEqual(timings[0][0], 10580)
        self.assertEqual(timings[-1][1], 14520)
        self.assertTrue(all(left[1] == right[0] for left, right in zip(timings, timings[1:])))
        self.assertTrue(all(start < end for start, end in timings))

    def test_built_subtitles_are_single_line_and_non_overlapping(self):
        engine = LayoutEngine()
        elements = build_subtitle_elements([
            ("于是他找镇元大仙，先借一个果子卖掉，拿到一百两。", 1000, 5000),
            ("唐僧用六十两买回一个果子还给大仙。", 5200, 8000),
        ], engine)
        self.assertTrue(all(len(element.lines) == 1 for element in elements))
        self.assertTrue(all(element.lines[0] == element.content for element in elements))
        ordered = sorted(elements, key=lambda element: element.start_ms)
        self.assertTrue(all(left.end_ms <= right.start_ms for left, right in zip(ordered, ordered[1:])))

    def test_opening_title_row_is_removed_from_narration_subtitles(self):
        rows = [
            ("GPU为什么适合训练AI", 0, 1800),
            ("接下来解释CPU和GPU的区别", 1800, 3600),
        ]

        self.assertEqual(without_opening_title_subtitle(rows, rows[0][0]), rows[1:])

    def test_renderer_uses_one_non_wrapping_subtitle_track(self):
        engine = LayoutEngine()
        elements = build_subtitle_elements([
            ("这是第一条很长的字幕，需要按照语义切分。", 0, 2200),
        ], engine)
        result = LayoutResult("subtitle_test", engine.canvas, elements)

        with tempfile.TemporaryDirectory() as directory:
            path = JianyingRenderer().render(
                result,
                draft_folder=Path(directory),
                draft_name="subtitle_test",
            )
            content = json.loads((path / "draft_content.json").read_text(encoding="utf-8"))

        subtitle_tracks = [track for track in content["tracks"] if track["name"] == NARRATION_SUBTITLE_TRACK]
        self.assertEqual(len(subtitle_tracks), 1)
        self.assertEqual(len(subtitle_tracks[0]["segments"]), len(elements))
        self.assertTrue(all(material["type"] == "text" for material in content["materials"]["texts"]))


if __name__ == "__main__":
    unittest.main()
