#!/usr/bin/env python3
"""Generate narration audio and per-line timing from a copywriting text file.

Examples:
    python3 -m src.02_generate_voice_timeline ./output/示例主题/wenan.txt
    python3 -m src.02_generate_voice_timeline ./output/示例主题/wenan.txt --voice Ting-Ting --rate 185
"""

from __future__ import annotations

import argparse
import base64
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

import requests

from ..env import load_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOUBAO_TTS_URL = "https://openspeech.bytedance.com/api/v1/tts"
DOUBAO_TTS_V3_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse"
DEFAULT_TTS_CLUSTER = "volcano_tts"
DEFAULT_TTS_RESOURCE_ID = "seed-tts-2.0"
DEFAULT_TTS_SPEAKER = "zh_female_shuangkuaisisi_uranus_bigtts"
DEFAULT_FULL_CHUNK_CHARS = 10000
DEFAULT_TTS_MODE = "full"
DEFAULT_TIMELINE_MODE = "native"
DEFAULT_ASR_MODEL = "small"
DEFAULT_NARRATION_EMOTION = "surprised"
DEFAULT_NARRATION_EMOTION_SCALE = 2.0
DEFAULT_TTS_MAX_ATTEMPTS = 3
DEFAULT_TTS_RETRY_DELAY_SECONDS = 2.0
DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS = 15.0
DEFAULT_TTS_READ_TIMEOUT_SECONDS = 120.0
DEFAULT_NARRATION_STYLE_INSTRUCTION = (
    "请用自然、有交流感、语调起伏鲜明的知识科普口播语气，像在兴奋地给朋友讲一个反常识发现。"
    "开头的问题明显上扬并带悬念；数字、对比词、否定词和核心概念清晰重读；"
    "转折前短暂收住，转折后明显抬起；解释部分保持快慢变化，不能平铺直叙；"
    "结论放慢一点并明显下沉，说得笃定、有记忆点。整段保持连贯，不要逐句重置语气；"
    "可以比普通科普更有表现力，但必须像真人自然说话，不要喊叫、卡通腔或机械变声。"
)
SPEAKER_ALIASES = {
    "female_04_shuangkuaisisi": DEFAULT_TTS_SPEAKER,
}
SENTENCE_RE = re.compile(r"[^。！？!?]+[。！？!?]?")
PUNCTUATION_RE = re.compile(r"[，。！？、；：,.!?;:「」『』“”‘’（）()《》〈〉【】\[\]—…·]")
ALIGN_TEXT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
QUESTION_TITLE_RE = re.compile(r"^\{(.+)\}$")
QUESTION_MARKERS = ("为什么", "怎么", "什么", "为何", "是不是", "能不能", "会不会", "吗", "呢", "谁", "哪")
TURN_OPENERS = ("但", "不过", "然而", "其实", "真正", "所以", "问题来了", "这就是", "换句话说")
EMPHASIS_MARKERS = (
    "夸张", "惊人", "数万亿", "几万度电", "几百上千", "海量", "上千块", "数十亿",
)


@dataclass(frozen=True)
class TimelineItem:
    index: int
    text: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float


@dataclass(frozen=True)
class NarrationVoiceProfile:
    tts_speed_ratio: float = 1.10
    master_tempo_ratio: float = 1.12
    # Full TTS already honors Chinese punctuation. Extra silence here makes
    # an otherwise continuous request sound like separately generated lines.
    sentence_pause_seconds: float = 0.0
    highpass_hz: int = 80
    lowpass_hz: int = 11000
    clarity_hz: int = 3200
    clarity_gain_db: float = 1.5
    compressor_threshold_db: float = -18.0
    compressor_ratio: float = 2.4
    compressor_attack_ms: float = 12.0
    compressor_release_ms: float = 90.0
    compressor_makeup_db: float = 2.2
    target_loudness_lufs: float = -14.0
    true_peak_db: float = -1.0
    loudness_range: float = 7.0


DEFAULT_NARRATION_VOICE_PROFILE = NarrationVoiceProfile()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成旁白音频，并输出每句话的时间段。")
    parser.add_argument("text_file", type=Path, help="输入文案 txt 文件。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="输出目录。默认写入输入 txt 所在目录。",
    )
    parser.add_argument(
        "--provider",
        choices=("doubao", "macos"),
        default="doubao",
        help="语音来源，默认 doubao；macos 使用系统 say 作为备用。",
    )
    parser.add_argument("--voice", default="Ting-Ting", help="macOS say 语音名称，provider=macos 时使用。")
    parser.add_argument("--rate", type=int, default=180, help="macOS say 语速，provider=macos 时使用。")
    parser.add_argument("--tts-api-key", default="", help="豆包新版 TTS API Key，默认从 .env 读取。")
    parser.add_argument("--tts-app-id", default="", help="旧版豆包 TTS AppID，provider=doubao-v1 时使用。")
    parser.add_argument("--tts-token", default="", help="旧版豆包 TTS Access Token，或新版 API Key 的兼容别名。")
    parser.add_argument("--tts-speaker", default="", help="豆包 TTS 音色，默认读取 DOUBAO_TTS_SPEAKER。")
    parser.add_argument("--tts-cluster", default="", help=f"豆包 TTS cluster，默认 {DEFAULT_TTS_CLUSTER}。")
    parser.add_argument(
        "--tts-resource-id",
        default="",
        help=f"豆包新版 TTS Resource ID，默认 {DEFAULT_TTS_RESOURCE_ID}。",
    )
    parser.add_argument(
        "--speed-ratio",
        type=float,
        default=DEFAULT_NARRATION_VOICE_PROFILE.tts_speed_ratio,
        help=f"豆包 TTS 模型内语速倍速，默认 {DEFAULT_NARRATION_VOICE_PROFILE.tts_speed_ratio:.2f}。",
    )
    parser.add_argument(
        "--sentence-pause",
        type=float,
        default=DEFAULT_NARRATION_VOICE_PROFILE.sentence_pause_seconds,
        help=(
            "整篇合成模式下，在规划出的句号后额外追加的静音秒数；"
            f"默认 {DEFAULT_NARRATION_VOICE_PROFILE.sentence_pause_seconds:.2f}。"
        ),
    )
    parser.add_argument(
        "--emotion",
        default=DEFAULT_NARRATION_EMOTION,
        help=f"Seed-TTS 原生情绪，默认 {DEFAULT_NARRATION_EMOTION}。",
    )
    parser.add_argument(
        "--emotion-scale",
        type=float,
        default=DEFAULT_NARRATION_EMOTION_SCALE,
        help="Seed-TTS 原生情绪强度，指定 --emotion 时生效。",
    )
    parser.add_argument(
        "--tts-mode",
        choices=("full", "line"),
        default=DEFAULT_TTS_MODE,
        help="TTS 方式：full 按长段落生成并保持连续语气；line 逐行生成并用真实音频时长写字幕时间线。默认 full。",
    )
    parser.add_argument(
        "--full-chunk-chars",
        type=int,
        default=DEFAULT_FULL_CHUNK_CHARS,
        help=(
            "full 模式下每个 TTS 分块的最大字数，默认 10000，尽量整篇一次生成，"
            "避免拼接断点；只有接口长度受限时才调小。"
        ),
    )
    parser.add_argument(
        "--timeline-mode",
        choices=("native", "asr", "estimate"),
        default=DEFAULT_TIMELINE_MODE,
        help=(
            "full 模式下 timeline 的生成方式：native 优先使用 Seed-TTS 原生时间戳并自动回退；"
            "asr 用整段音频反推；estimate 按字数估算。默认 native。"
        ),
    )
    parser.add_argument("--asr-model", default=DEFAULT_ASR_MODEL, help=f"timeline-mode=asr 时使用的 faster-whisper 模型，默认 {DEFAULT_ASR_MODEL}。")
    parser.add_argument("--asr-device", default="cpu", help="timeline-mode=asr 时使用的设备，默认 cpu。")
    parser.add_argument("--asr-compute-type", default="int8", help="timeline-mode=asr 时 faster-whisper compute_type，默认 int8。")
    parser.add_argument(
        "--split-mode",
        choices=("line", "sentence"),
        default="line",
        help="切分方式：line 按非空行；sentence 按句号问号叹号。默认 line。",
    )
    parser.add_argument(
        "--gap",
        type=float,
        default=0.0,
        help="句子之间插入的静音秒数，默认 0，连起来读。",
    )
    parser.add_argument(
        "--no-trim-silence",
        action="store_true",
        help="line 模式下不裁剪每句音频首尾静音。full 模式默认不裁剪。",
    )
    parser.add_argument(
        "--silence-threshold",
        default="-45dB",
        help="裁剪首尾静音的阈值，默认 -45dB。",
    )
    parser.add_argument(
        "--audio-name",
        default="narration.wav",
        help="整段旁白音频文件名，默认 narration.wav。",
    )
    return parser.parse_args()


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"缺少命令：{name}")


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"文案文件不存在：{path}")
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def split_text(text: str, mode: str) -> list[str]:
    if mode == "line":
        return [line.strip() for line in text.splitlines() if line.strip()]

    compact = re.sub(r"\s+", "", text)
    return [match.group(0).strip() for match in SENTENCE_RE.finditer(compact) if match.group(0).strip()]


def speech_text(text: str) -> str:
    value = text.strip()
    match = QUESTION_TITLE_RE.match(value)
    if match:
        return match.group(1).strip()
    return value


def resolve_tts_speaker(value: str) -> str:
    speaker = value.strip() or DEFAULT_TTS_SPEAKER
    return SPEAKER_ALIASES.get(speaker, speaker)


def ensure_tts_punctuation(
    text: str,
    *,
    index: int = 0,
    total: int = 1,
) -> str:
    value = speech_text(text)
    if not value:
        return value
    if value.endswith(("，", "。", "？", "！", ",", ".", "?", "!")):
        return value
    is_question = any(marker in value for marker in QUESTION_MARKERS)
    if QUESTION_TITLE_RE.match(text.strip()) or is_question:
        return value + "？"
    if any(marker in value for marker in EMPHASIS_MARKERS):
        return value + "！"
    if index == total - 1 or value.startswith(TURN_OPENERS) or (index + 1) % 3 == 0:
        return value + "。"
    return value + "，"


def join_for_full_tts(sentences: list[str]) -> str:
    readable = [sentence for sentence in sentences if speech_text(sentence)]
    # Keep the whole script in one TTS request. Punctuation carries prosody;
    # spaces between source lines can introduce unwanted micro-pauses in some
    # TTS models.
    return "".join(
        ensure_tts_punctuation(sentence, index=index, total=len(readable))
        for index, sentence in enumerate(readable)
    )


def text_units(text: str) -> int:
    return len(re.sub(r"\s+", "", speech_text(text)))


def chunk_sentences_for_full_tts(sentences: list[str], max_chars: int) -> list[list[str]]:
    if max_chars <= 0:
        raise ValueError("full-chunk-chars 必须大于 0")
    chunks: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for sentence in sentences:
        units = max(1, text_units(sentence))
        if current and current_chars + units > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(sentence)
        current_chars += units
    if current:
        chunks.append(current)
    return chunks


def timing_weight(text: str) -> float:
    value = PUNCTUATION_RE.sub("", speech_text(text))
    value = re.sub(r"\s+", "", value)
    if not value:
        return 1.0
    weight = 0.0
    for char in value:
        weight += 0.5 if char.isascii() else 1.0
    return max(1.0, weight)


def estimate_timeline(sentences: list[str], total_duration: float) -> list[TimelineItem]:
    weights = [timing_weight(sentence) for sentence in sentences]
    total_weight = sum(weights) or 1.0
    timeline: list[TimelineItem] = []
    current_seconds = 0.0
    for index, (sentence, weight) in enumerate(zip(sentences, weights), start=1):
        if index == len(sentences):
            end_seconds = total_duration
        else:
            end_seconds = current_seconds + total_duration * weight / total_weight
        duration_seconds = max(0.0, end_seconds - current_seconds)
        timeline.append(
            TimelineItem(
                index=index,
                text=sentence,
                start_seconds=round(current_seconds, 3),
                end_seconds=round(end_seconds, 3),
                duration_seconds=round(duration_seconds, 3),
            )
        )
        current_seconds = end_seconds
    return timeline


def scale_timeline(items: list[TimelineItem], scale: float) -> list[TimelineItem]:
    if scale <= 0:
        raise ValueError("时间线缩放比例必须大于 0")
    return [
        TimelineItem(
            index=item.index,
            text=item.text,
            start_seconds=round(item.start_seconds * scale, 3),
            end_seconds=round(item.end_seconds * scale, 3),
            duration_seconds=round(item.duration_seconds * scale, 3),
        )
        for item in items
    ]


def insert_sentence_pauses(
    audio_path: Path,
    timeline: list[TimelineItem],
    sentences: list[str],
    pause_seconds: float,
) -> list[TimelineItem]:
    if pause_seconds < 0:
        raise ValueError("句号停顿不能小于 0")
    if pause_seconds == 0 or not timeline:
        return timeline
    if len(timeline) != len(sentences):
        raise ValueError("句号停顿要求时间线与文案行数一致")

    pause_after = {
        index
        for index, sentence in enumerate(sentences[:-1])
        if ensure_tts_punctuation(sentence, index=index, total=len(sentences)).endswith(("。", "."))
    }
    if not pause_after:
        return timeline

    temporary = audio_path.with_name(f".{audio_path.stem}.paused.wav")
    with wave.open(str(audio_path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())
    if params.comptype != "NONE":
        raise ValueError("句号停顿只支持未压缩 PCM WAV")

    frame_width = params.nchannels * params.sampwidth
    frame_count = len(frames) // frame_width
    pause_frame_count = max(1, round(params.framerate * pause_seconds))
    pause_duration = pause_frame_count / params.framerate
    silence = b"\x00" * pause_frame_count * frame_width
    output = bytearray()
    cursor_frame = 0
    added_seconds = 0.0
    adjusted: list[TimelineItem] = []

    for index, item in enumerate(timeline):
        boundary_frame = max(cursor_frame, min(frame_count, round(item.end_seconds * params.framerate)))
        output.extend(frames[cursor_frame * frame_width : boundary_frame * frame_width])
        adjusted.append(TimelineItem(
            index=item.index,
            text=item.text,
            start_seconds=round(item.start_seconds + added_seconds, 3),
            end_seconds=round(item.end_seconds + added_seconds, 3),
            duration_seconds=item.duration_seconds,
        ))
        if index in pause_after:
            output.extend(silence)
            added_seconds += pause_duration
        cursor_frame = boundary_frame
    output.extend(frames[cursor_frame * frame_width :])

    try:
        with wave.open(str(temporary), "wb") as target:
            target.setparams(params)
            target.writeframes(output)
        temporary.replace(audio_path)
    finally:
        temporary.unlink(missing_ok=True)
    return adjusted


def estimate_timeline_from_chunks(sentence_chunks: list[list[str]], chunk_durations: list[float]) -> list[TimelineItem]:
    if len(sentence_chunks) != len(chunk_durations):
        raise ValueError("句子分块数量和音频分块数量不一致")
    timeline: list[TimelineItem] = []
    current_seconds = 0.0
    index = 1
    for chunk, chunk_duration in zip(sentence_chunks, chunk_durations):
        weights = [timing_weight(sentence) for sentence in chunk]
        total_weight = sum(weights) or 1.0
        chunk_start = current_seconds
        chunk_end = chunk_start + chunk_duration
        cursor = chunk_start
        for offset, (sentence, weight) in enumerate(zip(chunk, weights)):
            if offset == len(chunk) - 1:
                end_seconds = chunk_end
            else:
                end_seconds = cursor + chunk_duration * weight / total_weight
            duration_seconds = max(0.0, end_seconds - cursor)
            timeline.append(
                TimelineItem(
                    index=index,
                    text=sentence,
                    start_seconds=round(cursor, 3),
                    end_seconds=round(end_seconds, 3),
                    duration_seconds=round(duration_seconds, 3),
                )
            )
            cursor = end_seconds
            index += 1
        current_seconds = chunk_end
    return timeline


@dataclass(frozen=True)
class TimedChar:
    char: str
    start_seconds: float
    end_seconds: float


class TransientTtsError(RuntimeError):
    """A temporary TTS transport or service failure that can be retried or split."""


def scale_timed_chars(items: list[TimedChar], scale: float) -> list[TimedChar]:
    if scale <= 0:
        raise ValueError("时间戳缩放比例必须大于 0")
    return [
        TimedChar(
            char=item.char,
            start_seconds=item.start_seconds * scale,
            end_seconds=item.end_seconds * scale,
        )
        for item in items
    ]


def offset_timed_chars(items: list[TimedChar], offset_seconds: float) -> list[TimedChar]:
    return [
        TimedChar(
            char=item.char,
            start_seconds=item.start_seconds + offset_seconds,
            end_seconds=item.end_seconds + offset_seconds,
        )
        for item in items
    ]


def normalize_for_alignment(text: str) -> str:
    return "".join(ALIGN_TEXT_RE.findall(speech_text(text))).lower()


def reference_char_spans(sentences: list[str]) -> tuple[str, list[tuple[int, int]]]:
    cursor = 0
    chunks: list[str] = []
    spans: list[tuple[int, int]] = []
    for sentence in sentences:
        normalized = normalize_for_alignment(sentence)
        start = cursor
        cursor += len(normalized)
        spans.append((start, cursor))
        chunks.append(normalized)
    return "".join(chunks), spans


def interpolate_word_chars(word: str, start_seconds: float, end_seconds: float) -> list[TimedChar]:
    normalized = normalize_for_alignment(word)
    if not normalized:
        return []
    duration = max(0.01, end_seconds - start_seconds)
    unit = duration / len(normalized)
    return [
        TimedChar(
            char=char,
            start_seconds=start_seconds + index * unit,
            end_seconds=start_seconds + (index + 1) * unit,
        )
        for index, char in enumerate(normalized)
    ]


def transcribe_timed_chars(audio_path: Path, *, model_name: str, device: str, compute_type: str) -> list[TimedChar]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("缺少 faster-whisper，无法用整段音频反推字幕时间") from exc

    model = WhisperModel(model_name, device=device, compute_type=compute_type, local_files_only=True)
    segments, _ = model.transcribe(
        str(audio_path),
        language="zh",
        word_timestamps=True,
        vad_filter=False,
        beam_size=5,
    )
    chars: list[TimedChar] = []
    for segment in segments:
        words = segment.words or []
        if not words:
            chars.extend(interpolate_word_chars(segment.text, float(segment.start), float(segment.end)))
            continue
        for word in words:
            chars.extend(interpolate_word_chars(word.word, float(word.start), float(word.end)))
    if not chars:
        raise RuntimeError("ASR 没有返回可用的字级时间戳")
    return chars


def build_ref_to_hyp_map(reference: str, hypothesis: str) -> dict[int, int]:
    matcher = difflib.SequenceMatcher(a=reference, b=hypothesis, autojunk=False)
    mapping: dict[int, int] = {}
    for tag, ref_start, ref_end, hyp_start, hyp_end in matcher.get_opcodes():
        ref_len = ref_end - ref_start
        hyp_len = hyp_end - hyp_start
        if ref_len <= 0 or hyp_len <= 0:
            continue
        if tag == "equal":
            for offset in range(ref_len):
                mapping[ref_start + offset] = hyp_start + offset
            continue
        for offset in range(ref_len):
            ratio = offset / max(1, ref_len - 1)
            hyp_offset = round(ratio * max(0, hyp_len - 1))
            mapping[ref_start + offset] = hyp_start + hyp_offset
    return mapping


def nearest_mapped_index(mapping: dict[int, int], ref_index: int, *, ref_limit: int) -> int | None:
    if ref_index in mapping:
        return mapping[ref_index]
    for distance in range(1, ref_limit + 1):
        left = ref_index - distance
        right = ref_index + distance
        if left in mapping:
            return mapping[left]
        if right in mapping:
            return mapping[right]
    return None


def align_timeline_with_asr(
    sentences: list[str],
    audio_path: Path,
    total_duration: float,
    *,
    model_name: str,
    device: str,
    compute_type: str,
) -> list[TimelineItem]:
    timed_chars = transcribe_timed_chars(audio_path, model_name=model_name, device=device, compute_type=compute_type)
    return align_timeline_with_timed_chars(sentences, timed_chars, total_duration)


def align_timeline_with_timed_chars(
    sentences: list[str],
    timed_chars: list[TimedChar],
    total_duration: float,
) -> list[TimelineItem]:
    reference, spans = reference_char_spans(sentences)
    if not reference:
        raise ValueError("文案没有可用于时间戳对齐的字符")
    if not timed_chars:
        raise ValueError("没有可用的原生字级时间戳")

    hypothesis = "".join(item.char for item in timed_chars)
    mapping = build_ref_to_hyp_map(reference, hypothesis)
    coverage = len(mapping) / max(1, len(reference))
    if coverage < 0.65:
        raise RuntimeError(f"时间戳对齐覆盖率过低：{coverage:.1%}")

    items: list[TimelineItem] = []
    previous_end = 0.0
    for index, (sentence, (ref_start, ref_end)) in enumerate(zip(sentences, spans), start=1):
        if ref_start == ref_end:
            start_seconds = previous_end
            end_seconds = previous_end
        else:
            start_hyp = nearest_mapped_index(mapping, ref_start, ref_limit=len(reference))
            end_hyp = nearest_mapped_index(mapping, ref_end - 1, ref_limit=len(reference))
            if start_hyp is None or end_hyp is None:
                raise RuntimeError(f"第 {index} 行字幕无法映射到字级时间戳：{sentence}")
            start_hyp, end_hyp = sorted((start_hyp, end_hyp))
            start_seconds = timed_chars[start_hyp].start_seconds
            end_seconds = timed_chars[end_hyp].end_seconds

        start_seconds = max(previous_end, start_seconds)
        if index == len(sentences):
            end_seconds = total_duration
        else:
            end_seconds = max(start_seconds + 0.05, end_seconds)
        item = TimelineItem(
            index=index,
            text=sentence,
            start_seconds=round(start_seconds, 3),
            end_seconds=round(end_seconds, 3),
            duration_seconds=round(max(0.0, end_seconds - start_seconds), 3),
        )
        items.append(item)
        previous_end = item.end_seconds
    return items


def run(command: list[str]) -> None:
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def convert_to_wav(input_path: Path, output_path: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def master_narration_audio(
    audio_path: Path,
    profile: NarrationVoiceProfile = DEFAULT_NARRATION_VOICE_PROFILE,
) -> None:
    if not audio_path.is_file():
        raise FileNotFoundError(f"旁白音频不存在：{audio_path}")
    mastered_path = audio_path.with_name(f".{audio_path.stem}.mastered.wav")
    filters = narration_master_filters(profile)
    try:
        run([
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-af",
            filters,
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(mastered_path),
        ])
        mastered_path.replace(audio_path)
    finally:
        mastered_path.unlink(missing_ok=True)


def db_to_linear(decibels: float) -> float:
    return 10 ** (decibels / 20)


def narration_master_filters(profile: NarrationVoiceProfile) -> str:
    makeup = db_to_linear(profile.compressor_makeup_db)
    return ",".join((
        f"highpass=f={profile.highpass_hz}",
        f"lowpass=f={profile.lowpass_hz}",
        f"equalizer=f={profile.clarity_hz}:t=q:w=1:g={profile.clarity_gain_db:.1f}",
        (
            f"acompressor=threshold={profile.compressor_threshold_db:.1f}dB:"
            f"ratio={profile.compressor_ratio:.1f}:"
            f"attack={profile.compressor_attack_ms:.1f}:"
            f"release={profile.compressor_release_ms:.1f}:"
            f"makeup={makeup:.4f}"
        ),
        f"atempo={profile.master_tempo_ratio:.4f}",
        (
            f"loudnorm=I={profile.target_loudness_lufs:.1f}:"
            f"TP={profile.true_peak_db:.1f}:LRA={profile.loudness_range:.1f}"
        ),
    ))


def synthesize_sentence_macos(text: str, output_path: Path, *, voice: str, rate: int) -> None:
    aiff_path = output_path.with_suffix(".aiff")
    run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff_path), text])
    try:
        convert_to_wav(aiff_path, output_path)
    finally:
        aiff_path.unlink(missing_ok=True)


def synthesize_sentence_doubao(
    text: str,
    output_path: Path,
    *,
    app_id: str,
    token: str,
    speaker: str,
    cluster: str,
    speed_ratio: float,
) -> None:
    if not app_id:
        raise ValueError("缺少豆包 TTS AppID，请在 .env 中设置 DOUBAO_TTS_APP_ID，或传入 --tts-app-id")
    if not token:
        raise ValueError("缺少豆包 TTS Access Token，请在 .env 中设置 DOUBAO_TTS_ACCESS_TOKEN，或传入 --tts-token")
    if not speaker:
        raise ValueError("缺少豆包 TTS 音色，请在 .env 中设置 DOUBAO_TTS_SPEAKER，或传入 --tts-speaker")
    if not 0.5 <= speed_ratio <= 2.0:
        raise ValueError("speed-ratio 建议在 0.5 到 2.0 之间")

    body = {
        "app": {
            "appid": app_id,
            "token": token,
            "cluster": cluster,
        },
        "user": {"uid": "caijingkepu"},
        "audio": {
            "voice_type": speaker,
            "encoding": "mp3",
            "speed_ratio": speed_ratio,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "operation": "query",
        },
    }
    response = requests.post(
        DOUBAO_TTS_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer;{token}",
        },
        json=body,
        timeout=60,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"豆包 TTS 返回非 JSON: HTTP {response.status_code}") from exc
    if response.status_code >= 400 or payload.get("code") not in (0, 3000):
        raise RuntimeError(f"豆包 TTS 调用失败: HTTP {response.status_code}, {payload}")
    audio_base64 = payload.get("data")
    if not audio_base64:
        raise RuntimeError(f"豆包 TTS 没有返回音频数据: {payload}")

    mp3_path = output_path.with_suffix(".mp3")
    try:
        mp3_path.write_bytes(base64.b64decode(audio_base64))
        convert_to_wav(mp3_path, output_path)
    finally:
        mp3_path.unlink(missing_ok=True)


def extract_audio_chunks(payload: object) -> list[str]:
    chunks: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"audio", "data"} and isinstance(value, str) and len(value) > 64:
                chunks.append(value)
            else:
                chunks.extend(extract_audio_chunks(value))
    elif isinstance(payload, list):
        for item in payload:
            chunks.extend(extract_audio_chunks(item))
    return chunks


def timestamp_seconds(value: object, key: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if key.endswith("_ms") or key in {"start_time", "end_time", "begin_time"}:
        return number / 1000.0
    if number > 3600:
        return number / 1000.0
    return number


def extract_timed_chars(payload: object) -> list[TimedChar]:
    items: list[TimedChar] = []

    def walk(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return

        token = next(
            (
                str(value[key])
                for key in ("char", "word", "text")
                if isinstance(value.get(key), str) and str(value[key]).strip()
            ),
            "",
        )
        start_pair = next(
            ((key, value[key]) for key in ("start_ms", "start_time", "start", "begin_ms", "begin_time", "begin") if key in value),
            None,
        )
        end_pair = next(
            ((key, value[key]) for key in ("end_ms", "end_time", "end", "stop_ms", "stop_time", "stop") if key in value),
            None,
        )
        if token and start_pair and end_pair:
            start_seconds = timestamp_seconds(start_pair[1], start_pair[0])
            end_seconds = timestamp_seconds(end_pair[1], end_pair[0])
            if start_seconds is not None and end_seconds is not None and end_seconds >= start_seconds:
                items.extend(interpolate_word_chars(token, start_seconds, end_seconds))

        for nested in value.values():
            if isinstance(nested, (dict, list)):
                walk(nested)

    walk(payload)
    unique: dict[tuple[str, float, float], TimedChar] = {}
    for item in items:
        key = (item.char, round(item.start_seconds, 6), round(item.end_seconds, 6))
        unique[key] = item
    return sorted(unique.values(), key=lambda item: (item.start_seconds, item.end_seconds, item.char))


def write_pcm_wav(path: Path, pcm_data: bytes, *, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm_data)


def synthesize_sentence_doubao_v3(
    text: str,
    output_path: Path,
    *,
    api_key: str,
    speaker: str,
    resource_id: str,
    speed_ratio: float,
    emotion: str = "",
    emotion_scale: float = 2.0,
    context_texts: tuple[str, ...] = (),
    audio_format: str = "pcm",
    sample_rate: int = 24000,
    enable_subtitle: bool = True,
    max_attempts: int = DEFAULT_TTS_MAX_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_TTS_RETRY_DELAY_SECONDS,
    connect_timeout_seconds: float = DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
    read_timeout_seconds: float = DEFAULT_TTS_READ_TIMEOUT_SECONDS,
) -> list[TimedChar]:
    if not api_key:
        raise ValueError("缺少豆包新版 TTS API Key，请在 .env 中设置 DOUBAO_TTS_ACCESS_KEY，或传入 --tts-api-key")
    if not speaker:
        raise ValueError("缺少豆包 TTS 音色，请在 .env 中设置 DOUBAO_TTS_SPEAKER，或传入 --tts-speaker")
    if not resource_id:
        raise ValueError("缺少豆包 TTS Resource ID，请设置 DOUBAO_TTS_RESOURCE_ID，或传入 --tts-resource-id")
    if not 0.5 <= speed_ratio <= 2.0:
        raise ValueError("speed-ratio 建议在 0.5 到 2.0 之间")
    if emotion and emotion_scale <= 0:
        raise ValueError("emotion-scale 必须大于 0")

    if audio_format not in {"pcm", "mp3", "ogg_opus"}:
        raise ValueError(f"豆包新版 TTS 不支持音频格式：{audio_format}")
    if sample_rate <= 0:
        raise ValueError("sample_rate 必须大于 0")
    if max_attempts <= 0:
        raise ValueError("max_attempts 必须大于 0")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds 不能小于 0")
    if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0:
        raise ValueError("TTS 超时时间必须大于 0")

    speaker = resolve_tts_speaker(speaker)
    speech_rate = round((speed_ratio - 1.0) * 100)
    request_id = str(uuid.uuid4())
    req_params: dict[str, object] = {
        "text": text,
        "speaker": speaker,
        "audio_params": {
            "format": audio_format,
            "sample_rate": sample_rate,
            "speech_rate": speech_rate,
        },
    }
    if emotion.strip():
        audio_params = req_params["audio_params"]
        assert isinstance(audio_params, dict)
        audio_params["emotion"] = emotion.strip()
        audio_params["emotion_scale"] = emotion_scale
    if context_texts:
        req_params["context_texts"] = list(context_texts)
    if enable_subtitle:
        req_params["enable_subtitle"] = True
    body = {
        "user": {"uid": "caijingkepu"},
        "req_params": req_params,
    }
    for attempt in range(1, max_attempts + 1):
        response = None
        try:
            request_id = str(uuid.uuid4())
            response = requests.post(
                DOUBAO_TTS_V3_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": api_key,
                    "X-Api-Resource-Id": resource_id,
                    "X-Api-Request-Id": request_id,
                },
                json=body,
                stream=True,
                timeout=(connect_timeout_seconds, read_timeout_seconds),
            )
            if response.status_code >= 400:
                detail = response.text[:500]
                if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
                    raise requests.HTTPError(
                        f"HTTP {response.status_code}: {detail}",
                        response=response,
                    )
                raise RuntimeError(f"豆包新版 TTS 调用失败: HTTP {response.status_code}, {detail}")

            audio_chunks: list[bytes] = []
            timed_chars: list[TimedChar] = []
            errors: list[str] = []
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line in {"[DONE]", "DONE"}:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                code = payload.get("code") if isinstance(payload, dict) else None
                if code not in (None, 0, 20000000):
                    errors.append(json.dumps(payload, ensure_ascii=False))
                    continue
                timed_chars.extend(extract_timed_chars(payload))
                for item in extract_audio_chunks(payload):
                    try:
                        audio_chunks.append(base64.b64decode(item))
                    except (TypeError, ValueError):
                        pass

            if not audio_chunks:
                detail = errors[-1] if errors else "接口流结束但没有音频数据"
                raise RuntimeError(f"豆包新版 TTS 没有返回音频数据: {detail}")

            audio_data = b"".join(audio_chunks)
            if audio_format == "pcm":
                write_pcm_wav(output_path, audio_data, sample_rate=sample_rate)
            else:
                compressed_path = output_path.with_suffix(f".{audio_format}")
                try:
                    compressed_path.write_bytes(audio_data)
                    convert_to_wav(compressed_path, output_path)
                finally:
                    compressed_path.unlink(missing_ok=True)
            return extract_timed_chars([
                {"char": item.char, "start": item.start_seconds, "end": item.end_seconds}
                for item in timed_chars
            ])
        except requests.RequestException as exc:
            if attempt >= max_attempts:
                raise TransientTtsError(
                    f"豆包新版 TTS 网络请求连续失败 {max_attempts} 次: {exc}"
                ) from exc
            delay = retry_delay_seconds * attempt
            print(
                f"警告：豆包 TTS 请求失败，{delay:g} 秒后重试（{attempt}/{max_attempts}）：{exc}",
                file=sys.stderr,
            )
            time.sleep(delay)
        finally:
            if response is not None:
                close = getattr(response, "close", None)
                if callable(close):
                    close()

    raise AssertionError("unreachable")


def split_sentence_chunk_for_retry(sentences: list[str]) -> tuple[list[str], list[str]] | None:
    if len(sentences) < 2:
        return None
    weights = [max(1, text_units(sentence)) for sentence in sentences]
    target = sum(weights) / 2
    running = 0
    split_index = 1
    for index, weight in enumerate(weights[:-1], start=1):
        running += weight
        split_index = index
        if running >= target:
            break
    return sentences[:split_index], sentences[split_index:]


def audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return float(result.stdout.strip())


def make_silence(path: Path, duration_seconds: float) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=44100",
            "-t",
            f"{duration_seconds:.6f}",
            "-c:a",
            "pcm_s16le",
            str(path),
        ]
    )


def trim_silence(input_path: Path, output_path: Path, *, threshold: str) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-af",
            (
                "silenceremove="
                f"start_periods=1:start_duration=0.02:start_threshold={threshold}:"
                f"stop_periods=1:stop_duration=0.06:stop_threshold={threshold}"
            ),
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def concat_audio(parts: list[Path], output_path: Path) -> None:
    list_path = output_path.with_suffix(".concat.txt")
    lines = []
    for part in parts:
        escaped = str(part).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ]
        )
    finally:
        list_path.unlink(missing_ok=True)


def clean_csv_text(text: str) -> str:
    return PUNCTUATION_RE.sub("", text).strip()


def bracket_time(*values: float) -> str:
    return "[" + ",".join(f"{value:.3f}" for value in values) + "]"


def write_timeline(output_dir: Path, items: list[TimelineItem]) -> None:
    csv_lines = ["index,text,time"]
    for item in items:
        csv_lines.append(
            ",".join(
                (
                    str(item.index),
                    clean_csv_text(item.text),
                    bracket_time(
                        item.start_seconds,
                        item.end_seconds,
                        item.duration_seconds,
                    ),
                )
            )
        )
    (output_dir / "timeline.csv").write_text(
        "\ufeff" + "\n".join(csv_lines) + "\n",
        encoding="utf-8",
    )


def build_voice_timeline(args: argparse.Namespace) -> tuple[Path, list[TimelineItem]]:
    require_command("ffmpeg")
    require_command("ffprobe")
    if args.provider == "macos":
        require_command("say")
    if args.rate <= 0:
        raise ValueError("rate 必须大于 0")
    if args.gap < 0:
        raise ValueError("gap 不能小于 0")
    if args.sentence_pause < 0:
        raise ValueError("sentence-pause 不能小于 0")

    text_path = args.text_file.expanduser().resolve()
    text = read_text(text_path)
    sentences = split_text(text, args.split_mode)
    if not sentences:
        raise ValueError("文案中没有可朗读的句子")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else text_path.parent
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / args.audio_name

    timeline: list[TimelineItem] = []
    concat_parts: list[Path] = []
    current_seconds = 0.0
    tts_api_key = (
        args.tts_api_key
        or os.getenv("DOUBAO_TTS_API_KEY")
        or os.getenv("DOUBAO_TTS_ACCESS_KEY")
        or os.getenv("DOUBAO_TTS_ACCESS_TOKEN")
        or os.getenv("DOUBAO_TTS_TOKEN")
        or os.getenv("TTS_API_KEY")
        or os.getenv("TTS_TOKEN")
        or ""
    )
    tts_app_id = (
        args.tts_app_id
        or os.getenv("DOUBAO_TTS_APP_ID")
        or os.getenv("DOUBAO_TTS_APPID")
        or os.getenv("VOLCENGINE_TTS_APP_ID")
        or os.getenv("VOLCENGINE_TTS_APPID")
        or os.getenv("VOLC_TTS_APP_ID")
        or os.getenv("VOLC_TTS_APPID")
        or os.getenv("TTS_APP_ID")
        or os.getenv("TTS_APPID")
        or ""
    )
    tts_token = (
        args.tts_token
        or os.getenv("DOUBAO_TTS_ACCESS_TOKEN")
        or os.getenv("DOUBAO_TTS_TOKEN")
        or os.getenv("DOUBAO_TTS_ACCESS_KEY")
        or os.getenv("DOUBAO_TTS_API_KEY")
        or os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN")
        or os.getenv("VOLC_TTS_ACCESS_TOKEN")
        or os.getenv("TTS_ACCESS_TOKEN")
        or os.getenv("TTS_TOKEN")
        or ""
    )
    tts_speaker = resolve_tts_speaker(
        args.tts_speaker or os.getenv("DOUBAO_TTS_SPEAKER", DEFAULT_TTS_SPEAKER)
    )
    tts_cluster = args.tts_cluster or os.getenv("DOUBAO_TTS_CLUSTER", DEFAULT_TTS_CLUSTER)
    tts_resource_id = args.tts_resource_id or os.getenv("DOUBAO_TTS_RESOURCE_ID", DEFAULT_TTS_RESOURCE_ID)

    with tempfile.TemporaryDirectory(prefix="voice_timeline_") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        if args.tts_mode == "full":
            pending_chunks = chunk_sentences_for_full_tts(sentences, args.full_chunk_chars)
            if not pending_chunks:
                raise ValueError("文案中没有可朗读的内容")
            sentence_chunks: list[list[str]] = []
            full_parts: list[Path] = []
            chunk_durations: list[float] = []
            native_timed_chars: list[TimedChar] = []
            raw_cursor = 0.0
            while pending_chunks:
                sentence_chunk = pending_chunks.pop(0)
                chunk_index = len(sentence_chunks) + 1
                full_text = join_for_full_tts(sentence_chunk)
                chunk_path = temp_dir / f"full_chunk_{chunk_index:04d}.wav"
                final_chunk_path = chunk_path
                if args.provider == "macos":
                    synthesize_sentence_macos(full_text, chunk_path, voice=args.voice, rate=args.rate)
                else:
                    try:
                        chunk_timed_chars = synthesize_sentence_doubao_v3(
                            full_text,
                            chunk_path,
                            api_key=tts_api_key,
                            speaker=tts_speaker,
                            resource_id=tts_resource_id,
                            speed_ratio=args.speed_ratio,
                            emotion=args.emotion,
                            emotion_scale=args.emotion_scale,
                            context_texts=(DEFAULT_NARRATION_STYLE_INSTRUCTION,),
                            audio_format="pcm",
                            sample_rate=24000,
                            enable_subtitle=True,
                        )
                    except TransientTtsError:
                        split_chunks = split_sentence_chunk_for_retry(sentence_chunk)
                        if split_chunks is None:
                            raise
                        left, right = split_chunks
                        print(
                            f"警告：长段配音连续超时，自动拆成 {len(left)} 行和 {len(right)} 行后继续",
                            file=sys.stderr,
                        )
                        pending_chunks[0:0] = [left, right]
                        continue
                sentence_chunks.append(sentence_chunk)
                full_parts.append(final_chunk_path)
                chunk_duration = audio_duration(final_chunk_path)
                chunk_durations.append(chunk_duration)
                if args.provider != "macos":
                    native_timed_chars.extend(offset_timed_chars(chunk_timed_chars, raw_cursor))
                raw_cursor += chunk_duration
            concat_audio(full_parts, audio_path)
            raw_duration = audio_duration(audio_path)
            master_narration_audio(audio_path)
            total_duration = audio_duration(audio_path)
            timing_scale = total_duration / max(raw_duration, 0.001)
            native_timed_chars = scale_timed_chars(native_timed_chars, timing_scale)

            if args.timeline_mode == "native" and native_timed_chars:
                try:
                    timeline = align_timeline_with_timed_chars(sentences, native_timed_chars, total_duration)
                except (RuntimeError, ValueError) as exc:
                    print(f"警告：原生时间戳不可用，回退 ASR：{exc}", file=sys.stderr)
                    try:
                        timeline = align_timeline_with_asr(
                            sentences,
                            audio_path,
                            total_duration,
                            model_name=args.asr_model,
                            device=args.asr_device,
                            compute_type=args.asr_compute_type,
                        )
                    except (RuntimeError, ValueError, OSError) as asr_exc:
                        print(f"警告：ASR 对齐不可用，回退时长估算：{asr_exc}", file=sys.stderr)
                        timeline = estimate_timeline(sentences, total_duration)
            elif args.timeline_mode in {"native", "asr"}:
                if args.timeline_mode == "native":
                    print("警告：接口未返回原生时间戳，回退 ASR", file=sys.stderr)
                try:
                    timeline = align_timeline_with_asr(
                        sentences,
                        audio_path,
                        total_duration,
                        model_name=args.asr_model,
                        device=args.asr_device,
                        compute_type=args.asr_compute_type,
                    )
                except (RuntimeError, ValueError, OSError) as exc:
                    if args.timeline_mode == "asr":
                        raise
                    print(f"警告：ASR 对齐不可用，回退时长估算：{exc}", file=sys.stderr)
                    timeline = estimate_timeline(sentences, total_duration)
            else:
                timeline = scale_timeline(
                    estimate_timeline_from_chunks(sentence_chunks, chunk_durations),
                    timing_scale,
                )
            if timeline and abs(timeline[-1].end_seconds - total_duration) > 0.02:
                timeline = [*timeline[:-1], TimelineItem(
                    index=timeline[-1].index,
                    text=timeline[-1].text,
                    start_seconds=timeline[-1].start_seconds,
                    end_seconds=round(total_duration, 3),
                    duration_seconds=round(max(0.0, total_duration - timeline[-1].start_seconds), 3),
                )]
            if args.sentence_pause > 0:
                timeline = insert_sentence_pauses(
                    audio_path,
                    timeline,
                    sentences,
                    args.sentence_pause,
                )
            write_timeline(output_dir, timeline)
            return audio_path, timeline

        silence_path = temp_dir / "gap.wav"
        if args.gap > 0:
            make_silence(silence_path, args.gap)

        for index, sentence in enumerate(sentences, start=1):
            sentence_path = temp_dir / f"sentence_{index:04d}.wav"
            final_sentence_path = sentence_path
            if args.provider == "macos":
                synthesize_sentence_macos(sentence, sentence_path, voice=args.voice, rate=args.rate)
            else:
                synthesize_sentence_doubao_v3(
                    sentence,
                    sentence_path,
                    api_key=tts_api_key,
                    speaker=tts_speaker,
                    resource_id=tts_resource_id,
                    speed_ratio=args.speed_ratio,
                    emotion=args.emotion,
                    emotion_scale=args.emotion_scale,
                    context_texts=(DEFAULT_NARRATION_STYLE_INSTRUCTION,),
                    audio_format="pcm",
                    sample_rate=24000,
                    enable_subtitle=False,
                )
            if not args.no_trim_silence:
                trimmed_sentence_path = temp_dir / f"sentence_{index:04d}_trimmed.wav"
                trim_silence(sentence_path, trimmed_sentence_path, threshold=args.silence_threshold)
                final_sentence_path = trimmed_sentence_path
            duration = audio_duration(final_sentence_path)
            start = current_seconds
            end = start + duration
            timeline.append(
                TimelineItem(
                    index=index,
                    text=sentence,
                    start_seconds=round(start, 3),
                    end_seconds=round(end, 3),
                    duration_seconds=round(duration, 3),
                )
            )
            concat_parts.append(final_sentence_path)
            current_seconds = end
            if args.gap > 0 and index < len(sentences):
                concat_parts.append(silence_path)
                current_seconds += args.gap

        concat_audio(concat_parts, audio_path)
        raw_duration = audio_duration(audio_path)
        master_narration_audio(audio_path)
        final_duration = audio_duration(audio_path)
        timeline = scale_timeline(timeline, final_duration / max(raw_duration, 0.001))

    write_timeline(output_dir, timeline)
    return audio_path, timeline


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    args = parse_args()
    try:
        audio_path, timeline = build_voice_timeline(args)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"音频已生成：{audio_path}")
    print(f"CSV 已生成：{audio_path.parent / 'timeline.csv'}")
    print(f"句子数量：{len(timeline)}")
    if timeline:
        print(f"总时长约：{timeline[-1].end_seconds:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
