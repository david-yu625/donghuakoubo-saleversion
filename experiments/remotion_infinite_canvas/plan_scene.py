"""Build the spatial scene manifest for the infinite-canvas renderer."""

from __future__ import annotations

import json
from pathlib import Path

from prepare_assets import build_nodes, read_asset_timings, read_duration, read_project_captions, read_project_chapters


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
OUT = ROOT / "out"


def main() -> int:
    source_path = OUT / "source.json"
    if not source_path.is_file():
        raise FileNotFoundError("缺少 Stage 01 产物 out/source.json，请先执行素材准备")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    project = Path(str(source["projectDir"])).expanduser().resolve()
    narration = project / "narration.wav"
    assets = sorted((PUBLIC / "assets").glob("*.png"))
    if not narration.is_file() or not assets:
        raise FileNotFoundError("Stage 01 素材不完整，请重新执行素材准备")
    duration = read_duration(narration)
    captions = read_project_captions(project)
    chapters = read_project_chapters(project)
    asset_timings = read_asset_timings(project)
    if not captions:
        captions = [{"start": 0.0, "end": duration, "text": str(source.get("title", project.parent.name))}]
    asset_names = [path.name for path in assets]
    manifest = {
        "title": str(source.get("title", project.parent.name)),
        "projectDir": str(project),
        "durationSeconds": duration,
        "captions": captions,
        "chapters": chapters,
        "assets": asset_names,
        "nodes": build_nodes(
            asset_names,
            chapters,
            duration,
            asset_timings,
            str(source.get("title", project.parent.name)),
        ),
    }
    output = PUBLIC / "manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scene plan: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
