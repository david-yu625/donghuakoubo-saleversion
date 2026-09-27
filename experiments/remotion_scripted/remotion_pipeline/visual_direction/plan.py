from __future__ import annotations

from typing import Any

from ..contracts import VISUAL_STYLE_ID, validate_scene_facts, validate_visual_plan


PALETTES = ["#19766b", "#3769a5", "#b06a35", "#7860a6", "#b34d62", "#4d8060"]
TRANSITIONS = ["glide", "drift", "push", "pull", "wipe_left", "wipe_up", "iris", "arc"]
IMAGE_ANIMATIONS = ["rise", "slide_left", "slide_right", "scale", "wipe", "unfold", "tilt", "flip"]
CAMERA_MOVES = ["pan", "arc", "crane", "dolly", "overview"]
TRANSITION_FRAMES = {"glide": 16, "drift": 16, "push": 18, "pull": 18, "wipe_left": 14, "wipe_up": 14, "iris": 18, "arc": 18}
IMAGE_FRAMES = {"rise": 28, "slide_left": 28, "slide_right": 28, "scale": 30, "wipe": 26, "unfold": 28, "tilt": 30, "flip": 30}
# Camera moves should read as a decisive move between semantic beats. The
# image remains on screen for the rest of the shot, so long camera windows
# only make the cut feel sluggish.
CAMERA_FRAMES = {"pan": 30, "arc": 32, "crane": 34, "dolly": 36, "overview": 38}


def direct_scenes(facts: dict[str, Any], storyboard: dict[str, Any] | None = None) -> dict[str, Any]:
    """Choose visual emphasis and camera intent without assigning coordinates."""
    validate_scene_facts(facts)
    shots = facts["shots"]
    storyboard_by_id = {item["shot_id"]: item for item in (storyboard or {}).get("shots", [])}
    decisions = []
    for index, shot in enumerate(shots):
        storyboard_shot = storyboard_by_id.get(shot["id"], {})
        elements = storyboard_shot.get("elements", [])
        visual = elements[0].get("content", "") if elements else shot.get("visual", "")
        beat_frames = max(1, round((float(shot["end"]) - float(shot["start"])) * 30))
        transition = TRANSITIONS[(index - 1) % len(TRANSITIONS)]
        image_animation = IMAGE_ANIMATIONS[index % len(IMAGE_ANIMATIONS)]
        camera_move = "establish" if index == 0 else ("resolve" if index == len(shots) - 1 else "travel")
        camera_effect = CAMERA_MOVES[index % len(CAMERA_MOVES)]
        voice = str(shot.get("voice", ""))
        keyword = str(shot.get("keyword", ""))
        keyword_index = voice.find(keyword) if keyword else -1
        keyword_ratio = (keyword_index / max(1, len(voice))) if keyword_index >= 0 else 0.30
        keyword_ratio = max(0.16, min(0.62, keyword_ratio))
        decisions.append({
            "shot_id": shot["id"],
            "focal_intent": visual or "narration_subject",
            "camera_move": camera_move,
            "camera_effect": camera_effect,
            "transition": transition,
            "transition_frames": min(TRANSITION_FRAMES[transition], max(1, beat_frames - 2)),
            "image_animation": image_animation,
            "image_animation_frames": min(IMAGE_FRAMES[image_animation], max(1, beat_frames - 2)),
            "camera_frames": min(CAMERA_FRAMES[camera_effect], max(1, beat_frames)),
            "keyword_cue": "voice-led-emphasis",
            "keyword_delay_ratio": round(keyword_ratio, 3),
            "accent": PALETTES[index % len(PALETTES)],
            "style_id": VISUAL_STYLE_ID,
            "storyboard_element_count": int(storyboard_shot.get("element_count", 1)),
        })
    return validate_visual_plan({"shots": decisions}, [shot["id"] for shot in shots])
