"""Duplicate a Jianying draft and attach a chosen background music source."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..paths import default_draft_folder
from .tune_existing_draft import update_draft_metadata


def probe_duration_us(path: Path) -> int | None:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return round(float(result.stdout.strip()) * 1_000_000)
    except ValueError:
        return None


def attach_background_music(
    content: dict[str, Any],
    music_path: Path,
    *,
    template_content: dict[str, Any] | None = None,
) -> bool:
    tracks = content.setdefault("tracks", [])
    audio_materials = content.setdefault("materials", {}).setdefault("audios", [])
    music_track = next((track for track in tracks if track.get("name") == "background_music"), None)

    if music_track is None and template_content is not None:
        template_track = next(
            (track for track in template_content.get("tracks", []) if track.get("name") == "background_music"),
            None,
        )
        if template_track is not None:
            music_track = copy.deepcopy(template_track)
            tracks.insert(0, music_track)
            template_audio_ids = {
                segment.get("material_id")
                for segment in music_track.get("segments", [])
            }
            template_audios = {
                material["id"]: material
                for material in template_content.get("materials", {}).get("audios", [])
            }
            audio_materials.extend(
                copy.deepcopy(template_audios[material_id])
                for material_id in template_audio_ids
                if material_id in template_audios
            )

    if music_track is None or not music_track.get("segments"):
        return False
    audio_by_id = {material["id"]: material for material in audio_materials}
    duration_us = probe_duration_us(music_path)
    absolute_path = str(music_path.resolve())
    for segment in music_track["segments"]:
        material = audio_by_id.get(segment.get("material_id"))
        if material is None:
            continue
        material["path"] = absolute_path
        material["media_path"] = absolute_path
        material["material_name"] = music_path.name
        if duration_us is not None:
            material["duration"] = duration_us
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_name")
    parser.add_argument("new_name")
    parser.add_argument("--music", type=Path, default=Path("audio/bgm/bgm1.mp4"))
    parser.add_argument("--template-draft", type=Path)
    parser.add_argument("--draft-folder", type=Path, default=default_draft_folder())
    args = parser.parse_args()

    draft_folder = args.draft_folder.expanduser().resolve()
    source = draft_folder / args.source_name
    target = draft_folder / args.new_name
    music = args.music.expanduser()
    if not music.is_absolute():
        music = (Path(__file__).resolve().parents[2] / music).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source draft does not exist: {source}")
    if not music.is_file():
        raise FileNotFoundError(f"Background music does not exist: {music}")
    if target.exists():
        raise FileExistsError(f"Target draft already exists: {target}")

    template_content = None
    if args.template_draft:
        template_path = args.template_draft.expanduser()
        if not template_path.is_absolute():
            template_path = draft_folder / template_path
        template_content = json.loads((template_path / "draft_content.json").read_text(encoding="utf-8"))

    shutil.copytree(source, target)
    locked = target / ".locked"
    if locked.exists():
        locked.unlink()
    content_path = target / "draft_content.json"
    content = json.loads(content_path.read_text(encoding="utf-8"))
    original_content = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    if not attach_background_music(content, music, template_content=template_content):
        shutil.rmtree(target)
        raise ValueError("Could not attach a background_music track")

    (target / "draft_content.json.bak").write_text(original_content, encoding="utf-8")
    content_path.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    update_draft_metadata(target, args.new_name)
    print(target)
    print(f"background_music={music}")
    print(f"duration_us={probe_duration_us(music) or 'unknown'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
