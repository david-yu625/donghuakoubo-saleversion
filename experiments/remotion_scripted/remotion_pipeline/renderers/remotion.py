from __future__ import annotations

from typing import Any

from ..contracts import CONTRACT_VERSION, VISUAL_STYLE_ID, validate_layout, validate_manifest, validate_scene_facts, validate_visual_plan


def make_manifest(
    facts: dict[str, Any],
    visual_plan: dict[str, Any],
    layout: dict[str, Any],
    media: dict[str, dict[str, str]],
    audio_path: str,
) -> dict[str, Any]:
    validate_scene_facts(facts)
    validate_visual_plan(visual_plan, [shot["id"] for shot in facts["shots"]])
    validate_layout(layout, [shot["id"] for shot in facts["shots"]])
    direction = {item["shot_id"]: item for item in visual_plan["shots"]}
    positions = {item["shot_id"]: item for item in layout["shots"]}
    shots = []
    for fact in facts["shots"]:
        shot_id = fact["id"]
        if shot_id not in direction or shot_id not in positions or shot_id not in media:
            raise ValueError(f"Remotion input incomplete for shot {shot_id}")
        shots.append({
            **fact,
            **positions[shot_id],
            **direction[shot_id],
            **media[shot_id],
        })
    return validate_manifest({
        "contractVersion": CONTRACT_VERSION,
        "visualStyle": VISUAL_STYLE_ID,
        "infiniteCanvas": True,
        "title": facts["title"],
        "durationSeconds": facts["durationSeconds"],
        "audio": audio_path,
        "shots": shots,
        "captions": facts["captions"],
        "viewport": layout["viewport"],
        "world": layout["world"],
        "subtitleSafeArea": layout["subtitle_safe_area"],
    })
