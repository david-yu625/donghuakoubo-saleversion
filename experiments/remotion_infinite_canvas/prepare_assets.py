"""Prepare copies of existing project assets for the isolated Remotion sample."""

from __future__ import annotations

import json
import argparse
import csv
import hashlib
import random
import shutil
import sys
import wave
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.project_reader import read_subtitles
from src.application.project_compiler import split_subtitle_text, distribute_subtitle_timing
EXPERIMENT = Path(__file__).resolve().parent
PROJECT = ROOT / "output" / "计算机硬盘的起源与发展" / "landscape"
PUBLIC = EXPERIMENT / "public"
OUT = EXPERIMENT / "out"

ACCENTS = ("#ff4d4d", "#2673ff", "#8d4dff", "#0b9d77", "#ff8a00", "#e64291")
EFFECTS = (
    "reveal",
    "process",
    "timeline",
    "compare",
    "spotlight",
    "data",
    "orbit",
    "parallax",
    "scan",
    "burst",
)
LAYOUTS = ("horizontal", "staggered", "vertical", "grid")
EFFECT_CATALOG = json.loads((EXPERIMENT / "effect_catalog.json").read_text(encoding="utf-8"))
IMAGE_ANIMATIONS = tuple(EFFECT_CATALOG["image_animations"])
TRANSITIONS = tuple(EFFECT_CATALOG["transitions"])
CAMERA_MOVES = tuple(EFFECT_CATALOG["camera_moves"])


def _seeded_rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def effect_for_caption(text: str, index: int, seed: str, avoid: str = "") -> str:
    """Choose a semantic but reproducibly shuffled visual treatment."""
    normalized = text.replace(" ", "")
    preferred: tuple[str, ...] = ()
    if any(token in normalized for token in ("对比", "区别", "之前", "现在", "旧", "新")):
        preferred = ("compare", "parallax", "scan")
    elif any(token in normalized for token in ("年代", "历史", "起源", "发展", "时间", "年份", "年")):
        preferred = ("timeline", "orbit", "reveal")
    elif any(token in normalized for token in ("步骤", "流程", "原理", "过程", "如何", "连接", "传输", "工作")):
        preferred = ("process", "burst", "parallax")
    elif any(token in normalized for token in ("容量", "速度", "比例", "数字", "多少", "倍", "数据", "增长")):
        preferred = ("data", "scan", "orbit")
    elif any(token in normalized for token in ("问题", "风险", "错误", "失败", "注意", "攻击", "为什么")):
        preferred = ("spotlight", "burst", "scan")
    pool = list(dict.fromkeys((*preferred, *EFFECTS)))
    _seeded_rng(f"effect:{seed}:{index}").shuffle(pool)
    for effect in pool:
        if effect != avoid:
            return effect
    return pool[0]


def layout_for_shot(seed: str, image_count: int) -> str:
    """Choose only compositions that support the shot's image count."""
    if image_count <= 1:
        return "solo"
    choices = ("horizontal", "staggered", "vertical") if image_count == 2 else LAYOUTS
    return _seeded_rng(f"layout:{seed}:{image_count}").choice(choices)


def image_animation_for_asset(seed: str, index: int, avoid: str = "") -> str:
    choices = [item for item in IMAGE_ANIMATIONS if item != avoid] or list(IMAGE_ANIMATIONS)
    _seeded_rng(f"image-animation:{seed}:{index}").shuffle(choices)
    return choices[0]


def transition_for_shot(seed: str, index: int, avoid: str = "") -> str:
    choices = [item for item in TRANSITIONS if item != avoid] or list(TRANSITIONS)
    _seeded_rng(f"shot-transition:{seed}:{index}").shuffle(choices)
    return choices[0]


def varied_effect_sequence(choices: tuple[str, ...], count: int, seed: str) -> list[str]:
    """Use the complete library before repeating, including across shot boundaries."""
    if not choices or count <= 0:
        return []
    rng = _seeded_rng(seed)
    result: list[str] = []
    while len(result) < count:
        cycle = list(choices)
        rng.shuffle(cycle)
        if result and len(cycle) > 1 and cycle[0] == result[-1]:
            cycle[0], cycle[1] = cycle[1], cycle[0]
        result.extend(cycle)
    return result[:count]


def prepare_asset(source: Path, destination: Path) -> None:
    """Copy a complete illustration card without destructive background removal."""
    # These generated storyboard images use white paper, shadows, and
    # anti-aliased edges as part of the artwork. Removing near-white pixels
    # makes most of the illustration translucent and produces dirty halos.
    # InfiniteCanvas places cards in a non-overlapping layout, so alpha is
    # optional rather than a prerequisite.
    original = source.parent / "originals" / source.name
    # The shared asset folder may already contain a destructive cutout.
    # Recover the untouched illustration when the original is available.
    with Image.open(original if original.is_file() else source) as opened:
        image = opened.convert("RGBA")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为无限画布渲染准备一个项目的素材清单")
    parser.add_argument("--project-dir", type=Path, default=PROJECT)
    parser.add_argument("--title", default="")
    parser.add_argument("--skip-manifest", action="store_true", help="只准备素材，不生成空间规划清单")
    return parser.parse_args()


def read_duration(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as audio:
        return audio.getnframes() / max(1, audio.getframerate())


def read_project_captions(project: Path) -> list[dict[str, object]]:
    """Read spoken sentences, never chapter headings, for the subtitle lane."""
    timeline = project / "timeline.csv"
    if not timeline.is_file():
        raise FileNotFoundError(f"缺少旁白字幕时间轴：{timeline}")
    copy_path = project / "wenan.txt"
    copy_lines = copy_path.read_text(encoding="utf-8-sig").splitlines() if copy_path.is_file() else []
    captions = []
    for text, start_ms, end_ms in read_subtitles(timeline, copy_lines):
        chunks = split_subtitle_text(text, max_chars=26)
        for chunk, (start, end) in zip(chunks, distribute_subtitle_timing(chunks, start_ms, end_ms)):
            captions.append({"start": start / 1000, "end": end / 1000, "text": chunk})
    if not captions:
        raise ValueError(f"旁白字幕时间轴没有有效内容：{timeline}")
    return captions


def read_project_chapters(project: Path) -> list[dict[str, object]]:
    shot_path = project / "shot_timeline_source_time.csv"
    if not shot_path.is_file():
        return []
    captions: list[dict[str, object]] = []
    with shot_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                start = float(str(row.get("开始时间ms", "0"))) / 1000
                end = float(str(row.get("结束时间ms", "0"))) / 1000
            except ValueError:
                continue
            text = str(row.get("分镜标题", "")).strip() or str(
                row.get("分镜对应原始文案内容", "")
            ).strip()
            if end > start and text:
                captions.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text,
                        "shot_id": str(row.get("shot_id", "")).strip(),
                    }
                )
    return captions


def read_asset_timings(project: Path) -> dict[str, dict[str, object]]:
    """Read per-asset timing and shot ownership from the shared element timeline."""
    timeline_path = project / "element_timeline_with_assets.csv"
    if not timeline_path.is_file():
        return {}
    timings: dict[str, dict[str, object]] = {}
    with timeline_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_path = str(row.get("asset_path", "")).strip()
            asset_name = Path(raw_path).name
            if not asset_name:
                continue
            try:
                start = float(str(row.get("start_ms", "0"))) / 1000
                end = float(str(row.get("end_ms", "0"))) / 1000
            except ValueError:
                continue
            if end <= start:
                continue
            timings[asset_name] = {
                "start": start,
                "end": end,
                "shot_id": str(row.get("shot_id", "")).strip(),
                "role": str(row.get("role", "")).strip(),
            }
    return timings


def build_nodes(
    asset_names: list[str],
    captions: list[dict[str, object]],
    duration: float,
    asset_timings: dict[str, dict[str, object]] | None = None,
    scene_seed: str = "",
) -> list[dict[str, object]]:
    if not asset_names:
        return []
    node_count = len(asset_names)
    duration = max(1 / 30, float(duration))
    # Place shot groups on a deterministic serpentine world grid. Effects may
    # vary by shot, but layout coordinates never depend on random choices.
    nodes: list[dict[str, object]] = []
    caption_by_shot = {
        str(caption.get("shot_id", "")): caption
        for caption in captions
        if str(caption.get("shot_id", ""))
    }
    timings = asset_timings or {}
    # Keep assets from the same shot close together. The camera can then frame
    # the shot as a unit instead of crossing a huge canvas gap for every image.
    shot_order: dict[str, int] = {}
    shot_assets: dict[str, list[str]] = {}
    for asset in asset_names:
        timing = timings.get(asset, {})
        shot_id = str(timing.get("shot_id", "")).strip() or f"asset:{asset}"
        if shot_id not in shot_order:
            shot_order[shot_id] = len(shot_order)
        shot_assets.setdefault(shot_id, []).append(asset)
    shot_effects: dict[str, str] = {}
    shot_layouts: dict[str, str] = {}
    previous_effect = ""
    for shot_id, group_assets in shot_assets.items():
        caption = caption_by_shot.get(shot_id, {})
        title = str(caption.get("text", "")).replace("\n", " ").strip()
        shot_seed = f"{scene_seed}:{shot_id}:{title}:{','.join(group_assets)}"
        shot_effects[shot_id] = effect_for_caption(title, shot_order.get(shot_id, 0), shot_seed, previous_effect)
        shot_layouts[shot_id] = layout_for_shot(shot_seed, len(group_assets))
        previous_effect = shot_effects[shot_id]
    for index, asset in enumerate(asset_names):
        timing = timings.get(asset, {})
        caption = caption_by_shot.get(str(timing.get("shot_id", "")))
        if caption is None:
            caption = captions[min(index, len(captions) - 1)] if captions else {}
        start = float(timing.get("start", caption.get("start", duration * index / max(1, node_count))))
        end = float(timing.get("end", caption.get("end", duration)))
        start = max(0.0, min(duration - 1 / 30, start))
        end = max(start + 1 / 30, min(duration, end))
        title = str(caption.get("text", "")).replace("\n", " ").strip()
        shot_id = str(timing.get("shot_id", "")).strip() or f"asset:{asset}"
        shot_index = shot_order.get(shot_id, index)
        group_assets = shot_assets.get(shot_id, [asset])
        within_shot = group_assets.index(asset)
        if within_shot + 1 < len(group_assets):
            next_start = float(timings.get(group_assets[within_shot + 1], {}).get("start", end))
            next_start = max(0.0, min(duration, next_start))
            # Full-frame illustrations are alternatives, not transparent layers.
            # Keep a short overlap for a clean crossfade, then retire the old one.
            end = min(end, next_start + 8 / 30, duration)
            end = max(start + 1 / 30, end)
        # Shot groups follow a stable serpentine world route. Each stop has
        # enough room for the widest supported composition.
        row, column = divmod(shot_index, 3)
        base_x = 1500 + column * 3300
        if row % 2:
            base_x = 1500 + (2 - column) * 3300
        base_y = 760 + row * 2100
        layout = shot_layouts.get(shot_id, "center")
        width = 1120
        height = 760
        # Pack the complete shot group from measured card widths. This keeps
        # every image separated by a real gap instead of relying on a fixed
        # center offset that becomes too small for wide illustrations.
        group_gap = 180
        if layout == "vertical":
            x = base_x
            group_height = len(group_assets) * height + max(0, len(group_assets) - 1) * group_gap
            y = base_y - group_height / 2 + height / 2 + within_shot * (height + group_gap)
        elif layout == "grid":
            columns = 2
            rows = (len(group_assets) + columns - 1) // columns
            group_width = columns * width + (columns - 1) * group_gap
            group_height = rows * height + (rows - 1) * group_gap
            grid_column, grid_row = within_shot % columns, within_shot // columns
            x = base_x - group_width / 2 + width / 2 + grid_column * (width + group_gap)
            y = base_y - group_height / 2 + height / 2 + grid_row * (height + group_gap)
        else:
            group_width = len(group_assets) * width + max(0, len(group_assets) - 1) * group_gap
            group_left = base_x - group_width / 2
            x = group_left + width / 2 + within_shot * (width + group_gap)
            y = base_y + (120 if layout == "staggered" and within_shot % 2 else 0)
        nodes.append({
            "asset": asset,
            "x": x,
            "y": y,
            "width": width,
            "start": round(start * 30),
            "end": round(end * 30),
            "eyebrow": f"节点 {index + 1:02d}",
            "headline": title[:28] or f"知识节点 {index + 1}",
            "accent": ACCENTS[index % len(ACCENTS)],
            "rotate": (-2, 2, -1, 1)[index % 4],
            "effect": shot_effects.get(shot_id, "reveal"),
            "layout": layout,
            "role": str(timing.get("role", "")),
            "shot_id": shot_id,
        })
    # Assign per image in playback order, not once per shot. Shot boundaries
    # must not reset the shuffle and cause identical neighboring animations.
    nodes.sort(key=lambda node: (node["start"], node["asset"]))
    animations = varied_effect_sequence(IMAGE_ANIMATIONS, len(nodes), f"images:{scene_seed}")
    transitions = varied_effect_sequence(TRANSITIONS, max(0, len(nodes) - 1), f"transitions:{scene_seed}")
    camera_moves = varied_effect_sequence(CAMERA_MOVES, max(0, len(nodes) - 1), f"camera:{scene_seed}")
    for index, node in enumerate(nodes):
        animation = animations[index]
        transition = transitions[index - 1] if index else "glide"
        node["image_animation"] = animation
        node["image_animation_frames"] = EFFECT_CATALOG["image_animations"][animation]["duration_frames"]
        node["transition"] = transition
        node["transition_frames"] = EFFECT_CATALOG["transitions"][transition]["duration_frames"] if index else 0
        camera_move = camera_moves[index - 1] if index else "overview"
        node["camera_move"] = camera_move
        node["camera_frames"] = EFFECT_CATALOG["camera_moves"][camera_move]["duration_frames"]
    return nodes


def main() -> int:
    args = parse_args()
    project = args.project_dir.expanduser().resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    assets_dir = PUBLIC / "assets"
    audio_dir = PUBLIC / "audio"
    assets_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    source_assets = sorted((project / "generated_assets_plus").glob("*_img*.png"))
    if not source_assets:
        source_assets = sorted((project / "generated_assets_plus").glob("*.png"))
    if not source_assets:
        raise FileNotFoundError(f"没有找到图片素材：{project / 'generated_assets_plus'}")
    for old_asset in assets_dir.glob("*.png"):
        old_asset.unlink()
    for source in source_assets:
        prepare_asset(source, assets_dir / source.name)
    narration = project / "narration.wav"
    if not narration.is_file():
        raise FileNotFoundError(f"没有找到旁白：{narration}")
    shutil.copy2(narration, audio_dir / "narration.wav")
    asset_names = [path.name for path in source_assets]
    (OUT / "source.json").write_text(
        json.dumps(
            {"projectDir": str(project), "title": args.title.strip() or project.parent.name},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    if args.skip_manifest:
        print(f"Prepared {len(asset_names)} source assets from {project}")
        return 0
    duration = read_duration(narration)
    captions = read_project_captions(project)
    chapters = read_project_chapters(project)
    asset_timings = read_asset_timings(project)
    if not captions:
        captions = [{"start": 0.0, "end": duration, "text": args.title.strip() or project.parent.name}]
    manifest = {
        "title": args.title.strip() or project.parent.name,
        "durationSeconds": duration,
        "captions": captions,
        "chapters": chapters,
        "assets": asset_names,
        "nodes": build_nodes(asset_names, chapters, duration, asset_timings, args.title.strip() or project.parent.name),
    }
    (PUBLIC / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Prepared {len(asset_names)} source assets from {project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
