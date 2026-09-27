from __future__ import annotations

from typing import Any


def audit_density(screenplay: dict[str, Any], facts: dict[str, Any], media: dict[str, dict[str, str]], storyboard: dict[str, Any] | None = None) -> dict[str, Any]:
    """Report density ownership; never remove content during rendering."""
    shot_count = len(facts.get("shots", []))
    media_count = len(media)
    average_scene_seconds = float(facts.get("durationSeconds", 0)) / shot_count if shot_count else 0
    assets_per_shot = media_count / shot_count if shot_count else 0
    storyboard_rows = (storyboard or {}).get("shots", [])
    storyboard_counts = [int(shot.get("asset_count", 1)) for shot in storyboard_rows]
    average_elements = sum(storyboard_counts) / len(storyboard_counts) if storyboard_counts else 0
    if average_elements > 1:
        source_layer, reason = "prepare.storyboard", "the storyboard assigns multiple foreground visuals to a scene"
    elif assets_per_shot > 1:
        source_layer, reason = "prepare.media", "a scene owns multiple visual assets"
    elif shot_count > 8 or average_scene_seconds < 4:
        source_layer, reason = "prepare.script", "narrative scenes are too numerous or too short"
    else:
        source_layer, reason = "none", "one asset per scene at a readable duration"
    return {
        "shotCount": shot_count,
        "mediaCount": media_count,
        "assetsPerShot": round(assets_per_shot, 3),
        "averageSceneSeconds": round(average_scene_seconds, 3),
        "averageStoryboardElements": round(average_elements, 3),
        "referenceSourceLayer": "prepare.storyboard",
        "referenceCause": "Jianying storyboard rules require at least 2 foreground images plus a background per scene",
        "remotionPolicy": "one sparse composite illustration per semantic scene; canvas chrome and text are renderer layers",
        "sourceLayer": source_layer,
        "reason": reason,
        "policy": "audit-only; density changes happen before manifest generation",
        "scriptTitle": screenplay.get("title", ""),
    }
