import tempfile
import unittest
from pathlib import Path

from PIL import Image

from experiments.remotion_infinite_canvas.prepare_assets import (
    prepare_asset, read_project_captions, read_project_chapters,
    build_nodes, IMAGE_ANIMATIONS, TRANSITIONS, CAMERA_MOVES,
)


class RemotionAssetsTest(unittest.TestCase):
    def test_effect_library_is_used_across_images_and_shot_boundaries(self):
        assets = [f'image_{i:02d}.png' for i in range(25)]
        timings = {asset: {"start": i * 3, "end": (i + 1) * 3, "shot_id": str(i // 2)} for i, asset in enumerate(assets)}
        nodes = build_nodes(list(reversed(assets)), [], 75, timings, "demo")
        self.assertEqual(nodes, build_nodes(list(reversed(assets)), [], 75, timings, "demo"))
        for field, pool, offset in (("transition", TRANSITIONS, 1), ("image_animation", IMAGE_ANIMATIONS, 0), ("camera_move", CAMERA_MOVES, 1)):
            selected = [node[field] for node in nodes[offset:]]
            self.assertEqual(set(selected[:len(pool)]), set(pool))
            self.assertTrue(all(a != b for a, b in zip(selected, selected[1:])))
        self.assertEqual(nodes[0]["transition_frames"], 0)
        self.assertTrue(all(node["transition_frames"] > 0 for node in nodes[1:]))

    def test_subtitles_preserve_narration_separately_from_chapter(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            narration = "服务器收到请求后会把网页源代码作为响应发回来那是一堆HTML标签和文本"
            (project / "timeline.csv").write_text(
                f"index,text,time\n1,{narration},[0.000,5.760,5.760]\n", encoding="utf-8"
            )
            (project / "shot_timeline_source_time.csv").write_text(
                "shot_id,分镜标题,开始时间ms,结束时间ms,分镜对应原始文案内容\n"
                f"1,接收响应,0,5760,{narration}\n", encoding="utf-8"
            )
            captions = read_project_captions(project)
            self.assertEqual("".join(item["text"] for item in captions), narration)
            self.assertEqual(captions[0]["start"], 0)
            self.assertEqual(captions[-1]["end"], 5.760)
            self.assertTrue(all(a["end"] == b["start"] for a, b in zip(captions, captions[1:])))
            self.assertEqual(read_project_chapters(project)[0]["text"], "接收响应")

    def test_prefers_original_pixels_over_damaged_cutout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "originals").mkdir()
            Image.new("RGBA", (30, 20), (0, 0, 0, 0)).save(root / "image.png")
            original = Image.new("RGBA", (30, 20), (250, 248, 240, 255))
            original.putpixel((10, 10), (20, 60, 130, 255))
            original.save(root / "originals" / "image.png")
            output = root / "prepared" / "image.png"
            prepare_asset(root / "image.png", output)
            with Image.open(output) as actual:
                self.assertEqual(actual.size, original.size)
                self.assertEqual(actual.tobytes(), original.tobytes())

    def test_preserves_existing_alpha_when_original_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = Image.new("RGBA", (20, 20), (120, 180, 240, 128))
            original.save(root / "image.png")
            prepare_asset(root / "image.png", root / "prepared.png")
            with Image.open(root / "prepared.png") as actual:
                self.assertEqual(actual.tobytes(), original.tobytes())

    def test_missing_narration_timeline_does_not_substitute_headings(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                read_project_captions(Path(directory))
