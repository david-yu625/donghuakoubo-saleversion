"""Duplicate a Jianying draft and remove one specific text animation effect."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from ..paths import default_draft_folder
from .tune_existing_draft import update_draft_metadata


CHALK_OUTLINE_RESOURCE_ID = "7399879712140431883"


def remove_text_animation(content: dict[str, Any], resource_id: str) -> list[str]:
    animation_materials = content.get("materials", {}).get("material_animations", [])
    text_materials = {
        material["id"]: json.loads(material["content"])
        for material in content.get("materials", {}).get("texts", [])
    }
    animation_refs_by_track: dict[str, list[str]] = {}
    for track in content.get("tracks", []):
        for segment in track.get("segments", []):
            for reference in segment.get("extra_material_refs", []):
                animation_refs_by_track.setdefault(reference, []).append(
                    str(text_materials.get(segment.get("material_id"), {}).get("text", ""))
                )

    changed_texts: list[str] = []
    for material in animation_materials:
        animations = material.get("animations", [])
        removed = [animation for animation in animations if str(animation.get("resource_id")) == resource_id]
        if not removed:
            continue
        material["animations"] = [
            animation for animation in animations if str(animation.get("resource_id")) != resource_id
        ]
        changed_texts.extend(animation_refs_by_track.get(material.get("id"), []))
    return changed_texts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_name")
    parser.add_argument("new_name")
    parser.add_argument("--draft-folder", type=Path, default=default_draft_folder())
    parser.add_argument("--resource-id", default=CHALK_OUTLINE_RESOURCE_ID)
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
    changed_texts = remove_text_animation(content, args.resource_id)
    if not changed_texts:
        shutil.rmtree(target)
        raise ValueError(f"Text animation resource was not found: {args.resource_id}")

    (target / "draft_content.json.bak").write_text(original_content, encoding="utf-8")
    content_path.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    update_draft_metadata(target, args.new_name)

    print(target)
    print(f"removed_effect_count={len(changed_texts)}")
    for text in changed_texts:
        print(f"text={text.replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
