"""Template selection and layout execution."""

from __future__ import annotations

from dataclasses import replace

from ..core.models import Canvas, LayoutResult, SceneContent, Theme
from .templates import (
    BackgroundStackLayout,
    BoardOverviewLayout,
    BoardSectionLayout,
    FocusHistoryLayout,
    MultiGridLayout,
    MultiStackLayout,
    QuoteLayout,
    SingleFocusLayout,
    SingleSideLayout,
    SplitCompareLayout,
    TimelineFlowLayout,
    TitleImageLayout,
)


class LayoutEngine:
    def __init__(self, *, canvas: Canvas | None = None, theme: Theme | None = None):
        self.canvas = canvas or Canvas()
        self.theme = theme or Theme()
        self.templates = {
            "board_overview": BoardOverviewLayout(),
            "board_section": BoardSectionLayout(),
            "background_stack": BackgroundStackLayout(),
            "title_image": TitleImageLayout(),
            "single_side": SingleSideLayout(),
            "single_focus": SingleFocusLayout(),
            "focus_history": FocusHistoryLayout(),
            "multi_grid": MultiGridLayout(),
            "multi_stack": MultiStackLayout(),
            "split_compare": SplitCompareLayout(),
            "timeline_flow": TimelineFlowLayout(),
            "quote": QuoteLayout(),
        }

    def build(self, template: str, content: SceneContent | dict) -> LayoutResult:
        if template not in self.templates:
            available = ", ".join(sorted(self.templates))
            raise ValueError(f"未知布局模板 {template!r}，可用模板：{available}")
        scene = content if isinstance(content, SceneContent) else SceneContent.from_dict(content)
        scene = stabilize_keyword_visibility(scene)
        return self.templates[template].build(scene, self.canvas, self.theme)

    def choose(self, content: SceneContent | dict) -> str:
        scene = content if isinstance(content, SceneContent) else SceneContent.from_dict(content)
        if scene.semantic_role == "board_progressive" or (
            scene.background_element is not None and scene.overlay_image_elements
        ):
            return "background_stack"
        if scene.semantic_role == "overview":
            return "board_overview"
        if scene.semantic_role == "board_section":
            return "board_section"
        if scene.semantic_role == "compare":
            return "split_compare"
        if scene.semantic_role in {"sequence", "process", "risk"}:
            return "timeline_flow"
        if len(scene.images) >= 2:
            return "focus_history"
        return "title_image"

    def auto_build(self, content: SceneContent | dict) -> LayoutResult:
        return self.build(self.choose(content), content)


def stabilize_keyword_visibility(scene: SceneContent) -> SceneContent:
    if not scene.elements:
        return scene
    images = scene.image_elements
    elements = []
    for element in scene.elements:
        if element.element_type != "text":
            elements.append(element)
            continue
        candidates = []
        for image in images:
            overlap = min(element.end_ms, image.end_ms) - max(element.start_ms, image.start_ms)
            if overlap > 0:
                candidates.append((overlap, -abs(element.start_ms - image.start_ms), image))
        target = max(candidates, default=None, key=lambda item: (item[0], item[1]))
        elements.append(
            replace(element, end_ms=max(element.end_ms, target[2].end_ms))
            if target is not None
            else element
        )
    return replace(scene, elements=tuple(elements))
