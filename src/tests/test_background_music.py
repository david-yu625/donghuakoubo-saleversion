from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from ..core.models import Box, Canvas, ElementLayout, LayoutResult
from ..prepare.background_music import (
    BACKGROUND_MUSIC_NAME,
    BACKGROUND_MUSIC_SOURCE_META_NAME,
    ensure_project_background_music,
)
from ..renderers.jianying_renderer import BACKGROUND_MUSIC_VOLUME, FINAL_HOLD_MS, JianyingRenderer


class BackgroundMusicTest(unittest.TestCase):
    def test_source_audio_is_extracted_once_to_project_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "audio" / "bgm" / "bgm2[Sub Title].mp3"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"video-with-audio")
            project = root / "output" / "topic"

            def fake_ffmpeg(args, **kwargs):
                Path(args[-1]).write_bytes(b"prepared-audio")
                return subprocess.CompletedProcess(args, 0, "", "")

            with patch("src.prepare.background_music.shutil.which", return_value="ffmpeg"), patch(
                "src.prepare.background_music.subprocess.run",
                side_effect=fake_ffmpeg,
            ) as run:
                path = ensure_project_background_music(project, root)
                os.utime(path, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns + 1))
                second = ensure_project_background_music(project, root)
                source_metadata_exists = (
                    project / "prepared_assets" / BACKGROUND_MUSIC_SOURCE_META_NAME
                ).exists()

        self.assertEqual(path, project / "prepared_assets" / BACKGROUND_MUSIC_NAME)
        self.assertTrue(source_metadata_exists)
        self.assertEqual(second, path)
        self.assertEqual(run.call_count, 1)

    def test_changing_default_source_invalidates_existing_prepared_music(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_source = root / "audio" / "bgm" / "old.mp4"
            second_source = root / "audio" / "bgm" / "bgm1.mp4"
            first_source.parent.mkdir(parents=True)
            first_source.write_bytes(b"old-music")
            second_source.write_bytes(b"new-music")
            project = root / "output" / "topic"

            def fake_ffmpeg(args, **kwargs):
                Path(args[-1]).write_bytes(Path(args[args.index("-i") + 1]).read_bytes())
                return subprocess.CompletedProcess(args, 0, "", "")

            with patch("src.prepare.background_music.shutil.which", return_value="ffmpeg"), patch(
                "src.prepare.background_music.subprocess.run",
                side_effect=fake_ffmpeg,
            ) as run:
                ensure_project_background_music(project, root, source=first_source)
                result = ensure_project_background_music(project, root, source=second_source)
                result_bytes = result.read_bytes()

        self.assertEqual(result_bytes, b"new-music")
        self.assertEqual(run.call_count, 2)

    def test_missing_background_music_source_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                ensure_project_background_music(root / "output" / "topic", root)

    def test_renderer_loops_short_music_on_a_dedicated_low_volume_track(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            music = root / "music.wav"
            write_silent_wave(music, duration_ms=500)
            element = ElementLayout(
                "keyword",
                "text",
                "关键词",
                Box(72, 400, 500, 140),
                0,
                1300,
                30,
                "label",
                82,
                ("关键词",),
            )
            result = LayoutResult("test", Canvas(), [element])
            path = JianyingRenderer().render(
                result,
                draft_folder=root,
                draft_name="bgm_loop",
                background_music_path=music,
                include_sound_effects=False,
            )
            content = json.loads((path / "draft_content.json").read_text(encoding="utf-8"))

        track = next(track for track in content["tracks"] if track["name"] == "background_music")
        expected_duration_ms = 1300 + FINAL_HOLD_MS
        expected_starts = list(range(0, expected_duration_ms, 500))
        self.assertEqual(len(track["segments"]), len(expected_starts))
        self.assertEqual(
            [segment["target_timerange"]["start"] for segment in track["segments"]],
            [start * 1000 for start in expected_starts],
        )
        self.assertEqual(
            sum(segment["target_timerange"]["duration"] for segment in track["segments"]),
            expected_duration_ms * 1000,
        )
        self.assertTrue(all(segment["volume"] == BACKGROUND_MUSIC_VOLUME for segment in track["segments"]))


def write_silent_wave(path: Path, *, duration_ms: int) -> None:
    sample_rate = 8000
    frame_count = round(sample_rate * duration_ms / 1000)
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(sample_rate)
        file.writeframes(b"\x00\x00" * frame_count)


if __name__ == "__main__":
    unittest.main()
