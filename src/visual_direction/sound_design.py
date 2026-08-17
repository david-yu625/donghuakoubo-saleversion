"""Coordinate-free sound cues and density control for animated elements."""

from __future__ import annotations

from dataclasses import replace

from ..core.models import ElementLayout, LayoutResult


SOUND_GROUP_TOLERANCE_MS = 180
SOUND_MIN_GAP_MS = 950
SOUND_WINDOW_MS = 4000
SOUND_MAX_PER_WINDOW = 2

ROLE_PRIORITY = {
    "number": 50,
    "label": 40,
    "image": 30,
    "title": 20,
}


def sound_cue_for(element: ElementLayout, metadata: dict[str, object]) -> str:
    if element.role == "subtitle":
        return ""

    if element.element_type == "image":
        intro = str(metadata.get("video_intro", ""))
        if any(token in intro for token in ("滑动", "雨刷", "斜切")):
            return "swish"
        if any(token in intro for token in ("翻", "旋转", "折叠")):
            return "reveal"
        return "pop"

    if element.role not in {"title", "label", "number"}:
        return ""
    intro = str(metadata.get("text_intro", ""))
    if any(token in intro for token in ("露出", "擦开")):
        return "swish"
    if any(token in intro for token in ("显影", "打字")):
        return "chime"
    return "pop"


def sound_priority_for(element: ElementLayout) -> int:
    if element.element_type == "image":
        return ROLE_PRIORITY["image"]
    return ROLE_PRIORITY.get(element.role, 0)


def apply_sound_design(result: LayoutResult) -> LayoutResult:
    elements = [replace(element, metadata=_without_selected_sound(element.metadata)) for element in result.elements]
    candidates = [element for element in elements if element.metadata.get("sound_cue")]
    grouped = _group_nearby_candidates(candidates)

    selected: list[ElementLayout] = []
    selected_starts: list[int] = []
    for group in grouped:
        candidate = max(
            group,
            key=lambda element: (
                int(element.metadata.get("sound_priority", 0)),
                -element.start_ms,
                element.element_id,
            ),
        )
        if selected_starts and candidate.start_ms - selected_starts[-1] < SOUND_MIN_GAP_MS:
            continue
        recent = [start for start in selected_starts if candidate.start_ms - start < SOUND_WINDOW_MS]
        if len(recent) >= SOUND_MAX_PER_WINDOW:
            continue
        selected.append(candidate)
        selected_starts.append(candidate.start_ms)

    selected_ids = {element.element_id for element in selected}
    designed = []
    for element in elements:
        metadata = dict(element.metadata)
        if element.element_id in selected_ids:
            metadata["sound_effect"] = metadata["sound_cue"]
        designed.append(replace(element, metadata=metadata))

    decisions = list(result.decisions)
    decisions.append(f"音效设计：{len(candidates)} 个候选，节流后保留 {len(selected)} 个入场音效")
    return replace(result, elements=designed, decisions=decisions)


def _without_selected_sound(metadata: dict[str, object]) -> dict[str, object]:
    cleaned = dict(metadata)
    cleaned.pop("sound_effect", None)
    return cleaned


def _group_nearby_candidates(candidates: list[ElementLayout]) -> list[list[ElementLayout]]:
    ordered = sorted(candidates, key=lambda element: (element.start_ms, element.element_id))
    groups: list[list[ElementLayout]] = []
    for candidate in ordered:
        if not groups or candidate.start_ms - groups[-1][0].start_ms > SOUND_GROUP_TOLERANCE_MS:
            groups.append([candidate])
        else:
            groups[-1].append(candidate)
    return groups
