"""Attach coordinate-free visual directives to calculated elements."""

from __future__ import annotations

import random
from dataclasses import replace

from ..core.models import LayoutResult
from ..settings import DEFAULT_KEYWORD_FONT, KEYWORD_TEXT_COLORS
from .models import VisualPlan
from .presets import (
    BANNED_MOTION_EFFECTS,
    EFFECT_PROFILES,
    EMPHASIS_TEXT_LOOPS,
    SCENE_TRANSITION_INTROS,
)
from .sound_design import sound_cue_for, sound_priority_for


def apply_visual_plan(
    result: LayoutResult,
    plan: VisualPlan,
    *,
    previous_keyword_color: str = "",
) -> LayoutResult:
    profile_name = plan.motion.intensity if plan.motion.intensity in EFFECT_PROFILES else "soft"
    profile = EFFECT_PROFILES[profile_name]
    support_profile = EFFECT_PROFILES["soft" if profile_name == "story" else "flow"]
    text_count = sum(element.element_type == "text" and element.role != "subtitle" for element in result.elements)
    overlay_image_count = sum(
        element.element_type == "image"
        and element.role != "background"
        and element.metadata.get("stack_role") != "background"
        for element in result.elements
    )
    keyword_count = sum(
        element.element_type == "text" and element.role in {"label", "number"}
        for element in result.elements
    )
    title_intros = tiered_choices(profile_name, profile, support_profile, "title_intros", text_count, f"{plan.scene_id}:title-in")
    label_intros = tiered_choices(profile_name, profile, support_profile, "label_intros", text_count, f"{plan.scene_id}:label-in")
    loop_candidates = [
        element
        for element in result.elements
        if element.element_type == "text"
        and element.role == "title"
        and element.end_ms - element.start_ms >= 1200
    ]
    emphasis_element = next(
        (element for element in loop_candidates),
        None,
    )
    emphasis_loop = distributed_choices(
        EMPHASIS_TEXT_LOOPS,
        1 if emphasis_element is not None else 0,
        f"{plan.scene_id}:text-loop",
        randomize=True,
    )
    video_intros = tiered_choices(
        profile_name, profile, support_profile, "video_intros", overlay_image_count, f"{plan.scene_id}:video-in"
    )
    video_outros = tiered_choices(
        profile_name, profile, support_profile, "video_outros", overlay_image_count, f"{plan.scene_id}:video-out"
    )
    video_outros = avoid_matching_pairs(video_intros, video_outros, support_profile["video_outros"])
    keyword_colors = distributed_keyword_text_colors(
        keyword_count,
        f"{plan.scene_id}:keyword-text-color",
        avoid=previous_keyword_color,
    )
    elements = []
    text_index = 0
    keyword_index = 0
    image_index = 0
    background_index = 0
    for element in result.elements:
        metadata = dict(element.metadata)
        metadata["visual_plan"] = plan.scene_id
        if element.element_type == "text":
            metadata["font_name"] = font_for_role(element.role, plan)
            metadata.setdefault("text_color", color_for_role(element.role, plan))
            if element.role in {"label", "number"}:
                metadata["font_name"] = DEFAULT_KEYWORD_FONT
                metadata["text_color"] = keyword_colors[keyword_index]
                keyword_index += 1
                metadata.pop("keyword_color_role", None)
                metadata.pop("keyword_background_color", None)
            if element.role == "subtitle":
                metadata["text_intro"] = plan.motion.subtitle_enter
                metadata["text_outro"] = "渐隐"
            else:
                metadata["text_intro"] = (
                    title_intros[text_index] if element.role == "title" else label_intros[text_index]
                )
                metadata.pop("text_outro", None)
                if element.role in {"label", "number"}:
                    metadata.pop("text_loop", None)
                    metadata.pop("hollow_outline", None)
                elif emphasis_element is not None and element.element_id == emphasis_element.element_id:
                    metadata["text_loop"] = emphasis_loop[0]
                    metadata.pop("hollow_outline", None)
                else:
                    metadata.pop("text_loop", None)
                    metadata.pop("hollow_outline", None)
                text_index += 1
        else:
            is_background = element.role == "background" or metadata.get("stack_role") == "background"
            if is_background:
                metadata["video_intro"] = distributed_choices(
                    SCENE_TRANSITION_INTROS,
                    background_index + 1,
                    f"{plan.scene_id}:scene-transition",
                    randomize=True,
                )[background_index]
                metadata.pop("video_outro", None)
                metadata.pop("video_effect", None)
                metadata["hold_motion"] = "static"
                metadata["scene_transition"] = "background_intro"
                background_index += 1
            else:
                metadata["video_intro"] = video_intros[image_index]
                metadata["video_outro"] = video_outros[image_index]
                metadata.pop("video_effect", None)
                metadata["hold_motion"] = plan.motion.hold_motion
                image_index += 1
        sound_cue = sound_cue_for(element, metadata)
        if sound_cue:
            metadata["sound_cue"] = sound_cue
            metadata["sound_priority"] = sound_priority_for(element)
        elements.append(replace(element, metadata=metadata))
    decisions = list(result.decisions)
    decisions.append(
        f"视觉导演：{plan.layout.family}/{plan.layout.variant}，"
        f"字体={plan.typography.preset}，动效={plan.motion.intensity}"
    )
    return replace(result, elements=elements, decisions=decisions)


def distributed_keyword_text_colors(count: int, seed: str, *, avoid: str = "") -> list[str]:
    colors = distributed_choices(KEYWORD_TEXT_COLORS, count, seed, randomize=False)
    if colors and colors[0] == avoid and len(KEYWORD_TEXT_COLORS) > 1:
        replacement = next(color for color in KEYWORD_TEXT_COLORS if color != avoid)
        try:
            replacement_index = colors.index(replacement, 1)
        except ValueError:
            colors[0] = replacement
        else:
            colors[0], colors[replacement_index] = colors[replacement_index], colors[0]
    return colors


def distributed_choices(
    options: tuple[str, ...], count: int, seed: str, *, randomize: bool = True
) -> list[str]:
    if count <= 0:
        return []
    available = tuple(option for option in options if option not in BANNED_MOTION_EFFECTS)
    if not available:
        return [""] * count
    if randomize:
        rng = random.SystemRandom()
    else:
        # Keep the public helper reproducible for callers that use it as a
        # planning primitive; production visual plans opt into fresh draws.
        rng = random.Random(seed)
    selected: list[str] = []
    while len(selected) < count:
        batch = list(available)
        rng.shuffle(batch)
        if selected and batch[0] == selected[-1] and len(batch) > 1:
            batch[0], batch[1] = batch[1], batch[0]
        selected.extend(batch)
    return selected[:count]


def tiered_choices(
    profile_name: str,
    profile: dict[str, tuple[str, ...]],
    support_profile: dict[str, tuple[str, ...]],
    key: str,
    count: int,
    seed: str,
) -> list[str]:
    if profile_name not in {"story", "focus"} or count <= 1:
        return distributed_choices(profile[key], count, seed, randomize=True)
    return (
        distributed_choices(profile[key], 1, f"{seed}:accent", randomize=True)
        + distributed_choices(support_profile[key], count - 1, f"{seed}:support", randomize=True)
    )


def avoid_matching_pairs(intros: list[str], outros: list[str], alternatives: tuple[str, ...]) -> list[str]:
    if len(alternatives) <= 1:
        return outros
    adjusted = list(outros)
    for index, (intro, outro) in enumerate(zip(intros, adjusted)):
        if intro != outro:
            continue
        replacement_index = (alternatives.index(outro) + 1) % len(alternatives) if outro in alternatives else 0
        adjusted[index] = alternatives[replacement_index]
    return adjusted


def font_for_role(role: str, plan: VisualPlan) -> str:
    if role in {"title", "board_major_title"}:
        return plan.typography.title_font
    if role in {"label", "board_major_point", "board_subpoint"}:
        return plan.typography.label_font
    if role == "number":
        return plan.typography.number_font
    return "未光体"


def color_for_role(role: str, plan: VisualPlan) -> str:
    if role in {"board_major_title", "board_major_point", "board_subpoint"}:
        return "#111111"
    if role == "title":
        return plan.typography.title_color
    if role == "label":
        return plan.typography.label_color
    if role == "number":
        return plan.typography.number_color
    return "#FFFFFF"
