import unittest

from remotion_pipeline.layouts.world import layout_world
from remotion_pipeline.pipeline.scene_facts import build_scene_facts, split_sentences
from remotion_pipeline.renderers.remotion import make_manifest
from remotion_pipeline.visual_direction.plan import direct_scenes
from remotion_pipeline.contracts import VISUAL_STYLE_ID
from remotion_pipeline.pipeline.density import audit_density


class PipelineLayerTests(unittest.TestCase):
    def setUp(self):
        self.script = {
            "title": "Example",
            "shots": [
                {"id": "s1", "title": "Open", "voice": "Open the site", "keyword": "open", "visual": "browser"},
                {"id": "s2", "title": "Read", "voice": "Read the response", "keyword": "response", "visual": "html"},
                {"id": "s3", "title": "Extract", "voice": "Extract the value", "keyword": "value", "visual": "extract"},
                {"id": "s4", "title": "Finish", "voice": "Finish with care", "keyword": "care", "visual": "shield"},
            ],
        }

    def test_scene_facts_have_timing_but_no_presentation_geometry(self):
        facts = build_scene_facts(self.script, 12.0)
        self.assertEqual(facts["shots"][0]["start"], 0.6)
        self.assertAlmostEqual(facts["shots"][0]["end"], facts["shots"][1]["start"])
        self.assertNotIn("x", facts["shots"][0])
        self.assertNotIn("accent", facts["shots"][0])

    def test_captions_follow_sentence_beats_inside_each_scene(self):
        script = {
            "title": "Example",
            "shots": [
                {"id": "s1", "title": "Open", "voice": "先打开页面。然后查看结果！", "keyword": "页面", "visual": "browser"},
                {"id": "s2", "title": "Read", "voice": "继续读取。", "keyword": "读取", "visual": "html"},
                {"id": "s3", "title": "Extract", "voice": "提取数据。", "keyword": "数据", "visual": "extract"},
                {"id": "s4", "title": "Finish", "voice": "完成操作。", "keyword": "完成", "visual": "shield"},
            ],
        }
        facts = build_scene_facts(script, 8.0)
        self.assertEqual(split_sentences(script["shots"][0]["voice"]), ["先打开页面。", "然后查看结果！"])
        self.assertEqual([item["text"] for item in facts["captions"][:2]], ["先打开页面。", "然后查看结果！"])
        self.assertEqual(facts["captions"][0]["start"], facts["shots"][0]["start"])
        self.assertEqual(facts["captions"][1]["end"], facts["shots"][0]["end"])
        self.assertAlmostEqual(facts["captions"][0]["end"], facts["captions"][1]["start"], places=3)

    def test_captions_have_a_bounded_fallback_when_source_has_no_punctuation(self):
        parts = split_sentences("这是一个没有标点的长段落用于测试字幕不会整段同时出现")
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 24 for part in parts))

    def test_project_timeline_is_the_source_of_truth_for_caption_times(self):
        # The adapter consumes this same three-column shape from step 02.
        import csv
        import tempfile
        from pathlib import Path
        from scripts.build_from_project import read_project_captions

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with (project / "timeline.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["index", "text", "time"])
                writer.writeheader()
                writer.writerow({"index": "1", "text": "第一句", "time": "[0.000,2.500,2.500]"})
                writer.writerow({"index": "2", "text": "第二句", "time": "[2.500,4.000,1.500]"})
            self.assertEqual(read_project_captions(project, 4.0), [
                {"start": 0.0, "end": 2.5, "text": "第一句"},
                {"start": 2.5, "end": 4.0, "text": "第二句"},
            ])

    def test_renderer_joins_image_and_future_video_without_replanning(self):
        facts = build_scene_facts(self.script, 12.0)
        plan = direct_scenes(facts)
        layout = layout_world(facts)
        manifest = make_manifest(
            facts, plan, layout,
            {"s1": {"asset": "s1.png", "mediaType": "image", "styleId": VISUAL_STYLE_ID},
             "s2": {"asset": "s2.mp4", "mediaType": "video", "styleId": VISUAL_STYLE_ID},
             "s3": {"asset": "s3.png", "mediaType": "image", "styleId": VISUAL_STYLE_ID},
             "s4": {"asset": "s4.png", "mediaType": "image", "styleId": VISUAL_STYLE_ID}},
            "audio/narration.wav",
        )
        self.assertEqual(manifest["shots"][1]["mediaType"], "video")
        self.assertEqual(manifest["shots"][3]["camera_move"], "resolve")
        self.assertEqual(manifest["shots"][1]["x"], layout["shots"][1]["x"])

    def test_density_audit_points_to_upstream_storyboard_and_keeps_renderer_sparse(self):
        facts = build_scene_facts(self.script, 20.0)
        audit = audit_density(self.script, facts, {"s1": {}, "s2": {}}, {
            "shots": [{"asset_count": 3}, {"asset_count": 2}],
        })
        self.assertEqual(audit["sourceLayer"], "prepare.storyboard")
        self.assertEqual(audit["remotionPolicy"], "one sparse composite illustration per semantic scene; canvas chrome and text are renderer layers")


if __name__ == "__main__":
    unittest.main()
