from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ..core.models import Box, Canvas, ElementLayout, LayoutResult
from ..renderers.jianying_renderer import JianyingRenderer
from ..renderers.sound_effects import (
    SoundAsset,
    SoundEvent,
    choose_sound_asset,
    load_reference_sounds,
    load_sound_library,
)


class SoundEffectsTest(unittest.TestCase):
    def test_reference_draft_parser_reads_names_paths_and_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp3"
            source.write_bytes(b"sound")
            draft_info = root / "draft_info.json"
            draft_info.write_text(json.dumps({
                "materials": {
                    "audios": [{
                        "name": "啵1",
                        "path": str(source),
                        "duration": 366666,
                    }],
                },
            }, ensure_ascii=False), encoding="utf-8")

            sounds = load_reference_sounds(draft_info)

        self.assertEqual(sounds["啵1"].path, source)
        self.assertEqual(sounds["啵1"].duration_ms, 366)

    def test_bundled_library_is_preferred_over_reference_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "audio" / "sound_effect" / "library" / "pop_1.mp3"
            local.parent.mkdir(parents=True)
            local.write_bytes(b"local")
            reference_dir = root / "audio" / "sound_effect" / "音频和文字"
            reference_dir.mkdir(parents=True)
            reference_dir.joinpath("draft_info.json").write_text(
                json.dumps({"materials": {"audios": []}}),
                encoding="utf-8",
            )

            library = load_sound_library(root)

        self.assertEqual(library["pop"][0].path, local)

    def test_asset_choice_is_deterministic_and_avoids_immediate_repeat(self):
        event = SoundEvent("keyword", "pop", 1200)
        assets = (
            SoundAsset("one", Path("one.mp3")),
            SoundAsset("two", Path("two.mp3")),
        )
        library = {"pop": assets}
        first = choose_sound_asset(event, library)
        second = choose_sound_asset(event, library)
        alternate = choose_sound_asset(event, library, previous_path=first.path if first else None)

        self.assertEqual(first, second)
        self.assertIsNotNone(alternate)
        self.assertNotEqual(first.path, alternate.path)

    def test_rendered_sound_starts_at_animation_time(self):
        element = ElementLayout(
            "keyword",
            "text",
            "关键词",
            Box(72, 400, 500, 140),
            750,
            2500,
            30,
            "label",
            82,
            ("关键词",),
            metadata={"sound_effect": "pop"},
        )
        result = LayoutResult("test", Canvas(), [element])
        with tempfile.TemporaryDirectory() as directory:
            path = JianyingRenderer().render(
                result,
                draft_folder=Path(directory),
                draft_name="sound_timing",
            )
            content = json.loads((path / "draft_content.json").read_text(encoding="utf-8"))

        track = next(track for track in content["tracks"] if track["name"] == "sound_effects")
        self.assertEqual(len(track["segments"]), 1)
        self.assertEqual(track["segments"][0]["target_timerange"]["start"], 750000)
        self.assertLessEqual(track["segments"][0]["volume"], 0.30)


if __name__ == "__main__":
    unittest.main()
