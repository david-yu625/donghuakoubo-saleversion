"""Duplicate a Jianying draft and replace the public-service and global-title fonts."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from ..paths import default_draft_folder
from ..renderers.jianying_renderer import cached_font_path, draft
from .fix_existing_draft_title import fix_title_presentation
from .tune_existing_draft import update_draft_metadata

BANNED_FONT_IDS = {
    draft.FontType.站酷酷黑体.value.resource_id,
    draft.FontType.古印宋简.value.resource_id,
}


def font_style(font_type) -> dict[str, str]:
    path = cached_font_path(font_type)
    if path is None:
        raise FileNotFoundError(f"Jianying font is not cached: {font_type.value.name}")
    return {"id": font_type.value.resource_id, "path": path.replace("\\", "/")}


def replace_selected_fonts(content: dict[str, Any]) -> list[tuple[str, str]]:
    text_materials = {
        material["id"]: material
        for material in content.get("materials", {}).get("texts", [])
    }
    changed: list[tuple[str, str]] = []
    for track in content.get("tracks", []):
        for segment in track.get("segments", []):
            material = text_materials.get(segment.get("material_id"))
            if material is None:
                continue
            material_content = json.loads(material["content"])
            text = str(material_content.get("text", ""))
            styles = material_content.get("styles", [])
            if track.get("name") == "global_title":
                font_type = draft.FontType.雅酷黑简
            elif any(style.get("font", {}).get("id") in BANNED_FONT_IDS for style in styles):
                font_type = draft.FontType.ResourceHanRoundedCN_Md
            else:
                font_type = None
            if font_type is None:
                continue
            target_font = font_style(font_type)
            if styles and all(style.get("font", {}).get("id") == target_font["id"] for style in styles):
                continue
            for style in styles:
                style["font"] = target_font
            material["content"] = json.dumps(material_content, ensure_ascii=False, separators=(",", ":"))
            changed.append((text.replace("\n", ""), font_type.value.name))
    return changed


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
    changed = replace_selected_fonts(content)
    if not changed:
        shutil.rmtree(target)
        raise ValueError("No matching fonts were found to replace")

    asset_path = target / "Resources" / "title_bar_yellow_adaptive.png"
    fix_title_presentation(content, asset_path)
    (target / "draft_content.json.bak").write_text(original_content, encoding="utf-8")
    content_path.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    update_draft_metadata(target, args.new_name)

    print(target)
    for text, font_name in changed:
        print(f"font={text}:{font_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
