"""Duplicate a Jianying draft and restore a larger self-contained adaptive title bar."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from ..paths import default_draft_folder
from ..renderers.jianying_renderer import (
    create_title_bar_asset,
    global_title_presentation,
    title_bar_width,
)
from .tune_existing_draft import update_draft_metadata


def fix_title_presentation(content: dict[str, Any], asset_path: Path) -> tuple[str, float, int]:
    text_materials = {
        material["id"]: material
        for material in content.get("materials", {}).get("texts", [])
    }
    video_materials = {
        material["id"]: material
        for material in content.get("materials", {}).get("videos", [])
    }

    title = ""
    previous_size = 0.0
    canvas_width = int(content.get("canvas_config", {}).get("width", 1080))
    for track in content.get("tracks", []):
        if track.get("name") != "global_title":
            continue
        for segment in track.get("segments", []):
            material = text_materials.get(segment.get("material_id"))
            if material is None:
                continue
            material_content = json.loads(material["content"])
            title = " ".join(str(material_content.get("text", "")).split()).strip()
            presentation = global_title_presentation(title, canvas_width)
            material_content["text"] = presentation.text
            for style in material_content.get("styles", []):
                previous_size = float(style.get("size", previous_size))
                style["size"] = presentation.style_size
                style["range"] = [0, len(presentation.text)]
            material["letter_spacing"] = presentation.letter_spacing * 0.05
            material["content"] = json.dumps(material_content, ensure_ascii=False, separators=(",", ":"))
        break
    if not title:
        raise ValueError("Draft does not contain a readable global title")

    create_title_bar_asset(asset_path, title, canvas_width)
    with Image.open(asset_path) as image:
        asset_width, asset_height = image.size

    found_bar = False
    for track in content.get("tracks", []):
        if track.get("name") != "global_title_bar":
            continue
        for segment in track.get("segments", []):
            scale = segment.setdefault("clip", {}).setdefault("scale", {})
            scale["x"] = 1.0
            scale["y"] = 1.0
            material = video_materials.get(segment.get("material_id"))
            if material is None:
                continue
            absolute_asset_path = str(asset_path.resolve())
            material["path"] = absolute_asset_path
            material["media_path"] = absolute_asset_path
            material["material_name"] = asset_path.name
            material["width"] = asset_width
            material["height"] = asset_height
            found_bar = True
        break
    if not found_bar:
        raise ValueError("Draft does not contain a usable global title bar")
    return title, previous_size, title_bar_width(title, canvas_width)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_name")
    parser.add_argument("new_name")
    parser.add_argument("--draft-folder", type=Path, default=default_draft_folder())
    args = parser.parse_args()

    draft_folder = args.draft_folder.expanduser().resolve()
    source = draft_folder / args.source_name
    target = draft_folder / args.new_name
    if not source.is_dir():
        raise FileNotFoundError(f"Source draft does not exist: {source}")
    if target.exists():
        raise FileExistsError(f"Target draft already exists: {target}")

    shutil.copytree(source, target)
    locked = target / ".locked"
    if locked.exists():
        locked.unlink()

    content_path = target / "draft_content.json"
    content = json.loads(content_path.read_text(encoding="utf-8"))
    original_content = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    asset_path = target / "Resources" / "title_bar_yellow_adaptive.png"
    title, previous_size, bar_width = fix_title_presentation(content, asset_path)
    current_size = global_title_presentation(title).style_size

    (target / "draft_content.json.bak").write_text(original_content, encoding="utf-8")
    content_path.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    update_draft_metadata(target, args.new_name)

    print(target)
    print(f"title={title}")
    print(f"title_size={previous_size:.1f}->{current_size:.1f}")
    print(f"title_bar_width={bar_width}")
    print(f"title_bar_asset={asset_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
