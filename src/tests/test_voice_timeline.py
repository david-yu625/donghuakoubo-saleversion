from __future__ import annotations

import base64
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from ..prepare import voice_timeline as voice


class FakeTtsResponse:
    status_code = 200
    text = ""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def iter_lines(self, decode_unicode: bool = True):
        return iter(self.lines)


class VoiceTimelineTest(unittest.TestCase):
    def test_short_video_voice_profile_keeps_expression_while_increasing_pace(self):
        profile = voice.DEFAULT_NARRATION_VOICE_PROFILE
        filters = voice.narration_master_filters(profile)

        self.assertEqual(profile.tts_speed_ratio, 1.10)
        self.assertEqual(profile.master_tempo_ratio, 1.12)
        self.assertEqual(profile.sentence_pause_seconds, 0.0)
        self.assertEqual(voice.DEFAULT_NARRATION_EMOTION, "surprised")
        self.assertEqual(voice.DEFAULT_NARRATION_EMOTION_SCALE, 2.0)
        self.assertIn("highpass=f=80", filters)
        self.assertIn("equalizer=f=3200:t=q:w=1:g=1.5", filters)
        self.assertIn("threshold=-18.0dB:ratio=2.4:attack=12.0:release=90.0", filters)
        self.assertIn("loudnorm=I=-14.0:TP=-1.0:LRA=7.0", filters)
        self.assertAlmostEqual(voice.db_to_linear(2.2), 1.2882, places=4)

    def test_full_tts_text_adds_questions_turns_and_sentence_boundaries(self):
        text = voice.join_for_full_tts([
            "AI训练为什么这么耗电",
            "你可能以为只是机器开得久",
            "这个解释并不完整",
            "但真正原因藏在计算量里",
            "每一步都要调整大量参数",
            "这就是训练耗电的原因",
        ])

        self.assertEqual(
            text,
            "AI训练为什么这么耗电？你可能以为只是机器开得久，这个解释并不完整。"
            "但真正原因藏在计算量里。每一步都要调整大量参数，这就是训练耗电的原因。",
        )
        self.assertIn("自然、有交流感", voice.DEFAULT_NARRATION_STYLE_INSTRUCTION)
        self.assertIn("语调起伏鲜明", voice.DEFAULT_NARRATION_STYLE_INSTRUCTION)
        self.assertIn("必须像真人自然说话", voice.DEFAULT_NARRATION_STYLE_INSTRUCTION)
        self.assertEqual(
            voice.ensure_tts_punctuation("这个数字听起来很夸张", index=1, total=3),
            "这个数字听起来很夸张！",
        )

    def test_science_voice_defaults_to_shuangkuai_sisi_2(self):
        self.assertEqual(
            voice.DEFAULT_TTS_SPEAKER,
            "zh_female_shuangkuaisisi_uranus_bigtts",
        )
        self.assertEqual(
            voice.resolve_tts_speaker("female_04_shuangkuaisisi"),
            voice.DEFAULT_TTS_SPEAKER,
        )

    def test_seed_tts_request_uses_pcm_context_and_native_timestamps(self):
        pcm = b"\x00\x00" * 240
        response = FakeTtsResponse([
            json.dumps({"code": 0, "data": base64.b64encode(pcm).decode("ascii")}),
            json.dumps({
                "code": 0,
                "subtitles": [
                    {"text": "你", "start_time": 0, "end_time": 100},
                    {"text": "好", "start_time": 100, "end_time": 200},
                ],
            }, ensure_ascii=False),
            json.dumps({"code": 20000000}),
        ])

        with tempfile.TemporaryDirectory() as directory, patch.object(
            voice.requests,
            "post",
            return_value=response,
        ) as post:
            output = Path(directory) / "speech.wav"
            timed_chars = voice.synthesize_sentence_doubao_v3(
                "你好",
                output,
                api_key="key",
                speaker="female_04_shuangkuaisisi",
                resource_id="seed-tts-2.0",
                speed_ratio=1.0,
                emotion="surprised",
                emotion_scale=2.0,
                context_texts=("科普口播",),
                audio_format="pcm",
                sample_rate=24000,
                enable_subtitle=True,
            )

            request = post.call_args.kwargs["json"]["req_params"]
            self.assertEqual(request["speaker"], voice.DEFAULT_TTS_SPEAKER)
            self.assertEqual(request["context_texts"], ["科普口播"])
            self.assertTrue(request["enable_subtitle"])
            self.assertEqual(request["audio_params"]["format"], "pcm")
            self.assertEqual(request["audio_params"]["emotion"], "surprised")
            self.assertEqual(request["audio_params"]["emotion_scale"], 2.0)
            with wave.open(str(output), "rb") as audio:
                self.assertEqual(audio.getframerate(), 24000)
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)

        self.assertEqual([item.char for item in timed_chars], ["你", "好"])
        self.assertAlmostEqual(timed_chars[-1].end_seconds, 0.2)

    def test_seed_tts_retries_read_timeout_and_uses_separate_timeouts(self):
        pcm = b"\x00\x00" * 240
        response = FakeTtsResponse([
            json.dumps({"code": 0, "data": base64.b64encode(pcm).decode("ascii")}),
            json.dumps({"code": 20000000}),
        ])

        with tempfile.TemporaryDirectory() as directory, patch.object(
            voice.requests,
            "post",
            side_effect=[voice.requests.ReadTimeout("temporary timeout"), response],
        ) as post, patch.object(voice.time, "sleep") as sleep:
            output = Path(directory) / "speech.wav"
            voice.synthesize_sentence_doubao_v3(
                "你好",
                output,
                api_key="key",
                speaker=voice.DEFAULT_TTS_SPEAKER,
                resource_id="seed-tts-2.0",
                speed_ratio=1.0,
                max_attempts=3,
                retry_delay_seconds=0.5,
                connect_timeout_seconds=10,
                read_timeout_seconds=30,
            )

        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 30))
        sleep.assert_called_once_with(0.5)

    def test_long_chunk_can_be_split_near_half_for_retry(self):
        split = voice.split_sentence_chunk_for_retry(["短句", "第二句更长", "第三句", "最后一句"])

        self.assertIsNotNone(split)
        left, right = split or ([], [])
        self.assertEqual(left + right, ["短句", "第二句更长", "第三句", "最后一句"])
        self.assertTrue(left)
        self.assertTrue(right)

    def test_native_timestamps_align_back_to_copywriting_lines(self):
        timed_chars = [
            voice.TimedChar("第", 0.0, 0.2),
            voice.TimedChar("一", 0.2, 0.4),
            voice.TimedChar("句", 0.4, 0.8),
            voice.TimedChar("第", 0.9, 1.1),
            voice.TimedChar("二", 1.1, 1.4),
            voice.TimedChar("句", 1.4, 1.8),
        ]

        timeline = voice.align_timeline_with_timed_chars(
            ["第一句", "第二句"],
            timed_chars,
            total_duration=1.8,
        )

        self.assertEqual([(item.start_seconds, item.end_seconds) for item in timeline], [
            (0.0, 0.8),
            (0.9, 1.8),
        ])

    def test_mastering_scales_timestamps_with_final_duration(self):
        scaled = voice.scale_timed_chars(
            [voice.TimedChar("字", 1.0, 2.0)],
            0.95,
        )
        self.assertEqual((scaled[0].start_seconds, scaled[0].end_seconds), (0.95, 1.9))

    def test_sentence_pause_extends_audio_and_shifts_following_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "speech.wav"
            with wave.open(str(audio_path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b"\x01\x00" * 8000)

            sentences = ["第一行", "第二行", "第三行", "第四行"]
            timeline = [
                voice.TimelineItem(index, text, start, end, end - start)
                for index, (text, start, end) in enumerate(zip(
                    sentences,
                    (0.0, 0.25, 0.5, 0.75),
                    (0.25, 0.5, 0.75, 1.0),
                ), start=1)
            ]

            adjusted = voice.insert_sentence_pauses(audio_path, timeline, sentences, 0.14)

            self.assertAlmostEqual(voice.audio_duration(audio_path), 1.14, places=3)
            self.assertEqual(adjusted[2].end_seconds, 0.75)
            self.assertEqual(adjusted[3].start_seconds, 0.89)
            self.assertEqual(adjusted[3].end_seconds, 1.14)


if __name__ == "__main__":
    unittest.main()
