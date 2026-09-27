"""Stable contracts between the isolated Remotion production stages.

The Jianying workflow is the reference for responsibilities and visual style,
but this package deliberately owns its own data files and validation.  A stage
may only add fields promised by its output contract; presentation geometry is
kept out of semantic stages until the layout stage.
"""

from __future__ import annotations

from typing import Any, Iterable


CONTRACT_VERSION = "remotion-scripted-v1"
VISUAL_STYLE_ID = "jianying-mg-whiteboard-v1"
MEDIA_TYPES = {"image", "video"}
CAMERA_MOVES = {"establish", "travel", "resolve"}
CAMERA_EFFECTS = {"pan", "arc", "crane", "dolly", "overview"}
TRANSITIONS = {"glide", "drift", "push", "pull", "wipe_left", "wipe_up", "iris", "arc"}
IMAGE_ANIMATIONS = {"rise", "slide_left", "slide_right", "scale", "wipe", "unfold", "tilt", "flip"}
GEOMETRY_KEYS = {"x", "y", "width", "height", "zoom", "left", "top"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _keys(items: Iterable[dict[str, Any]]) -> set[str]:
    return {key for item in items for key in item}


def validate_screenplay(project: dict[str, Any]) -> dict[str, Any]:
    shots = project.get("shots")
    _require(isinstance(project.get("title"), str) and project["title"].strip(), "screenplay.title is required")
    _require(isinstance(shots, list) and 4 <= len(shots) <= 10, "screenplay.shots must contain 4 to 10 shots")
    ids: set[str] = set()
    for index, shot in enumerate(shots):
        _require(isinstance(shot, dict), f"screenplay.shots[{index}] must be an object")
        for field in ("id", "title", "voice", "keyword"):
            _require(str(shot.get(field, "")).strip(), f"screenplay.shots[{index}].{field} is required")
        shot_id = str(shot["id"])
        _require(shot_id not in ids, f"duplicate shot id: {shot_id}")
        ids.add(shot_id)
        _require(not (_keys([shot]) & GEOMETRY_KEYS), f"screenplay shot {shot_id} contains layout geometry")
        asset_type = str(shot.get("asset_type", "image"))
        _require(asset_type in MEDIA_TYPES, f"unsupported asset_type for {shot_id}: {asset_type}")
        if asset_type == "video":
            _require(str(shot.get("source", "")).strip(), f"video shot {shot_id} requires source")
    return project


def validate_scene_facts(facts: dict[str, Any]) -> dict[str, Any]:
    shots = facts.get("shots")
    _require(isinstance(shots, list) and shots, "scene_facts.shots must not be empty")
    duration = float(facts.get("durationSeconds", 0))
    _require(duration > 0, "scene_facts.durationSeconds must be positive")
    previous_end = 0.0
    ids: set[str] = set()
    for shot in shots:
        shot_id = str(shot.get("id", ""))
        _require(shot_id and shot_id not in ids, f"invalid or duplicate scene id: {shot_id}")
        ids.add(shot_id)
        start, end = float(shot.get("start", -1)), float(shot.get("end", -1))
        _require(0 <= start < end <= duration + 0.05, f"invalid timing for scene {shot_id}")
        _require(start >= previous_end - 0.05, f"scene timings overlap at {shot_id}")
        _require(not (_keys([shot]) & GEOMETRY_KEYS), f"scene facts {shot_id} contain layout geometry")
        previous_end = end
    _require(isinstance(facts.get("captions"), list), "scene_facts.captions must be a list")
    return facts


def validate_visual_plan(plan: dict[str, Any], shot_ids: Iterable[str]) -> dict[str, Any]:
    decisions = plan.get("shots")
    expected = list(shot_ids)
    _require(isinstance(decisions, list) and len(decisions) == len(expected), "visual_plan must cover every scene")
    actual = []
    for decision in decisions:
        shot_id = str(decision.get("shot_id", ""))
        _require(shot_id in expected and shot_id not in actual, f"visual_plan has invalid scene id: {shot_id}")
        _require(decision.get("camera_move") in CAMERA_MOVES, f"invalid camera move for {shot_id}")
        _require(decision.get("camera_effect") in CAMERA_EFFECTS, f"invalid camera effect for {shot_id}")
        _require(decision.get("transition") in TRANSITIONS, f"invalid transition for {shot_id}")
        _require(decision.get("image_animation") in IMAGE_ANIMATIONS, f"invalid image animation for {shot_id}")
        for field in ("transition_frames", "image_animation_frames", "camera_frames"):
            _require(int(decision.get(field, 0)) > 0, f"{field} must be positive for {shot_id}")
        _require(decision.get("style_id") == VISUAL_STYLE_ID, f"visual style mismatch for {shot_id}")
        _require(not (_keys([decision]) & GEOMETRY_KEYS), f"visual plan {shot_id} contains layout geometry")
        actual.append(shot_id)
    _require(actual == expected, "visual_plan scene order must match scene_facts")
    return plan


def validate_storyboard(storyboard: dict[str, Any], shot_ids: Iterable[str]) -> dict[str, Any]:
    expected = list(shot_ids)
    rows = storyboard.get("shots")
    _require(storyboard.get("style_id") == VISUAL_STYLE_ID, "storyboard visual style mismatch")
    _require(storyboard.get("density_policy") == "one-composite-illustration-per-scene", "storyboard density policy mismatch")
    _require(isinstance(rows, list) and [str(row.get("shot_id", "")) for row in rows] == expected, "storyboard scene order mismatch")
    for row in rows:
        _require(int(row.get("asset_count", 0)) == 1 and len(row.get("elements", [])) == 1, f"storyboard must be sparse for {row.get('shot_id')}")
    return storyboard


def validate_layout(layout: dict[str, Any], shot_ids: Iterable[str]) -> dict[str, Any]:
    canvas, world, placements = layout.get("canvas"), layout.get("world"), layout.get("shots")
    _require(isinstance(canvas, dict) and isinstance(world, dict), "layout requires canvas and world")
    _require(isinstance(placements, list) and len(placements) == len(list(shot_ids)), "layout must cover every scene")
    _require(float(world.get("width", 0)) > float(canvas.get("width", 0)), "infinite world must exceed viewport width")
    _require(float(world.get("height", 0)) > float(canvas.get("height", 0)), "infinite world must exceed viewport height")
    for placement in placements:
        _require(float(placement.get("width", 0)) > 0 and float(placement.get("height", 0)) > 0, "layout placement size must be positive")
        _require("x" in placement and "y" in placement, "layout placement requires world coordinates")
    return layout


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _require(manifest.get("contractVersion") == CONTRACT_VERSION, "manifest contract version mismatch")
    _require(manifest.get("visualStyle") == VISUAL_STYLE_ID, "manifest visual style mismatch")
    _require(manifest.get("infiniteCanvas") is True, "manifest must enable infiniteCanvas")
    shots = manifest.get("shots")
    _require(isinstance(shots, list) and shots, "manifest.shots must not be empty")
    for shot in shots:
        _require(shot.get("mediaType") in MEDIA_TYPES, f"manifest media type invalid for {shot.get('id')}")
        _require(str(shot.get("asset", "")) and not str(shot["asset"]).startswith(("/", "\\")), "manifest asset path must be relative")
        _require(shot.get("styleId") == VISUAL_STYLE_ID, f"manifest media style mismatch for {shot.get('id')}")
        _require(shot.get("camera_effect") in CAMERA_EFFECTS, f"manifest camera effect invalid for {shot.get('id')}")
        _require(shot.get("transition") in TRANSITIONS, f"manifest transition invalid for {shot.get('id')}")
        _require(shot.get("image_animation") in IMAGE_ANIMATIONS, f"manifest image animation invalid for {shot.get('id')}")
        for field in ("transition_frames", "image_animation_frames", "camera_frames"):
            _require(int(shot.get(field, 0)) > 0, f"manifest {field} must be positive for {shot.get('id')}")
    return manifest
