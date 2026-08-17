"""Stateful scene director for layout, typography, and motion choices."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..core.models import SceneFacts
from .models import LayoutChoice, VisualPlan
from .presets import BOARD_MOTION_PRESET, MOTION_PRESETS, TYPOGRAPHY_PRESETS


SINGLE_IMAGE_LAYOUTS = (
    LayoutChoice("single_image", "title_above", "title_image"),
    LayoutChoice("single_image", "side_caption", "single_side"),
    LayoutChoice("single_image", "full_focus", "single_focus"),
)
MULTI_IMAGE_LAYOUTS = (
    LayoutChoice("multi_image", "focus_history", "focus_history"),
    LayoutChoice("multi_image", "clean_grid", "multi_grid"),
    LayoutChoice("multi_image", "card_stack", "multi_stack"),
)
TEXT_LAYOUTS = (
    LayoutChoice("text", "center_quote", "quote"),
)
COMPARE_LAYOUTS = (
    LayoutChoice("comparison", "split_columns", "split_compare"),
)
TIMELINE_LAYOUTS = (
    LayoutChoice("sequence", "timeline_flow", "timeline_flow"),
)
BACKGROUND_STACK_LAYOUT = LayoutChoice("composite_image", "background_stack", "background_stack")
BOARD_OVERVIEW_LAYOUT = LayoutChoice("board", "overview", "board_overview")
BOARD_SECTION_LAYOUT = LayoutChoice("board", "numbered_section", "board_section")
PROCESS_LAYOUTS = (
    LayoutChoice("process", "timeline_flow", "timeline_flow"),
)
RISK_LAYOUTS = (
    LayoutChoice("risk", "timeline_flow", "timeline_flow"),
)


@dataclass
class DirectorState:
    recent_templates: list[str] = field(default_factory=list)


class VisualDirector:
    def __init__(self) -> None:
        self.state = DirectorState()

    def plan(self, facts: SceneFacts) -> VisualPlan:
        candidates = self._layout_candidates(facts)
        layout = self._without_immediate_repeat(candidates)
        motion = (
            BOARD_MOTION_PRESET
            if facts.semantic_role == "board_progressive"
            else replace(
                MOTION_PRESETS[facts.scene_index % len(MOTION_PRESETS)],
                hold_motion=hold_motion_for_semantics(facts.semantic_role, facts.scene_index),
            )
        )
        self.state.recent_templates.append(layout.template)
        self.state.recent_templates = self.state.recent_templates[-4:]
        return VisualPlan(
            scene_id=facts.scene_id,
            layout=layout,
            typography=TYPOGRAPHY_PRESETS[facts.scene_index % len(TYPOGRAPHY_PRESETS)],
            motion=motion,
            enter_order=("title", "main", "support", "subtitle"),
        )

    def _layout_candidates(self, facts: SceneFacts) -> tuple[LayoutChoice, ...]:
        if facts.semantic_role == "board_progressive" and facts.background_image is not None:
            return (BACKGROUND_STACK_LAYOUT,)
        if facts.semantic_role == "overview" and facts.background_image is not None:
            return (BOARD_OVERVIEW_LAYOUT,)
        if facts.semantic_role == "board_section" and facts.background_image is not None:
            return (BOARD_SECTION_LAYOUT,)
        if facts.background_image is not None and facts.overlay_images:
            return (BACKGROUND_STACK_LAYOUT,)
        if not facts.images:
            return TEXT_LAYOUTS
        if facts.semantic_role == "compare" and len(facts.images) >= 2:
            return COMPARE_LAYOUTS
        if facts.semantic_role == "process":
            return PROCESS_LAYOUTS
        if facts.semantic_role == "risk":
            return RISK_LAYOUTS
        if facts.semantic_role == "sequence":
            return TIMELINE_LAYOUTS
        if len(facts.images) >= 2:
            return rotate(MULTI_IMAGE_LAYOUTS, facts.scene_index)
        return rotate(SINGLE_IMAGE_LAYOUTS, facts.scene_index)

    def _without_immediate_repeat(self, candidates: tuple[LayoutChoice, ...]) -> LayoutChoice:
        previous = self.state.recent_templates[-1] if self.state.recent_templates else ""
        for candidate in candidates:
            if candidate.template != previous:
                return candidate
        return candidates[0]


def rotate(values: tuple[LayoutChoice, ...], offset: int) -> tuple[LayoutChoice, ...]:
    index = offset % len(values)
    return values[index:] + values[:index]


def hold_motion_for_semantics(semantic_role: str, scene_index: int) -> str:
    role_motion = {
        "board_progressive": "static",
        "overview": "push_in",
        "board_section": "drift",
        "risk": "push_in",
        "process": "pan",
        "sequence": "pan",
        "compare": "drift",
    }
    return role_motion.get(semantic_role, ("drift", "push_in", "pull_out")[scene_index % 3])
