"""Duplicate an existing Jianying draft and apply narrowly scoped visual fixes."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from ..paths import default_draft_folder
from ..renderers.jianying_renderer import global_title_bar_scale


GREEN_REPLACEMENTS = {
    "#B8F23D": "#5F3DC4",
    "#7AE582": "#D9480F",
}
SCALE_KEYFRAME_TYPES = {"KFTypeScaleX", "KFTypeScaleY", "KFTypeUniformScale"}


def rgb_to_hex(color: list[float]) -> str:
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in color[:3])


def hex_to_rgb(color: str) -> list[float]:
    raw = color.lstrip("#")
    return [int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4)]


def replace_green_keyword_colors(content: dict[str, Any]) -> list[tuple[str, str, str]]:
    text_materials = {
        material["id"]: material
        for material in content.get("materials", {}).get("texts", [])
    }
    changed: list[tuple[str, str, str]] = []
    for track in content.get("tracks", []):
        name = str(track.get("name", ""))
        if track.get("type") != "text" or not name.startswith("layout_") or "_txt" not in name:
            continue
        for segment in track.get("segments", []):
            material = text_materials.get(segment.get("material_id"))
            if material is None:
                continue
            material_content = json.loads(material["content"])
            material_changed = False
            for style in material_content.get("styles", []):
                solid = style.get("fill", {}).get("content", {}).get("solid", {})
                color = solid.get("color")
                if not isinstance(color, list) or len(color) < 3:
                    continue
                original = rgb_to_hex(color)
                replacement = GREEN_REPLACEMENTS.get(original)
                if replacement is None:
                    continue
                replacement_rgb = hex_to_rgb(replacement)
                solid["color"] = replacement_rgb
                for stroke in style.get("strokes", []):
                    stroke_solid = stroke.get("content", {}).get("solid", {})
                    if rgb_to_hex(stroke_solid.get("color", [])) == original:
                        stroke_solid["color"] = replacement_rgb
                changed.append((material_content.get("text", ""), original, replacement))
                material_changed = True
            if material_changed:
                material["content"] = json.dumps(material_content, ensure_ascii=False, separators=(",", ":"))
    return changed


def enlarge_layout_images(content: dict[str, Any], factor: float) -> int:
    changed = 0
    for track in content.get("tracks", []):
        name = str(track.get("name", ""))
        if track.get("type") != "video" or not name.startswith("layout_"):
            continue
        for segment in track.get("segments", []):
            scale = segment.get("clip", {}).get("scale", {})
            for axis in ("x", "y"):
                if isinstance(scale.get(axis), (int, float)):
                    scale[axis] *= factor
            for keyframe_group in segment.get("common_keyframes", []):
                if keyframe_group.get("property_type") not in SCALE_KEYFRAME_TYPES:
                    continue
                for keyframe in keyframe_group.get("keyframe_list", []):
                    keyframe["values"] = [
                        value * factor if isinstance(value, (int, float)) else value
                        for value in keyframe.get("values", [])
                    ]
            changed += 1
    return changed


def fit_title_bar_to_text(content: dict[str, Any]) -> tuple[str, float]:
    text_materials = {
        material["id"]: material
        for material in content.get("materials", {}).get("texts", [])
    }
    title = ""
    for track in content.get("tracks", []):
        if track.get("name") != "global_title":
            continue
        segments = track.get("segments", [])
        if segments:
            material = text_materials.get(segments[0].get("material_id"))
            if material is not None:
                title = str(json.loads(material["content"]).get("text", "")).strip()
        break
    if not title:
        raise ValueError("Draft does not contain a readable global title")

    canvas_width = int(content.get("canvas_config", {}).get("width", 1080))
    scale_x = global_title_bar_scale(title, canvas_width)
    for track in content.get("tracks", []):
        if track.get("name") != "global_title_bar":
            continue
        for segment in track.get("segments", []):
            segment.setdefault("clip", {}).setdefault("scale", {})["x"] = scale_x
        return title, scale_x
    raise ValueError("Draft does not contain a global title bar")


def update_draft_metadata(path: Path, draft_name: str) -> None:
    metadata_path = path / "draft_meta_info.json"
    if not metadata_path.exists():
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    now_us = int(time.time() * 1_000_000)
    metadata["draft_name"] = draft_name
    metadata["draft_fold_path"] = path.as_posix()
    metadata["draft_id"] = str(uuid.uuid4()).upper()
    metadata["tm_draft_create"] = now_us
    metadata["tm_draft_modified"] = now_us
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_name")
    parser.add_argument("new_name")
    parser.add_argument("--draft-folder", type=Path, default=default_draft_folder())
    parser.add_argument("--image-scale", type=float, default=1.12)
    args = parser.parse_args()

    draft_folder = args.draft_folder.expanduser().resolve()
    source = draft_folder / args.source_name
    target = draft_folder / args.new_name
    if not source.is_dir():
        raise FileNotFoundError(f"Source draft does not exist: {source}")
    if target.exists():
        raise FileExistsError(f"Target draft already exists: {target}")
    if not 1.0 < args.image_scale <= 1.25:
        raise ValueError("Image scale must be greater than 1.0 and at most 1.25")

    shutil.copytree(source, target)
    locked = target / ".locked"
    if locked.exists():
        locked.unlink()

    content_path = target / "draft_content.json"
    content = json.loads(content_path.read_text(encoding="utf-8"))
    original_content = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    color_changes = replace_green_keyword_colors(content)
    image_count = enlarge_layout_images(content, args.image_scale)
    title, title_scale = fit_title_bar_to_text(content)

    (target / "draft_content.json.bak").write_text(original_content, encoding="utf-8")
    content_path.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    update_draft_metadata(target, args.new_name)

    print(target)
    print(f"green_text_replacements={len(color_changes)}")
    print(f"layout_images_scaled={image_count}")
    print(f"image_scale={args.image_scale:.3f}")
    print(f"title={title}")
    print(f"title_bar_scale_x={title_scale:.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
