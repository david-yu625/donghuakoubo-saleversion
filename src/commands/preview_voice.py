"""Generate a short Doubao voice preview WAV."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ..env import load_env_file
from ..prepare.voice_timeline import (
    DEFAULT_NARRATION_EMOTION,
    DEFAULT_NARRATION_EMOTION_SCALE,
    DEFAULT_NARRATION_STYLE_INSTRUCTION,
    DEFAULT_NARRATION_VOICE_PROFILE,
    DEFAULT_TTS_RESOURCE_ID,
    DEFAULT_TTS_SPEAKER,
    PROJECT_ROOT,
    master_narration_audio,
    resolve_tts_speaker,
    synthesize_sentence_doubao_v3,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speaker", default=DEFAULT_TTS_SPEAKER, help="豆包 TTS 音色 ID")
    parser.add_argument("--output", type=Path, required=True, help="试听 WAV 输出路径")
    parser.add_argument("--text", default="你好，这是当前音色的试听效果。")
    parser.add_argument("--speed-ratio", type=float, default=DEFAULT_NARRATION_VOICE_PROFILE.tts_speed_ratio)
    parser.add_argument("--emotion", default=DEFAULT_NARRATION_EMOTION)
    parser.add_argument("--emotion-scale", type=float, default=DEFAULT_NARRATION_EMOTION_SCALE)
    args = parser.parse_args()

    load_env_file(PROJECT_ROOT / ".env")
    api_key = (
        os.getenv("DOUBAO_TTS_API_KEY")
        or os.getenv("DOUBAO_TTS_ACCESS_KEY")
        or os.getenv("DOUBAO_TTS_ACCESS_TOKEN")
        or os.getenv("DOUBAO_TTS_TOKEN")
        or ""
    )
    resource_id = os.getenv("DOUBAO_TTS_RESOURCE_ID", DEFAULT_TTS_RESOURCE_ID)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    synthesize_sentence_doubao_v3(
        args.text,
        output,
        api_key=api_key,
        speaker=resolve_tts_speaker(args.speaker),
        resource_id=resource_id,
        speed_ratio=args.speed_ratio,
        emotion=args.emotion,
        emotion_scale=args.emotion_scale,
        context_texts=(DEFAULT_NARRATION_STYLE_INSTRUCTION,),
        audio_format="pcm",
        sample_rate=24000,
        enable_subtitle=False,
    )
    master_narration_audio(output)
    print(f"试听音频：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
