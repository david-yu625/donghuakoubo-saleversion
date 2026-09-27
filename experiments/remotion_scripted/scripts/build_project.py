from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from remotion_pipeline.config import PUBLIC_ROOT, RUNS_ROOT, load_env
from remotion_pipeline.layouts.world import layout_world
from remotion_pipeline.pipeline.scene_facts import build_scene_facts
from remotion_pipeline.prepare.media import prepare_media
from remotion_pipeline.prepare.script import create_screenplay
from remotion_pipeline.prepare.storyboard import build_storyboard
from remotion_pipeline.prepare.voice import synthesize_narration
from remotion_pipeline.renderers.remotion import make_manifest
from remotion_pipeline.visual_direction.plan import direct_scenes
from remotion_pipeline.pipeline.density import audit_density
from remotion_pipeline.contracts import validate_storyboard
from remotion_pipeline.prepare.copywriting import create_copywriting
from remotion_pipeline.prepare.timeline import build_voice_timeline
from remotion_pipeline.prepare.shot_timeline import create_shot_timeline


def slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value).strip("_") or "scripted_video"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish_assets(run: Path, media: dict[str, dict[str, str]]) -> None:
    for item in media.values():
        source = run / "assets" / item["asset"] if item["mediaType"] == "image" else run / item["asset"]
        # The manifest stores image paths relative to the renderer's `assets/` namespace.
        # Keep that namespace intact when publishing from a run directory.
        target = PUBLIC_ROOT / "assets" / item["asset"] if item["mediaType"] == "image" else PUBLIC_ROOT / item["asset"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    audio_target = PUBLIC_ROOT / "audio" / "narration.wav"
    audio_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run / "narration.wav", audio_target)


def audio_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def normalize_storyboard_cache(payload: object) -> dict | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("shots"), list):
        return None
    rows = []
    for item in payload["shots"]:
        if "background_summary" in item and "elements" in item:
            rows.append(item)
            continue
        background = item.get("background", {})
        elements = item.get("elements", [])
        if not isinstance(background, dict) or not isinstance(elements, list) or not elements:
            return None
        rows.append({
            "shot_id": item.get("shot_id"),
            "background_summary": background.get("summary", ""),
            "elements": [{"element_id": element.get("element_id"), "content": element.get("content", ""), "role": "single_composite"} for element in elements],
            "element_count": 1,
            "asset_count": 1,
        })
    return {"style_id": "jianying-mg-whiteboard-v1", "density_policy": "one-composite-illustration-per-scene", "shots": rows}


def build_project(topic: str, screenplay_path: Path | None, reuse_assets: bool) -> Path:
    values = load_env()
    supplied_screenplay = create_screenplay(topic, values, screenplay_path) if screenplay_path else None
    if supplied_screenplay is not None:
        screenplay = supplied_screenplay
        copywriting = {
            "title": screenplay.get("title", topic),
            "wenan": "\n".join([str(screenplay.get("voice", "")).strip(), *(str(shot.get("voice", "")).strip() for shot in screenplay.get("shots", []))]).strip(),
            "source": "supplied-screenplay-compatibility-input",
        }
    else:
        copywriting = create_copywriting(topic, values)
        tts_project = {"title": copywriting["title"], "voice": copywriting["wenan"], "shots": []}
        screenplay = None
    run = RUNS_ROOT / slug(topic)
    run.mkdir(parents=True, exist_ok=True)
    write_json(run / "copywriting.json", copywriting)

    narration_path = run / "narration.wav"
    if reuse_assets and narration_path.is_file():
        narration_duration = audio_duration(narration_path)
    elif supplied_screenplay is not None:
        narration_duration = synthesize_narration(supplied_screenplay, narration_path, values)
    else:
        narration_duration = synthesize_narration(tts_project, narration_path, values)
    voice_timeline = build_voice_timeline(copywriting, narration_duration)
    if screenplay is None:
        screenplay = create_shot_timeline(copywriting, voice_timeline, values)
    write_json(run / "script.json", screenplay)
    facts = build_scene_facts(screenplay, narration_duration)
    storyboard_path = run / "storyboard.json"
    cached_storyboard = normalize_storyboard_cache(json.loads(storyboard_path.read_text(encoding="utf-8"))) if reuse_assets and storyboard_path.is_file() else None
    cached_rows = (cached_storyboard or {}).get("shots", []) if isinstance(cached_storyboard, dict) else []
    can_reuse_storyboard = (
        isinstance(cached_storyboard, dict)
        and cached_storyboard.get("density_policy") == "one-composite-illustration-per-scene"
        and len(cached_rows) == len(facts["shots"])
        and all("background_summary" in row and "elements" in row for row in cached_rows)
    )
    storyboard = cached_storyboard if can_reuse_storyboard else build_storyboard(facts, values)
    validate_storyboard(storyboard, [shot["id"] for shot in facts["shots"]])
    visual_plan = direct_scenes(facts, storyboard)
    layout = layout_world(facts)
    planned_shots = visual_plan_shots(facts, visual_plan)
    storyboard_by_id = {item["shot_id"]: item for item in storyboard["shots"]}
    for shot in planned_shots:
        shot["storyboard_elements"] = [item["content"] for item in storyboard_by_id[shot["id"]]["elements"]]
        shot["background_summary"] = storyboard_by_id[shot["id"]]["background_summary"]
    media = prepare_media(planned_shots, run, values, reuse=reuse_assets)
    manifest = make_manifest(facts, visual_plan, layout, media, "audio/narration.wav")

    write_json(run / "scene_facts.json", facts)
    write_json(run / "storyboard.json", storyboard)
    write_json(run / "voice_timeline.json", voice_timeline)
    write_json(run / "shot_timeline.json", {
        "shots": [{"id": shot["id"], "title": shot["title"], "start": shot["start"], "end": shot["end"], "sourceText": shot["voice"]} for shot in facts["shots"]],
        "source": "semantic-scene-facts",
    })
    write_json(run / "visual_plan.json", visual_plan)
    write_json(run / "layout.json", layout)
    write_json(run / "density_audit.json", audit_density(screenplay, facts, media, storyboard))
    write_json(run / "manifest.json", manifest)
    publish_assets(run, media)
    write_json(PUBLIC_ROOT / "manifest.json", manifest)
    print(f"run={run}")
    print(f"duration={narration_duration:.2f}s shots={len(facts['shots'])}")
    print(f"manifest={PUBLIC_ROOT / 'manifest.json'}")
    return run


def visual_plan_shots(facts: dict, visual_plan: dict) -> list[dict]:
    decisions = {item["shot_id"]: item for item in visual_plan["shots"]}
    return [{**shot, **decisions[shot["id"]]} for shot in facts["shots"]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a physically isolated Remotion video project")
    parser.add_argument("--topic", default="什么是爬虫程序")
    parser.add_argument("--script", type=Path, help="Use an explicitly supplied screenplay JSON")
    parser.add_argument("--reuse-assets", action="store_true", help="Reuse only media under this topic's run directory")
    args = parser.parse_args()
    screenplay = args.script.expanduser().resolve() if args.script else None
    build_project(args.topic, screenplay, args.reuse_assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
