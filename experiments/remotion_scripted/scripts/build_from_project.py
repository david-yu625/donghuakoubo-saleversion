"""Adapt one prepared agent project to the scripted Remotion contract.

The main agent already owns copywriting, narration, shot timing and image
generation.  This adapter keeps those inputs, chooses one image per semantic
shot, and hands the result to the latest isolated Remotion layers.  It never
imports the Jianying renderer.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import wave
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROJECT_ROOT = ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from remotion_pipeline.config import PUBLIC_ROOT, RUNS_ROOT
from remotion_pipeline.contracts import VISUAL_STYLE_ID, validate_scene_facts
from remotion_pipeline.pipeline.density import audit_density
from remotion_pipeline.pipeline.scene_facts import build_scene_facts
from remotion_pipeline.layouts.world import layout_world
from remotion_pipeline.renderers.remotion import make_manifest
from remotion_pipeline.visual_direction.plan import direct_scenes


def slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value).strip("_") or "agent_project"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / max(1, audio.getframerate())


STRONG_CAPTION_PUNCTUATION = "。！？!?"
WEAK_CAPTION_PUNCTUATION = "，,；;：:、—"
CAPTION_BREAK_BEFORE = (
    "但是", "可是", "不过", "然而", "于是", "然后", "所以", "因此",
    "如果", "要是", "只要", "结果", "其实", "同时", "另外", "接着",
    "最后", "反而", "还给", "拿到", "换成", "变成", "导致", "说明",
    "意味着", "先", "再", "又", "但", "却",
)
CAPTION_ACTION_BREAK_BEFORE = ("还给", "拿到", "买回", "卖掉", "借来", "赚到", "亏掉", "涨到", "跌到", "换来", "换成", "变成")
CAPTION_BREAK_AFTER = ("以后", "之后", "后来", "当时", "这时", "目前", "后")
# Whisper word timestamps tend to land a little after the visual speech onset.
# A small lead keeps captions readable without changing the source audio.


def caption_display_width(text: str) -> float:
    import unicodedata
    width = 0.0
    for character in text:
        if character.isspace():
            width += 0.5
        elif unicodedata.east_asian_width(character) in {"W", "F", "A"}:
            width += 1.0
        else:
            width += 0.55
    return width


def split_caption_text(text: str, max_width: int = 24) -> list[str]:
    """Mirror Jianying's semantic single-line subtitle splitting."""
    import unicodedata
    normalized = re.sub(r"\s+", " ", text).strip()
    clauses: list[str] = []
    current = ""
    for character in normalized:
        if character in WEAK_CAPTION_PUNCTUATION:
            if current.strip():
                clauses.append(current.strip())
            current = ""
        elif character in STRONG_CAPTION_PUNCTUATION:
            current += character
            if current.strip():
                clauses.append(current.strip())
            current = ""
        else:
            current += character
    if current.strip():
        clauses.append(current.strip())

    merged: list[str] = []
    for clause in clauses:
        if caption_display_width(clause) < 4 and merged:
            merged[-1] += clause
        elif caption_display_width(clause) < 4 and len(merged) + 1 < len(clauses):
            merged.append(clause)
        else:
            merged.append(clause)

    chunks: list[str] = []
    for clause in merged:
        remaining = clause.strip()
        while caption_display_width(remaining) > max_width:
            positions: list[int] = []
            for token in (*CAPTION_BREAK_AFTER, *CAPTION_BREAK_BEFORE, *CAPTION_ACTION_BREAK_BEFORE):
                start = 0
                while True:
                    found = remaining.find(token, start)
                    if found < 0:
                        break
                    position = found + len(token) if token in CAPTION_BREAK_AFTER else found
                    if 4 <= caption_display_width(remaining[:position]) <= max_width:
                        positions.append(position)
                    start = found + len(token)
            if positions:
                split_at = max(positions, key=lambda index: caption_display_width(remaining[:index]))
            else:
                target = max_width if caption_display_width(remaining) > max_width * 2 else caption_display_width(remaining) / 2
                width = 0.0
                split_at = max(1, len(remaining) - 1)
                for index, character in enumerate(remaining, start=1):
                    width += caption_display_width(character)
                    if width > target and index > 1:
                        split_at = index - 1
                        break
            left, remaining = remaining[:split_at].strip(), remaining[split_at:].strip()
            if left:
                chunks.append(left)
        if remaining:
            chunks.append(remaining)

    cleaned = []
    for chunk in chunks:
        value = "".join(character for character in chunk if not unicodedata.category(character).startswith("P")).strip()
        if value:
            cleaned.append(value)
    return cleaned or [text.strip()]


def distribute_caption_timing(chunks: list[str], start: float, end: float) -> list[tuple[float, float]]:
    weights = [max(0.5, caption_display_width(chunk)) for chunk in chunks]
    total = sum(weights)
    timings: list[tuple[float, float]] = []
    cursor = start
    for index, weight in enumerate(weights):
        chunk_end = end if index == len(chunks) - 1 else cursor + (end - start) * weight / total
        timings.append((round(cursor, 3), round(chunk_end, 3)))
        cursor = chunk_end
    return timings


CAPTION_ASR_LEAD_SECONDS = 0.08


def read_project_captions(
    project_or_timeline: Path,
    duration: float,
    source_text_dir: Path | None = None,
    audio_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Read the speech recognizer/TTS sentence timings produced by step 02."""
    timeline = (
        project_or_timeline / "timeline.csv"
        if project_or_timeline.is_dir()
        else project_or_timeline
    )
    if not timeline.is_file():
        raise FileNotFoundError(f"missing voice sentence timeline: {timeline}")
    project = source_text_dir or (project_or_timeline if project_or_timeline.is_dir() else project_or_timeline.parent)
    punctuation_map: dict[str, str] = {}
    source_text = project / "wenan.txt"
    if source_text.is_file():
        for line in source_text.read_text(encoding="utf-8-sig").splitlines():
            normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", line)
            if normalized:
                punctuation_map.setdefault(normalized, line.strip())
    parsed_rows: list[tuple[str, float, float]] = []
    with timeline.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            text = str(row.get("text", "")).strip()
            raw_time = str(row.get("time", "")).strip()
            # Older step-02 CSVs wrote the comma-separated time tuple without
            # quoting it. DictReader then places the remaining tuple fields in
            # the None-valued overflow column; join them back before parsing.
            overflow = row.get(None, [])
            if isinstance(overflow, list) and overflow:
                raw_time = ",".join([raw_time, *(str(item).strip() for item in overflow)])
            match = re.fullmatch(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,.*\]", raw_time)
            if not text or not match:
                continue
            start = max(0.0, min(float(match.group(1)), duration))
            end = max(start, min(float(match.group(2)), duration))
            if end <= start:
                continue
            source_caption = punctuation_map.get(re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text), text)
            parsed_rows.append((source_caption, start, end))
    if not parsed_rows:
        raise ValueError(f"voice sentence timeline has no valid rows: {timeline}")

    from src.application.project_compiler import split_subtitle_text, distribute_subtitle_timing
    from src.prepare.voice_timeline import build_ref_to_hyp_map, nearest_mapped_index, normalize_for_alignment, transcribe_timed_chars
    timed_chars = None
    mapping = None
    reference = "".join(normalize_for_alignment(item[0]) for item in parsed_rows)
    if audio_path and audio_path.is_file():
        try:
            timed_chars = transcribe_timed_chars(audio_path, model_name="small", device="cpu", compute_type="int8")
            mapping = build_ref_to_hyp_map(reference, "".join(item.char for item in timed_chars))
            if len(mapping) / max(1, len(reference)) < 0.65:
                timed_chars = None
        except (ImportError, OSError, RuntimeError, ValueError):
            timed_chars = None
    captions: list[dict[str, Any]] = []
    reference_cursor = 0
    for source_caption, row_start, row_end in parsed_rows:
        chunks = split_subtitle_text(source_caption, max_chars=24)
        ranges: list[tuple[float, float]] = []
        normalized_source = normalize_for_alignment(source_caption)
        local_cursor = 0
        if timed_chars is not None and mapping is not None:
            for chunk in chunks:
                normalized_chunk = normalize_for_alignment(chunk)
                chunk_start = normalized_source.find(normalized_chunk, local_cursor)
                if chunk_start < 0 or not normalized_chunk:
                    ranges = []
                    break
                chunk_end = chunk_start + len(normalized_chunk) - 1
                start_hyp = nearest_mapped_index(mapping, reference_cursor + chunk_start, ref_limit=len(reference))
                end_hyp = nearest_mapped_index(mapping, reference_cursor + chunk_end, ref_limit=len(reference))
                if start_hyp is None or end_hyp is None:
                    ranges = []
                    break
                start_hyp, end_hyp = sorted((start_hyp, end_hyp))
                start = max(row_start, timed_chars[start_hyp].start_seconds - CAPTION_ASR_LEAD_SECONDS)
                end = min(row_end, timed_chars[end_hyp].end_seconds - CAPTION_ASR_LEAD_SECONDS)
                ranges.append((start, max(start + 0.05, end)))
                local_cursor = chunk_start + len(normalized_chunk)
        if len(ranges) != len(chunks):
            ranges = [(a / 1000, b / 1000) for a, b in distribute_subtitle_timing(chunks, round(row_start * 1000), round(row_end * 1000))]
        for chunk, (start_ms, end_ms) in zip(chunks, ranges):
            captions.append({"start": round(start_ms, 3), "end": round(end_ms, 3), "text": chunk})
        reference_cursor += len(normalized_source)
    captions.sort(key=lambda item: (item["start"], item["end"]))
    return captions


def keyword_for(title: str, voice: str) -> str:
    title = title.strip()
    if title and title in voice:
        return title
    phrases = re.findall(r"[\u4e00-\u9fff]{4,10}", voice)
    return phrases[0] if phrases else (title or voice[:8] or "重点")


def read_shots(project: Path, duration: float) -> list[dict[str, Any]]:
    timeline = project / "shot_timeline_source_time.csv"
    if not timeline.is_file():
        raise FileNotFoundError(f"missing shot timeline: {timeline}")
    shots: list[dict[str, Any]] = []
    with timeline.open("r", encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            start = float(str(row.get("开始时间ms", "0"))) / 1000
            end = float(str(row.get("结束时间ms", "0"))) / 1000
            start = max(0.0, min(start, duration - 1 / 30))
            end = max(start + 1 / 30, min(end, duration))
            title = str(row.get("分镜标题", "")).strip() or f"知识节点 {index:02d}"
            voice = str(row.get("分镜对应原始文案内容", "")).strip()
            if not voice:
                raise ValueError(f"shot {index} has no narration text")
            shots.append({
                "id": str(row.get("shot_id", "")).strip() or str(index),
                "title": title,
                "voice": voice,
                "keyword": keyword_for(title, voice),
                "visual": f"{title}，单张白底手绘MG插画，黑色手绘线条，蓝青黄橙强调色，画面主体清晰，避免可读文字。",
                "asset_type": "image",
                "source": "",
                "start": round(start, 3),
                "end": round(end, 3),
            })
    if not 4 <= len(shots) <= 10:
        raise ValueError(f"scripted Remotion requires 4 to 10 shots, got {len(shots)}")
    return shots


def image_for_shot(asset_dir: Path, shot_id: str, fallback_index: int, used: set[Path]) -> Path:
    candidates = sorted(asset_dir.glob(f"*{shot_id}_img*.png"))
    if not candidates:
        candidates = sorted(asset_dir.glob(f"s{shot_id}_img*.png"))
    if not candidates:
        candidates = sorted(path for path in asset_dir.glob("*.png") if "_img" in path.name)
    candidates = [path for path in candidates if path not in used]
    if not candidates:
        raise FileNotFoundError(f"no image asset available for shot {shot_id} in {asset_dir}")
    return candidates[min(fallback_index, len(candidates) - 1)]


def copy_white_asset(source: Path, target: Path) -> None:
    original = source.parent / "originals" / source.name
    source = original if original.is_file() else source
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        background.alpha_composite(image)
        target.parent.mkdir(parents=True, exist_ok=True)
        background.convert("RGB").save(target, format="PNG", optimize=True)


def build_from_project(
    project: Path,
    title: str,
    narration_override: Path | None = None,
    timeline_override: Path | None = None,
) -> Path:
    project = project.expanduser().resolve()
    narration = (narration_override or (project / "narration.wav")).expanduser().resolve()
    # Remotion owns a separate one-composite-per-shot asset directory. Older
    # prepared projects may only have the Jianying directory, so retain a
    # read-only fallback for backwards compatibility.
    source_assets = project / "generated_assets_remotion"
    if not source_assets.is_dir():
        source_assets = project / "generated_assets_plus"
    if not narration.is_file():
        raise FileNotFoundError(f"missing narration: {narration}")
    if not source_assets.is_dir():
        raise FileNotFoundError(f"missing generated assets: {source_assets}")

    duration = duration_seconds(narration)
    project_title = title.strip() or project.parent.name
    shots = read_shots(project, duration)
    screenplay = {"title": project_title, "voice": "".join(item["voice"] for item in shots), "shots": shots}
    facts = build_scene_facts(screenplay, duration)
    caption_source = timeline_override or project
    facts["captions"] = read_project_captions(caption_source, duration, project, narration)
    validate_scene_facts(facts)
    storyboard = {
        "style_id": VISUAL_STYLE_ID,
        "density_policy": "one-composite-illustration-per-scene",
        "shots": [
            {
                "shot_id": shot["id"],
                "background_summary": "opaque white paper",
                "elements": [{"element_id": f"e{index + 1:02d}", "content": shot["visual"], "role": "single_composite"}],
                "element_count": 1,
                "asset_count": 1,
            }
            for index, shot in enumerate(shots)
        ],
    }
    visual_plan = direct_scenes(facts, storyboard)
    layout = layout_world(facts)
    run = RUNS_ROOT / "_agent" / slug(project_title)
    assets = run / "assets"
    if run.exists():
        shutil.rmtree(run)
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(narration, run / "narration.wav")

    media: dict[str, dict[str, str]] = {}
    used: set[Path] = set()
    for index, shot in enumerate(shots):
        source = image_for_shot(source_assets, str(shot["id"]), index, used)
        used.add(source)
        target = assets / f"shot_{index + 1:02d}.png"
        copy_white_asset(source, target)
        media[shot["id"]] = {
            "asset": target.name,
            "mediaType": "image",
            "assetSource": "agent-prepared",
            "styleId": VISUAL_STYLE_ID,
            "assetCount": 1,
            "cacheBust": str(target.stat().st_mtime_ns),
        }

    manifest = make_manifest(facts, visual_plan, layout, media, "audio/narration.wav")
    # The agent runner uses this ownership marker to prevent a later topic
    # from rendering with the previous topic's manifest.
    manifest["projectDir"] = str(project)
    write_json(run / "script.json", screenplay)
    write_json(run / "scene_facts.json", facts)
    write_json(run / "storyboard.json", storyboard)
    write_json(run / "visual_plan.json", visual_plan)
    write_json(run / "layout.json", layout)
    write_json(run / "density_audit.json", audit_density(screenplay, facts, media, storyboard))
    write_json(run / "manifest.json", manifest)
    write_json(run / "source.json", {"projectDir": str(project), "title": project_title})
    write_json(ROOT / "out" / "source.json", {"projectDir": str(project), "title": project_title, "runDir": str(run)})

    public_assets = PUBLIC_ROOT / "assets"
    public_assets.mkdir(parents=True, exist_ok=True)
    for old in public_assets.glob("*.png"):
        old.unlink()
    for item in assets.glob("*.png"):
        shutil.copy2(item, public_assets / item.name)
    public_audio = PUBLIC_ROOT / "audio"
    public_audio.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run / "narration.wav", public_audio / "narration.wav")
    write_json(PUBLIC_ROOT / "manifest.json", manifest)
    print(f"adapted={project}")
    print(f"manifest={PUBLIC_ROOT / 'manifest.json'}")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt an agent project to the latest scripted Remotion renderer")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--narration-path", type=Path, default=None, help="Remotion-only narration WAV override")
    parser.add_argument("--timeline-path", type=Path, default=None, help="Remotion-only sentence timeline CSV override")
    args = parser.parse_args()
    build_from_project(args.project_dir, args.title, args.narration_path, args.timeline_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
