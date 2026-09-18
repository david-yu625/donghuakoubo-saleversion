"""Prepare copies of existing project assets for the isolated Remotion sample."""

from __future__ import annotations

import json
import argparse
import csv
import shutil
import wave
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = Path(__file__).resolve().parent
PROJECT = ROOT / "output" / "计算机硬盘的起源与发展" / "landscape"
PUBLIC = EXPERIMENT / "public"
OUT = EXPERIMENT / "out"

ACCENTS = ("#ff4d4d", "#2673ff", "#8d4dff", "#0b9d77", "#ff8a00", "#e64291")


def make_white_transparent(source: Path, destination: Path) -> None:
    """Keep the original drawing while making its near-white paper transparent."""
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    pixels = []
    for red, green, blue, alpha in image.getdata():
        whiteness = min(red, green, blue)
        if whiteness >= 250:
            pixels.append((red, green, blue, 0))
        elif whiteness >= 225 and max(red, green, blue) - whiteness < 28:
            pixels.append((red, green, blue, round(alpha * (250 - whiteness) / 25)))
        else:
            pixels.append((red, green, blue, alpha))
    image.putdata(pixels)
    box = image.getbbox()
    if box is not None:
        image = image.crop(box)
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
                captions.append({"start": start, "end": end, "text": text})
    return captions


def build_nodes(asset_names: list[str], captions: list[dict[str, object]], duration: float) -> list[dict[str, object]]:
    if not asset_names:
        return []
    node_count = len(asset_names)
    # A loose zig-zag path keeps the camera moving through a spatial story.
    nodes: list[dict[str, object]] = []
    for index, asset in enumerate(asset_names):
        caption = captions[min(index, len(captions) - 1)] if captions else {}
        start = float(caption.get("start", duration * index / max(1, node_count)))
        title = str(caption.get("text", "")).replace("\n", " ").strip()
        x = 850 + index * 1080
        y = 520 + (index % 3 - 1) * 530
        if index % 2:
            y -= 170
        nodes.append({
            "asset": asset,
            "x": x,
            "y": y,
            "width": max(620, 980 - (index % 3) * 90),
            "start": round(start * 30),
            "eyebrow": f"节点 {index + 1:02d}",
            "headline": title[:28] or f"知识节点 {index + 1}",
            "accent": ACCENTS[index % len(ACCENTS)],
            "rotate": (-2, 2, -1, 1)[index % 4],
        })
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
    frames_dir = OUT / "frames"
    if frames_dir.is_dir():
        shutil.rmtree(frames_dir)
    rendered_output = OUT / "infinite-canvas.mp4"
    if rendered_output.exists():
        rendered_output.unlink()
    for source in source_assets:
        make_white_transparent(source, assets_dir / source.name)
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
    if not captions:
        captions = [{"start": 0.0, "end": duration, "text": args.title.strip() or project.parent.name}]
    manifest = {
        "title": args.title.strip() or project.parent.name,
        "durationSeconds": duration,
        "captions": captions,
        "assets": asset_names,
        "nodes": build_nodes(asset_names, captions, duration),
    }
    (PUBLIC / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Prepared {len(asset_names)} source assets from {project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
