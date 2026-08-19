"""Layout components inspired by hierarchical motion-graphics layouts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import combinations
import json
from pathlib import Path
import re

from PIL import Image

from ..core.geometry import fit_aspect, inside, overlaps
from ..core.models import AnimationSpec, Box, Canvas, ElementLayout, LayoutResult, SceneContent, Theme
from ..core.text_measure import fit_text, resolve_font, text_width
from .regions import subtitle_area as narration_subtitle_area


@dataclass(frozen=True)
class AssetGeometry:
    source_width: int
    source_height: int
    bbox: tuple[int, int, int, int]

    @property
    def visible_width(self) -> int:
        return max(1, self.bbox[2] - self.bbox[0])

    @property
    def visible_height(self) -> int:
        return max(1, self.bbox[3] - self.bbox[1])


@lru_cache(maxsize=1024)
def _asset_geometry_cached(path: str, modified_ns: int, file_size: int) -> AssetGeometry:
    """Read image bounds once, while invalidating when the file changes."""
    try:
        with Image.open(path) as image:
            width, height = image.size
            if "A" in image.getbands():
                bbox = image.getchannel("A").getbbox()
                if bbox:
                    return AssetGeometry(width, height, bbox)
            return AssetGeometry(width, height, (0, 0, width, height))
    except (OSError, ValueError):
        return AssetGeometry(4, 3, (0, 0, 4, 3))


def asset_geometry(path: str) -> AssetGeometry:
    if not path:
        return AssetGeometry(4, 3, (0, 0, 4, 3))
    try:
        image_path = Path(path)
        stat = image_path.stat()
    except OSError:
        return AssetGeometry(4, 3, (0, 0, 4, 3))
    return _asset_geometry_cached(str(image_path), stat.st_mtime_ns, stat.st_size)


def image_metadata(geometry: AssetGeometry) -> dict[str, object]:
    return {
        "source_size": [geometry.source_width, geometry.source_height],
        "source_bbox": list(geometry.bbox),
        "fit": "contain_visible",
    }


def emphasis_font_size(theme: Theme) -> int:
    return round(theme.body_font_size * 1.85)


def keyword_font_size(theme: Theme) -> int:
    return round(theme.body_font_size * 1.45)


def is_landscape(canvas: Canvas | Box) -> bool:
    return canvas.width > canvas.height


def landscape_title_height(canvas: Canvas, portrait_height: int) -> int:
    if not is_landscape(canvas):
        return portrait_height
    return max(92, min(portrait_height, round(canvas.height * 0.12)))


def landscape_title_font_size(canvas: Canvas, theme: Theme, ratio: float = 0.11) -> int:
    if not is_landscape(canvas):
        return theme.title_font_size
    return min(theme.title_font_size, round(canvas.height * ratio))


class BoardOverviewLayout:
    """Show the whole lesson map before individual numbered sections."""

    name = "board_overview"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        background = content.background_element
        role_overlays = tuple(item for item in content.overlay_image_elements if item.role == "overview_diagram")
        role_labels = tuple(item for item in content.text_elements if item.role == "major_point")
        overlays = tuple(sorted(role_overlays or content.overlay_image_elements, key=lambda item: (item.start_ms, item.element_id)))
        labels = tuple(sorted(role_labels or content.text_elements, key=lambda item: (item.start_ms, item.element_id)))
        if background is None:
            return LayoutResult(self.name, canvas, [], ["board_overview 缺少背景图"], [])

        elements = [_board_background_layout(background, content.duration_ms, canvas)]
        content_box = Box(
            canvas.content_left,
            canvas.content_top,
            canvas.content_right - canvas.content_left,
            canvas.content_bottom - canvas.content_top,
        )
        label_count = max(1, min(4, len(labels)))
        if is_landscape(canvas):
            relation_region = Box(
                content_box.x + round(content_box.width * 0.28),
                content_box.y,
                round(content_box.width * 0.44),
                round(content_box.height * 0.48),
            )
            labels_top = content_box.y + round(content_box.height * 0.55)
            gap = 28
            label_width = (content_box.width - gap * (label_count - 1)) // label_count
            label_slots = [
                Box(content_box.x + index * (label_width + gap), labels_top, label_width, content_box.bottom - labels_top)
                for index in range(label_count)
            ]
        else:
            relation_region = Box(
                content_box.x + round(content_box.width * 0.12),
                content_box.y,
                round(content_box.width * 0.76),
                round(content_box.height * 0.35),
            )
            labels_top = relation_region.bottom + 28
            slot_height = max(1, (content_box.bottom - labels_top - 16 * (label_count - 1)) // label_count)
            label_slots = [
                Box(content_box.x, labels_top + index * (slot_height + 16), content_box.width, slot_height)
                for index in range(label_count)
            ]

        for index, source in enumerate(overlays):
            slot = stack_slots(
                len(overlays),
                relation_region,
                landscape=is_landscape(canvas),
                gap=16,
            )[index]
            geometry = asset_geometry(source.content)
            elements.append(ElementLayout(
                element_id=source.element_id,
                element_type="image",
                content=source.content,
                box=fit_aspect(geometry.visible_width, geometry.visible_height, slot),
                start_ms=source.start_ms,
                end_ms=max(source.end_ms, content.duration_ms),
                z_index=20 + index,
                role="board_relation",
                animation=AnimationSpec(enter="scale_in", enter_duration_ms=260),
                metadata={**image_metadata(geometry), "board_level": "overview"},
            ))

        for index, source in enumerate(labels[:label_count]):
            slot = label_slots[index]
            measured, decision = fit_text(
                source.content,
                max_width=slot.width,
                max_height=slot.height,
                initial_size=64 if is_landscape(canvas) else 58,
                min_size=38,
                max_lines=2,
                theme=theme,
            )
            elements.append(ElementLayout(
                element_id=source.element_id,
                element_type="text",
                content=source.content,
                box=Box(slot.x, round(slot.center_y - measured.height / 2), slot.width, measured.height),
                start_ms=source.start_ms,
                end_ms=source.end_ms,
                z_index=50 + index,
                role="board_major_point",
                font_size=measured.font_size,
                lines=measured.lines,
                animation=AnimationSpec(enter="drop_bounce", enter_duration_ms=240),
                metadata={"board_level": "major", "board_index": index + 1},
            ))
        decisions = [
            f"信息图总览：先展示中心关系，再依次出现 {label_count} 个编号大点",
            "白底素材使用分区网格，不依赖透明抠图",
        ]
        return LayoutResult(self.name, canvas, elements, [], decisions)


class BoardSectionLayout:
    """Pair each numbered subpoint with one white-background diagram."""

    name = "board_section"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        background = content.background_element
        role_images = tuple(item for item in content.overlay_image_elements if item.role == "subpoint_diagram")
        role_labels = tuple(item for item in content.text_elements if item.role == "subpoint_label")
        major_titles = tuple(item for item in content.text_elements if item.role == "major_title")
        explicit_contract = bool(role_images or role_labels or major_titles)
        images = tuple(sorted(role_images or content.overlay_image_elements, key=lambda item: (item.start_ms, item.element_id)))
        labels = tuple(sorted(
            role_labels or tuple(item for item in content.text_elements if item.role != "major_title"),
            key=lambda item: (item.start_ms, item.element_id),
        ))
        if background is None:
            return LayoutResult(self.name, canvas, [], ["board_section 缺少背景图"], [])

        elements = [_board_background_layout(background, content.duration_ms, canvas)]
        count = min(len(images), len(labels))
        content_box = Box(
            canvas.content_left,
            canvas.content_top,
            canvas.content_right - canvas.content_left,
            canvas.content_bottom - canvas.content_top,
        )
        if major_titles:
            title = major_titles[0]
            title_height = 112 if is_landscape(canvas) else 104
            title_slot = Box(content_box.x, content_box.y, content_box.width, title_height)
            measured, _ = fit_text(
                title.content,
                max_width=title_slot.width,
                max_height=title_slot.height,
                initial_size=72 if is_landscape(canvas) else 60,
                min_size=42,
                max_lines=1,
                theme=theme,
            )
            elements.append(ElementLayout(
                element_id=title.element_id,
                element_type="text",
                content=title.content,
                box=Box(title_slot.x, round(title_slot.center_y - measured.height / 2), title_slot.width, measured.height),
                start_ms=title.start_ms,
                end_ms=title.end_ms,
                z_index=55,
                role="board_major_title",
                font_size=measured.font_size,
                lines=measured.lines,
                animation=AnimationSpec(enter="drop_bounce", enter_duration_ms=240),
                metadata={"board_level": "major_title"},
            ))
            content_box = Box(
                content_box.x,
                title_slot.bottom + 20,
                content_box.width,
                max(1, content_box.bottom - title_slot.bottom - 20),
            )
        gap = 36 if is_landscape(canvas) else 24
        columns = count if is_landscape(canvas) else 1
        rows = 1 if is_landscape(canvas) else max(1, count)
        cell_width = (content_box.width - gap * (columns - 1)) // max(1, columns)
        cell_height = (content_box.height - gap * (rows - 1)) // rows

        for index, (image, label) in enumerate(zip(images, labels)):
            column = index if is_landscape(canvas) else 0
            row = 0 if is_landscape(canvas) else index
            cell = Box(
                content_box.x + column * (cell_width + gap),
                content_box.y + row * (cell_height + gap),
                cell_width,
                cell_height,
            )
            label_height = round(cell.height * (0.22 if is_landscape(canvas) else 0.20))
            label_slot = Box(cell.x, cell.y, cell.width, label_height)
            image_slot = Box(cell.x + 8, label_slot.bottom + 8, cell.width - 16, cell.height - label_height - 8)
            measured, decision = fit_text(
                label.content,
                max_width=label_slot.width,
                max_height=label_slot.height,
                initial_size=54 if is_landscape(canvas) else 48,
                min_size=34,
                max_lines=2,
                theme=theme,
            )
            elements.append(ElementLayout(
                element_id=label.element_id,
                element_type="text",
                content=label.content,
                box=Box(label_slot.x, round(label_slot.center_y - measured.height / 2), label_slot.width, measured.height),
                start_ms=label.start_ms,
                end_ms=label.end_ms,
                z_index=40 + index,
                role="board_subpoint",
                font_size=measured.font_size,
                lines=measured.lines,
                animation=AnimationSpec(enter="drop_bounce", enter_duration_ms=220),
                metadata={"board_level": "minor", "board_index": index + 1},
            ))
            geometry = asset_geometry(image.content)
            elements.append(ElementLayout(
                element_id=image.element_id,
                element_type="image",
                content=image.content,
                box=fit_aspect(geometry.visible_width, geometry.visible_height, image_slot),
                start_ms=image.start_ms,
                end_ms=max(image.end_ms, content.duration_ms),
                z_index=20 + index,
                role="board_diagram",
                animation=AnimationSpec(enter="scale_in", enter_duration_ms=260),
                metadata={**image_metadata(geometry), "board_level": "minor", "board_index": index + 1},
            ))
        decisions = [
            f"板书分点：{count} 个编号小点与 {count} 张元素图一一配对",
            "所有白底图片使用互不遮挡的稳定分栏",
        ]
        warnings = []
        if len(images) != len(labels):
            warnings.append("board_section 图片与小点文字数量不一致")
        if explicit_contract and len(major_titles) != 1:
            warnings.append("board_section 必须有且只有一个大点标题")
        return LayoutResult(self.name, canvas, elements, warnings, decisions)


def _board_background_layout(source, duration_ms: int, canvas: Canvas) -> ElementLayout:
    geometry = asset_geometry(source.content)
    return ElementLayout(
        element_id=source.element_id,
        element_type="image",
        content=source.content,
        box=fit_aspect(geometry.visible_width, geometry.visible_height, Box(0, 0, canvas.width, canvas.height)),
        start_ms=source.start_ms,
        end_ms=max(source.end_ms, duration_ms),
        z_index=10,
        role="background",
        animation=AnimationSpec(enter="fade_scale", enter_duration_ms=240),
        metadata={**image_metadata(geometry), "board_level": "background"},
    )


class BackgroundStackLayout:
    """Keep the whiteboard plate visible while overlays build the explanation."""

    name = "background_stack"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        background = content.background_element
        overlays = tuple(sorted(content.overlay_image_elements, key=lambda item: (item.start_ms, item.element_id)))
        if background is None:
            raise ValueError("background_stack 缺少背景图")
        if content.text_elements:
            raise ValueError("background_stack 只接受背景图和元素图，文字应当已经包含在对应图片内容中")

        stage = Box(0, 0, canvas.width, canvas.height)
        background_hold_ms = separate_background_hold_ms(content.duration_ms, overlays)
        element_stage_duration_ms = max(1, content.duration_ms - background_hold_ms)
        remapped_overlays = sequential_element_stage_timing(
            overlays,
            background_hold_ms=background_hold_ms,
            element_stage_duration_ms=element_stage_duration_ms,
            scene_duration_ms=content.duration_ms,
            strategy=background_stack_timing_strategy(background.element_id),
        )
        base_geometry = asset_geometry(background.content)
        background_content_ratio = background_content_bottom_ratio(background.content)
        elements = [ElementLayout(
            element_id=background.element_id,
            element_type="image",
            content=background.content,
            box=stage,
            start_ms=background.start_ms,
            end_ms=content.duration_ms,
            z_index=10,
            role="background",
            animation=AnimationSpec(enter="fade_scale", enter_duration_ms=320),
            metadata={
                **image_metadata(base_geometry),
                "stack_role": "background",
                "background_phase_duration_ms": background_hold_ms,
                "background_content_bottom_ratio": background_content_ratio,
            },
        )]

        gap = board_element_gap(canvas)
        content_region = board_content_region(
            canvas,
            gap=gap,
            background_content_ratio=background_content_ratio,
        )
        layout_variant = background_stack_variant(background.element_id)
        phased_boxes = progressive_stack_boxes(
            remapped_overlays,
            content_region,
            landscape=is_landscape(canvas),
            gap=gap,
            variant=layout_variant,
        )
        decisions = [
            f"板书背景：{background.element_id} 从镜头开始持续到结束，标题区只由背景图承载",
            f"元素节奏：{background_stack_timing_strategy_name(background_stack_timing_strategy(background.element_id))}；按入场、成组讲解和退场事件重新编排",
            f"横版构图：{background_stack_variant_name(layout_variant)}；元素区从 y={content_region.y} 开始，避开背景真实文字区",
        ]
        for index, source in enumerate(remapped_overlays):
            geometry = asset_geometry(source.content)
            phases = phased_boxes.get(source.element_id, [])
            if not phases:
                raise ValueError(f"元素 {source.element_id} 没有可用的渐进布局阶段")
            box = phases[0][1]
            metadata = {
                **image_metadata(geometry),
                "stack_role": "overlay",
                "stack_index": index,
                "base_element_id": background.element_id,
                "stage_background": "whiteboard_background",
                "layout_variant": background_stack_variant_name(layout_variant),
            }
            keyframes = [
                {
                    "offset_ms": time_ms - source.start_ms,
                    "box": [target.x, target.y, target.width, target.height],
                }
                for time_ms, target in phases[1:]
                if source.start_ms < time_ms < source.end_ms
            ]
            if keyframes:
                metadata["layout_keyframes"] = keyframes
            elements.append(ElementLayout(
                element_id=source.element_id,
                element_type="image",
                content=source.content,
                box=box,
                start_ms=source.start_ms,
                end_ms=source.end_ms,
                z_index=20 + index,
                role="overlay",
                animation=AnimationSpec(
                    enter=background_stack_enter_styles(layout_variant)[index % 3],
                    enter_after_ms=0,
                    enter_duration_ms=320,
                ),
                metadata=metadata,
            ))
        validate_progressive_board(elements, content_region, minimum_gap=gap)
        return LayoutResult(self.name, canvas, elements, [], decisions)


def separate_background_hold_ms(duration_ms: int, overlays) -> int:
    """Reserve a readable board-only intro before element animation begins."""
    if duration_ms <= 1 or not overlays:
        return max(0, duration_ms)
    return min(max(800, round(duration_ms * 0.20)), 1800, max(1, duration_ms - 1))


def background_stack_timing_strategy(background_id: str) -> str:
    """Vary explainers between cumulative, paired, and relay beats."""
    return ("cumulative", "pair_then_result", "relay")[background_stack_variant(background_id)]


def background_stack_timing_strategy_name(strategy: str) -> str:
    return {
        "cumulative": "关系累计",
        "pair_then_result": "成对讲解后切换结果",
        "relay": "单张接力讲解",
    }.get(strategy, "关系累计")


def sequential_element_stage_timing(
    overlays,
    *,
    background_hold_ms: int,
    element_stage_duration_ms: int,
    scene_duration_ms: int,
    strategy: str = "cumulative",
):
    """Plan visibility beats; source timings never force every card to persist."""
    ordered = tuple(sorted(overlays, key=lambda item: (item.start_ms, item.element_id)))
    if not ordered:
        return ordered
    stage_end_ms = background_hold_ms + element_stage_duration_ms
    count = len(ordered)
    if count == 1:
        return (replace(ordered[0], start_ms=background_hold_ms, end_ms=scene_duration_ms),)

    if strategy == "pair_then_result" and count >= 3:
        # Explain the first two as one relationship, clear them, then give the result a clean stage.
        first_start = background_hold_ms
        second_start = background_hold_ms + round(element_stage_duration_ms * 0.18)
        pair_end = background_hold_ms + round(element_stage_duration_ms * 0.56)
        result_start = pair_end
        remapped = [
            replace(ordered[0], start_ms=first_start, end_ms=pair_end),
            replace(ordered[1], start_ms=second_start, end_ms=pair_end),
            replace(ordered[2], start_ms=result_start, end_ms=scene_duration_ms),
        ]
        remaining = ordered[3:]
        for index, source in enumerate(remaining):
            start_ms = result_start + round((scene_duration_ms - result_start) * index / len(remaining))
            end_ms = scene_duration_ms if index == len(remaining) - 1 else start_ms + round((scene_duration_ms - result_start) * 0.62)
            remapped.append(replace(source, start_ms=start_ms, end_ms=max(start_ms + 650, end_ms)))
        return tuple(remapped)

    if strategy == "relay":
        # One idea occupies the board at a time. A short overlap lets the transition read naturally.
        interval = element_stage_duration_ms / count
        overlap = min(260, round(interval * 0.16))
        remapped = []
        for index, source in enumerate(ordered):
            start_ms = background_hold_ms + round(interval * index)
            end_ms = scene_duration_ms if index == count - 1 else background_hold_ms + round(interval * (index + 1)) + overlap
            remapped.append(replace(source, start_ms=start_ms, end_ms=min(scene_duration_ms, end_ms)))
        return tuple(remapped)

    # Cumulative relation: each successive visual stays to form the final composite.
    remapped = []
    for index, source in enumerate(ordered):
        start_ms = background_hold_ms + round(element_stage_duration_ms * index / count)
        start_ms = min(scene_duration_ms - 1, max(background_hold_ms, start_ms))
        remapped.append(replace(source, start_ms=start_ms, end_ms=scene_duration_ms))
    return tuple(remapped)


def board_element_gap(canvas: Canvas) -> int:
    return 18 if is_landscape(canvas) else 16


def background_content_bottom_ratio(path: str) -> float:
    """Read Step 06's measured background content boundary when available."""
    try:
        image_path = Path(path)
        manifest_path = image_path.parent / "background_content_bounds.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        value = float(data.get(image_path.name, {}).get("content_bottom_ratio", 0.0))
        return min(1.0, max(0.0, value))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0.0


def board_content_region(canvas: Canvas, *, gap: int, background_content_ratio: float = 0.0) -> Box:
    subtitle_top = narration_subtitle_area(canvas).y
    bottom = min(canvas.content_bottom, subtitle_top - gap)
    measured_bottom = round(canvas.height * background_content_ratio) + max(28, gap * 2)
    top = max(canvas.content_top, round(canvas.height * 0.20), measured_bottom)
    if bottom <= top:
        # A malformed or over-sensitive background-bound measurement must not
        # make the whole project uncompilable. Fall back to the reserved top
        # fifth and let the element images occupy the remaining stage.
        top = max(canvas.content_top, round(canvas.height * 0.20))
    if bottom <= top:
        raise ValueError("标题区和字幕区之间没有可用的板书内容空间")
    return Box(
        canvas.content_left,
        top,
        canvas.content_right - canvas.content_left,
        bottom - top,
    )


def background_stack_variant(background_id: str) -> int:
    """Choose a stable horizontal composition from the shot number when available."""
    match = re.search(r"(?:^|_)s(\d+)_bg", background_id)
    if match:
        return (int(match.group(1)) - 1) % 3
    return sum(background_id.encode("utf-8")) % 3


def background_stack_variant_name(variant: int) -> str:
    return ("居中主舞台", "左侧主叙事", "上方横向流程")[variant % 3]


def background_stack_enter_styles(variant: int) -> tuple[str, str, str]:
    return (
        ("fade_scale", "slide_up", "slide_left"),
        ("slide_left", "fade_scale", "slide_up"),
        ("slide_up", "fade_scale", "slide_left"),
    )[variant % 3]


def stack_slots(count: int, region: Box, *, landscape: bool, gap: int, variant: int = 0) -> list[Box]:
    if count <= 0:
        return []
    if landscape:
        variant %= 3
        if count == 1:
            # Give a lone explanatory visual the whole stage. It reflows only
            # when another visual arrives and creates an actual relationship.
            return [region.inset(max(10, gap // 2))]
        if count == 2:
            if variant == 0:
                column_width = (region.width - gap) // 2
                return [
                    Box(region.x, region.y, column_width, region.height),
                    Box(region.x + column_width + gap, region.y, region.right - (region.x + column_width + gap), region.height),
                ]
            if variant == 1:
                main_width = round(region.width * 0.58)
                support_width = region.width - main_width - gap
                return [
                    Box(region.x, region.y, main_width, region.height),
                    Box(region.x + main_width + gap, region.y, support_width, region.height),
                ]
            support_width = round(region.width * 0.42)
            main_width = region.width - support_width - gap
            return [
                Box(region.x, region.y, support_width, region.height),
                Box(region.x + support_width + gap, region.y, main_width, region.height),
            ]
        if count == 3:
            if variant == 0:
                support_width = round(region.width * 0.38)
                support_height = (region.height - gap) // 2
                main_x = region.x + support_width + gap + round(region.width * 0.03)
                main_width = region.right - main_x
                return [
                    Box(region.x + round(region.width * 0.03), region.y, support_width, support_height),
                    Box(region.x + round(region.width * 0.03), region.y + support_height + gap, support_width, support_height),
                    Box(main_x, region.y, main_width, region.height),
                ]
            if variant == 1:
                main_width = round(region.width * 0.56)
                support_width = region.width - main_width - gap
                support_height = (region.height - gap) // 2
                return [
                    Box(region.x, region.y, main_width, region.height),
                    Box(region.x + main_width + gap, region.y, support_width, support_height),
                    Box(region.x + main_width + gap, region.y + support_height + gap, support_width, support_height),
                ]
            top_height = round(region.height * 0.52)
            support_width = (region.width - gap) // 2
            support_height = region.height - top_height - gap
            return [
                Box(region.x, region.y, region.width, top_height),
                Box(region.x, region.y + top_height + gap, support_width, support_height),
                Box(region.x + support_width + gap, region.y + top_height + gap, support_width, support_height),
            ]
        if count == 4:
            if variant == 0:
                column_width = (region.width - gap) // 2
                row_height = (region.height - gap) // 2
                right_width = region.width - column_width - gap
                bottom_height = region.height - row_height - gap
                # Column-major order preserves the one-main/two-support composition
                # used by the three-image phase when the fourth image arrives.
                return [
                    Box(region.x, region.y, column_width, row_height),
                    Box(region.x, region.y + row_height + gap, column_width, bottom_height),
                    Box(region.x + column_width + gap, region.y, right_width, row_height),
                    Box(region.x + column_width + gap, region.y + row_height + gap, right_width, bottom_height),
                ]
            if variant == 1:
                main_width = round(region.width * 0.58)
                support_width = region.width - main_width - gap
                support_height = (region.height - gap * 2) // 3
                return [
                    Box(region.x, region.y, main_width, region.height),
                    Box(region.x + main_width + gap, region.y, support_width, support_height),
                    Box(region.x + main_width + gap, region.y + support_height + gap, support_width, support_height),
                    Box(
                        region.x + main_width + gap,
                        region.y + (support_height + gap) * 2,
                        support_width,
                        region.bottom - (region.y + (support_height + gap) * 2),
                    ),
                ]
            main_height = round(region.height * 0.56)
            support_height = region.height - main_height - gap
            support_width = (region.width - gap * 2) // 3
            return [
                Box(region.x, region.y, region.width, main_height),
                Box(region.x, region.y + main_height + gap, support_width, support_height),
                Box(region.x + support_width + gap, region.y + main_height + gap, support_width, support_height),
                Box(
                    region.x + (support_width + gap) * 2,
                    region.y + main_height + gap,
                    region.right - (region.x + (support_width + gap) * 2),
                    support_height,
                ),
            ]
        if count == 5:
            # Keep a dense five-beat explanation balanced: three equal cells
            # on top and two centered cells below, rather than leaving the
            # final row visually pinned to the left edge.
            row_height = (region.height - gap) // 2
            top_width = (region.width - gap * 2) // 3
            bottom_width = (region.width - gap) // 2
            top_total = top_width * 3 + gap * 2
            bottom_total = bottom_width * 2 + gap
            top_x = region.x + (region.width - top_total) // 2
            bottom_x = region.x + (region.width - bottom_total) // 2
            bottom_y = region.y + row_height + gap
            return [
                Box(top_x + index * (top_width + gap), region.y, top_width, row_height)
                for index in range(3)
            ] + [
                Box(bottom_x + index * (bottom_width + gap), bottom_y, bottom_width, region.bottom - bottom_y)
                for index in range(2)
            ]
        columns = min(3, count)
        rows = (count + columns - 1) // columns
        slot_width = (region.width - gap * (columns - 1)) // columns
        slot_height = (region.height - gap * (rows - 1)) // rows
        if slot_width <= 0 or slot_height <= 0:
            raise ValueError(f"横屏内容区无法容纳 {count} 张元素图")
        return [
            Box(
                region.x + (index % columns) * (slot_width + gap),
                region.y + (index // columns) * (slot_height + gap),
                region.right - (region.x + (index % columns) * (slot_width + gap))
                if index % columns == columns - 1 else slot_width,
                region.bottom - (region.y + (index // columns) * (slot_height + gap))
                if index // columns == rows - 1 else slot_height,
            )
            for index in range(count)
        ]
    slot_height = (region.height - gap * (count - 1)) // count
    if slot_height <= 0:
        raise ValueError(f"竖屏内容区无法容纳 {count} 张元素图")
    return [
        Box(region.x, region.y + index * (slot_height + gap), region.width, slot_height)
        for index in range(count)
    ]


def progressive_stack_boxes(
    overlays,
    region: Box,
    *,
    landscape: bool,
    gap: int,
    variant: int = 0,
) -> dict[str, list[tuple[int, Box]]]:
    """Reflow visible overlays whenever another element enters or leaves."""
    phases: dict[str, list[tuple[int, Box]]] = {item.element_id: [] for item in overlays}
    events = sorted({time_ms for item in overlays for time_ms in (item.start_ms, item.end_ms)})
    for time_ms in events:
        active = [item for item in overlays if item.start_ms <= time_ms < item.end_ms]
        if not active:
            continue
        active.sort(key=lambda item: (item.start_ms, item.element_id))
        slots = stack_slots(len(active), region, landscape=landscape, gap=gap, variant=variant)
        for index, item in enumerate(active):
            geometry = asset_geometry(item.content)
            box = fit_aspect(geometry.visible_width, geometry.visible_height, slots[index])
            previous = phases[item.element_id][-1][1] if phases[item.element_id] else None
            if box != previous:
                phases[item.element_id].append((time_ms, box))
    return phases


def validate_progressive_board(elements: list[ElementLayout], content_region: Box, *, minimum_gap: int) -> None:
    overlays = [element for element in elements if element.role == "overlay"]
    failures: list[str] = []
    for element in overlays:
        boxes = [element.box]
        boxes.extend(
            Box(*(int(value) for value in item["box"]))
            for item in element.metadata.get("layout_keyframes", [])
            if isinstance(item, dict) and isinstance(item.get("box"), list) and len(item["box"]) == 4
        )
        if any(not box_inside(box, content_region) for box in boxes):
            failures.append(
                f"元素 {element.element_id} 越过板书安全内容区："
                f"({element.box.x},{element.box.y},{element.box.width},{element.box.height})"
            )
    events = sorted({time_ms for element in overlays for time_ms in (element.start_ms, element.end_ms)})
    for time_ms in events:
        active = [element for element in overlays if element.start_ms <= time_ms < element.end_ms]
        for first, second in combinations(active, 2):
            if overlaps(_layout_box_at(first, time_ms), _layout_box_at(second, time_ms), gap=minimum_gap):
                failures.append(f"元素 {first.element_id} 与 {second.element_id} 在 {time_ms}ms 间距不足或发生重叠")
    if failures:
        raise ValueError("background_stack 布局校验失败：" + "；".join(failures))


def _final_layout_box(element: ElementLayout) -> Box:
    keyframes = element.metadata.get("layout_keyframes", [])
    if isinstance(keyframes, list) and keyframes:
        raw_box = keyframes[-1].get("box") if isinstance(keyframes[-1], dict) else None
        if isinstance(raw_box, list) and len(raw_box) == 4:
            return Box(*(int(value) for value in raw_box))
    return element.box


def _layout_box_at(element: ElementLayout, time_ms: int) -> Box:
    active_box = element.box
    for item in element.metadata.get("layout_keyframes", []):
        if not isinstance(item, dict) or not isinstance(item.get("box"), list):
            continue
        if element.start_ms + int(item.get("offset_ms", 0)) > time_ms:
            break
        raw_box = item["box"]
        if len(raw_box) == 4:
            active_box = Box(*(int(value) for value in raw_box))
    return active_box


def box_inside(box: Box, region: Box) -> bool:
    return (
        box.x >= region.x
        and box.y >= region.y
        and box.right <= region.right
        and box.bottom <= region.bottom
    )


class TimelineFlowLayout:
    name = "timeline_flow"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        images = content.image_elements
        labels = content.text_elements
        number_labels = {
            label.element_id
            for label in labels
            if (target := overlay_image_for(label, images)) is not None
        }
        left = canvas.content_left
        width = canvas.content_right - left
        region = Box(
            left,
            canvas.content_top,
            width,
            canvas.content_bottom - canvas.content_top,
        )
        elements: list[ElementLayout] = []
        decisions = [f"共同编排：{len(images)} 张图片、{len(labels)} 个关键词均保留源时间并参与布局"]
        image_lanes, image_lane_count = assign_interval_lanes(images)
        label_lanes, label_lane_count = assign_interval_lanes(labels)
        image_slots, label_slots = mixed_phase_slots(
            image_lane_count,
            label_lane_count,
            region,
            stable_layout_variant(content),
        )
        decisions.append(
            f"场景级稳定槽位：图片 {image_lane_count} 轨、关键词 {label_lane_count} 轨；"
            "时间重叠元素分轨，非重叠元素复用"
        )
        phased_boxes: dict[str, list[tuple[int, Box]]] = {}
        if image_lane_count > 1:
            image_region = timeline_image_region(label_lane_count, region, stable_layout_variant(content))
            phased_boxes = progressive_image_boxes(images, image_lanes, image_region)
            phase_count = len({time_ms for phases in phased_boxes.values() for time_ms, _ in phases})
            decisions.append(f"分阶段图片重排：按当前可见图片数生成 {phase_count} 个布局阶段")

        for source in images:
            lane = image_lanes[source.element_id]
            slot = image_slots[lane]
            geometry = asset_geometry(source.content)
            box = fit_aspect(geometry.visible_width, geometry.visible_height, slot)
            metadata = image_metadata(geometry)
            phases = phased_boxes.get(source.element_id, [])
            if phases:
                box = phases[0][1]
                keyframes = [
                    {
                        "offset_ms": time_ms - source.start_ms,
                        "box": [target.x, target.y, target.width, target.height],
                    }
                    for time_ms, target in phases[1:]
                    if source.start_ms < time_ms < source.end_ms
                ]
                if keyframes:
                    metadata["layout_keyframes"] = keyframes
            elements.append(ElementLayout(
                element_id=source.element_id,
                element_type="image",
                content=source.content,
                box=box,
                start_ms=source.start_ms,
                end_ms=source.end_ms,
                z_index=10 + lane,
                role="main" if lane == 0 else "support",
                animation=AnimationSpec(enter="fade_scale", enter_duration_ms=320),
                metadata=metadata,
            ))

        for source in labels:
            lane = label_lanes[source.element_id]
            label_box = label_slots[lane]
            role = "number" if source.element_id in number_labels else "label"
            initial_size = emphasis_font_size(theme) if role == "number" else keyword_font_size(theme)
            formatted_text = balanced_keyword_text(
                source.content,
                max_width=label_box.width,
                max_height=label_box.height,
                font_size=initial_size,
                max_lines=3,
                theme=theme,
            )
            measured, decision = fit_text(
                formatted_text,
                max_width=label_box.width,
                max_height=label_box.height,
                initial_size=initial_size,
                min_size=64,
                max_lines=3,
                theme=theme,
            )
            if decision:
                decisions.append(f"关键词 {source.element_id}：{decision}")
            elements.append(ElementLayout(
                element_id=source.element_id,
                element_type="text",
                content=source.content,
                box=Box(
                    label_box.x,
                    round(label_box.center_y - measured.height / 2),
                    label_box.width,
                    measured.height,
                ),
                start_ms=source.start_ms,
                end_ms=source.end_ms,
                z_index=30 + lane,
                role=role,
                font_size=measured.font_size,
                lines=measured.lines,
                animation=AnimationSpec(enter="drop_bounce", enter_duration_ms=260),
            ))

        warnings = []
        if not elements:
            warnings.append("timeline_flow 没有可布局元素")
        return LayoutResult(self.name, canvas, elements, warnings, decisions)


def assign_interval_lanes(elements) -> tuple[dict[str, int], int]:
    """Color an interval graph so simultaneous elements never share a visual slot."""
    lanes: list[int] = []
    assignments: dict[str, int] = {}
    for element in sorted(elements, key=lambda item: (item.start_ms, item.end_ms, item.element_id)):
        lane = next((index for index, available_at in enumerate(lanes) if available_at <= element.start_ms), None)
        if lane is None:
            lane = len(lanes)
            lanes.append(element.end_ms)
        else:
            lanes[lane] = element.end_ms
        assignments[element.element_id] = lane
    return assignments, len(lanes)


def stable_layout_variant(content: SceneContent) -> int:
    """Choose scene-level variety without making placement depend on timing fragments."""
    identity = "|".join(element.element_id for element in content.elements) or content.title
    return sum(identity.encode("utf-8")) % 4


def overlay_image_for(label, images):
    markers = ("标签牌", "利润标签", "日期牌")
    for image in images:
        if image.start_ms != label.start_ms or image.end_ms != label.end_ms:
            continue
        if any(marker in image.source_content for marker in markers):
            return image
    return None


def mixed_phase_slots(
    image_count: int,
    keyword_count: int,
    region: Box,
    phase_index: int,
) -> tuple[list[Box], list[Box]]:
    if keyword_count == 0:
        return phase_slots(image_count, region), []
    if image_count == 0:
        return [], keyword_phase_slots(keyword_count, region.inset(20))

    inner = region.inset(20)
    landscape = is_landscape(region)
    gap = 28 if landscape else 32
    if image_count == 1 and keyword_count == 1:
        variant = phase_index % 4
        if landscape or variant in {0, 2}:
            keyword_width = round((inner.width - gap) * (0.28 if landscape else 0.27))
            image_width = inner.width - gap - keyword_width
            if landscape or variant == 2:
                image_box = Box(inner.x, inner.y, image_width, inner.height)
                keyword_box = Box(inner.x + image_width + gap, inner.y, keyword_width, inner.height)
            else:
                keyword_box = Box(inner.x, inner.y, keyword_width, inner.height)
                image_box = Box(inner.x + keyword_width + gap, inner.y, image_width, inner.height)
            return [image_box], [keyword_box]

        keyword_height = min(280, round((inner.height - gap) * 0.24))
        image_height = inner.height - gap - keyword_height
        top_keyword_box = Box(inner.x, inner.y, inner.width, keyword_height)
        bottom_image_box = Box(inner.x, inner.y + keyword_height + gap, inner.width, image_height)
        if variant == 1:
            return [bottom_image_box], [top_keyword_box]
        top_image_box = Box(inner.x, inner.y, inner.width, image_height)
        bottom_keyword_box = Box(inner.x, inner.y + image_height + gap, inner.width, keyword_height)
        return [top_image_box], [bottom_keyword_box]

    if landscape:
        keyword_width = min(460, max(320, round(inner.width * 0.26)))
        image_width = inner.width - gap - keyword_width
        if phase_index % 2 == 0:
            image_region = Box(inner.x, inner.y, image_width, inner.height)
            keyword_region = Box(inner.x + image_width + gap, inner.y, keyword_width, inner.height)
        else:
            keyword_region = Box(inner.x, inner.y, keyword_width, inner.height)
            image_region = Box(inner.x + keyword_width + gap, inner.y, image_width, inner.height)
        return phase_slots(image_count, image_region), keyword_phase_slots(keyword_count, keyword_region)

    image_region = timeline_image_region(keyword_count, region, phase_index)
    keyword_height = inner.height - gap - image_region.height
    keyword_region = (
        Box(inner.x, image_region.bottom + gap, inner.width, keyword_height)
        if phase_index % 2 == 0
        else Box(inner.x, inner.y, inner.width, keyword_height)
    )
    return phase_slots(image_count, image_region), keyword_phase_slots(keyword_count, keyword_region)


def timeline_image_region(keyword_count: int, region: Box, phase_index: int) -> Box:
    """Reserve one stable image stage; only its internal composition reflows."""
    if keyword_count == 0:
        return region
    inner = region.inset(20)
    gap = 28 if is_landscape(region) else 32
    if is_landscape(region):
        keyword_width = min(460, max(320, round(inner.width * 0.26)))
        image_width = inner.width - gap - keyword_width
        if phase_index % 2 == 0:
            return Box(inner.x, inner.y, image_width, inner.height)
        return Box(inner.x + keyword_width + gap, inner.y, image_width, inner.height)
    keyword_height = 280 if keyword_count == 2 else min(270, max(230, round(inner.height * 0.23)))
    image_height = inner.height - gap - keyword_height
    if phase_index % 2 == 0:
        return Box(inner.x, inner.y, inner.width, image_height)
    return Box(inner.x, inner.y + keyword_height + gap, inner.width, image_height)


def progressive_image_boxes(images, lanes: dict[str, int], region: Box) -> dict[str, list[tuple[int, Box]]]:
    """Compute geometry at each visibility change without changing source timing."""
    events = sorted({time_ms for image in images for time_ms in (image.start_ms, image.end_ms)})
    phases: dict[str, list[tuple[int, Box]]] = {image.element_id: [] for image in images}
    for time_ms in events:
        active = sorted(
            (image for image in images if image.start_ms <= time_ms < image.end_ms),
            key=lambda image: (lanes[image.element_id], image.start_ms, image.element_id),
        )
        if not active:
            continue
        slots = aspect_aware_phase_slots(active, region)
        for index, image in enumerate(active):
            geometry = asset_geometry(image.content)
            box = fit_aspect(geometry.visible_width, geometry.visible_height, slots[index])
            previous = phases[image.element_id][-1][1] if phases[image.element_id] else None
            if box != previous:
                phases[image.element_id].append((time_ms, box))
    return phases


def aspect_aware_phase_slots(images, region: Box) -> list[Box]:
    """Keep portrait heroes tall and let wide diagrams span the stage."""
    count = len(images)
    if count < 3:
        return phase_slots(count, region)
    main_geometry = asset_geometry(images[0].content)
    main_ratio = main_geometry.visible_width / main_geometry.visible_height
    if main_ratio >= 1.35:
        return hero_top_slots(count, region)
    return hero_side_slots(count, region)


def keyword_phase_slots(count: int, region: Box) -> list[Box]:
    if count <= 1:
        return [region.inset(16)]
    gap = 20 if is_landscape(region) else 28
    columns = 1 if count == 2 or region.width < 520 else 2
    rows = (count + columns - 1) // columns
    slot_width = (region.width - gap * (columns - 1)) // columns
    slot_height = (region.height - gap * (rows - 1)) // rows
    return [
        Box(
            region.x + (index % columns) * (slot_width + gap),
            region.y + (index // columns) * (slot_height + gap),
            slot_width,
            slot_height,
        ).inset(12)
        for index in range(count)
    ]


def balanced_keyword_text(
    text: str,
    *,
    max_width: int,
    max_height: int,
    font_size: int,
    max_lines: int,
    theme: Theme,
) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    compact = normalized.replace(" ", "")
    font = resolve_font(theme.font_path, font_size)
    line_height = max(font_size, round(font_size * theme.line_height))
    semantic_lines = semantic_keyword_lines(normalized, compact)
    if (
        1 < len(semantic_lines) <= max_lines
        and line_height * len(semantic_lines) <= max_height
        and max(text_width(line, font) for line in semantic_lines) <= max_width
    ):
        return "\n".join(semantic_lines)

    if text_width(normalized, font) <= max_width and line_height <= max_height:
        return normalized

    tokens = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]", compact)
    interval_widths: list[list[int]] | None = None
    if len(tokens) >= 20:
        interval_widths = [[0] * (len(tokens) + 1) for _ in tokens]
        for start in range(len(tokens)):
            value = ""
            for end in range(start + 1, len(tokens) + 1):
                value += tokens[end - 1]
                interval_widths[start][end] = text_width(value, font)
    for line_count in range(2, min(max_lines, len(tokens)) + 1):
        if line_height * line_count > max_height:
            continue
        candidates: list[tuple[tuple[float, float, float, float], tuple[str, ...]]] = []
        for breaks in combinations(range(1, len(tokens)), line_count - 1):
            boundaries = (0, *breaks, len(tokens))
            lines = tuple(
                "".join(tokens[boundaries[index]:boundaries[index + 1]])
                for index in range(line_count)
            )
            if interval_widths is None:
                widths = tuple(text_width(line, font) for line in lines)
            else:
                widths = tuple(
                    interval_widths[boundaries[index]][boundaries[index + 1]]
                    for index in range(line_count)
                )
            if max(widths) > max_width:
                continue
            orphan_count = sum(len(line) == 1 for line in lines)
            awkward_breaks = sum(
                lines[index].endswith("第") or lines[index + 1].startswith(("月", "年", "日"))
                for index in range(len(lines) - 1)
            )
            average = sum(widths) / len(widths)
            imbalance = max(widths) - min(widths)
            variance = sum((width - average) ** 2 for width in widths)
            candidates.append(((orphan_count, awkward_breaks, imbalance, variance), lines))
        if candidates:
            return "\n".join(min(candidates, key=lambda item: item[0])[1])
    return compact


def semantic_keyword_lines(normalized: str, compact: str) -> tuple[str, ...]:
    boundaries: set[int] = set()
    cursor = 0
    words = normalized.split(" ")
    for word in words[:-1]:
        cursor += len(word)
        boundaries.add(cursor)

    for token in ("上涨", "下跌", "会跌", "买回", "卖出", "还给", "后还", "亏损", "流程"):
        start = 0
        while True:
            index = compact.find(token, start)
            if index < 0:
                break
            if index > 0:
                boundaries.add(index)
            start = index + len(token)
    ordered = (0, *sorted(boundary for boundary in boundaries if 0 < boundary < len(compact)), len(compact))
    return tuple(compact[ordered[index]:ordered[index + 1]] for index in range(len(ordered) - 1))


def phase_slots(count: int, region: Box) -> list[Box]:
    if count <= 1:
        return [region.inset(20 if is_landscape(region) else 36)]
    landscape = is_landscape(region)
    gap = 24 if landscape else 28
    if count == 2:
        slot_width = (region.width - gap) // 2
        y_pad = 16 if landscape else 40
        return [
            Box(region.x, region.y + y_pad, slot_width, region.height - y_pad * 2),
            Box(region.x + slot_width + gap, region.y + y_pad, slot_width, region.height - y_pad * 2),
        ]
    if count == 3:
        return hero_top_slots(count, region)
    if count == 4:
        return hero_side_slots(count, region)
    columns = 2 if count <= 4 else 3
    rows = (count + columns - 1) // columns
    slot_width = (region.width - gap * (columns - 1)) // columns
    slot_height = (region.height - gap * (rows - 1)) // rows
    slots: list[Box] = []
    for index in range(count):
        row = index // columns
        column = index % columns
        slots.append(Box(
            region.x + column * (slot_width + gap),
            region.y + row * (slot_height + gap),
            slot_width,
            slot_height,
        ))
    return slots


def hero_top_slots(count: int, region: Box) -> list[Box]:
    gap = 28
    support_count = count - 1
    main_height = round((region.height - gap) * 0.56)
    support_height = region.height - gap - main_height
    support_width = (region.width - gap * (support_count - 1)) // support_count
    return [
        Box(region.x, region.y, region.width, main_height),
        *[
            Box(
                region.x + index * (support_width + gap),
                region.y + main_height + gap,
                support_width,
                support_height,
            )
            for index in range(support_count)
        ],
    ]


def hero_side_slots(count: int, region: Box) -> list[Box]:
    gap = 28
    support_count = count - 1
    main_width = round((region.width - gap) * 0.52)
    support_width = region.width - gap - main_width
    support_height = (region.height - gap * (support_count - 1)) // support_count
    return [
        Box(region.x, region.y, main_width, region.height),
        *[
            Box(
                region.x + main_width + gap,
                region.y + index * (support_height + gap),
                support_width,
                support_height,
            )
            for index in range(support_count)
        ],
    ]


class TitleImageLayout:
    name = "title_image"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        image_source = content.image_elements[0] if content.image_elements else None
        title_source = content.text_elements[0] if content.text_elements else None
        left = canvas.content_left
        width = canvas.content_right - left
        top = canvas.content_top
        height = canvas.content_bottom - top
        warnings: list[str] = []
        decisions: list[str] = []
        image_content = image_source.content if image_source else (content.images[0] if content.images else "")

        if is_landscape(canvas):
            gap = 44
            image_width = round(width * 0.62) if content.title else width
            image_region = Box(left, top, image_width, height)
            title_area = Box(left + image_width + gap, top + 38, max(280, width - image_width - gap), height - 76)
            title, decision = fit_text(
                content.title,
                max_width=title_area.width,
                max_height=title_area.height,
                initial_size=landscape_title_font_size(canvas, theme),
                min_size=38,
                max_lines=theme.title_max_lines,
                theme=theme,
            ) if content.title else (None, None)
            if decision:
                decisions.append(f"标题：{decision}")
            geometry = asset_geometry(image_content)
            image_box = fit_aspect(geometry.visible_width, geometry.visible_height, image_region)
            elements = [
                ElementLayout(
                    element_id=image_source.element_id if image_source else "image_0",
                    element_type="image",
                    content=image_content,
                    box=image_box,
                    start_ms=image_source.start_ms if image_source else 0,
                    end_ms=image_source.end_ms if image_source else content.duration_ms,
                    z_index=10,
                    role="main",
                    animation=AnimationSpec(enter="fade_scale", enter_after_ms=120),
                    metadata=image_metadata(geometry),
                )
            ]
            if title:
                elements.append(ElementLayout(
                    element_id=title_source.element_id if title_source else "title",
                    element_type="text",
                    content=content.title,
                    box=Box(title_area.x, round(title_area.center_y - title.height / 2), title_area.width, title.height),
                    start_ms=title_source.start_ms if title_source else 0,
                    end_ms=title_source.end_ms if title_source else content.duration_ms,
                    z_index=20,
                    role="title",
                    font_size=title.font_size,
                    lines=title.lines,
                    animation=AnimationSpec(enter="slide_up", enter_duration_ms=360),
                ))
            return LayoutResult(self.name, canvas, elements, warnings, decisions)

        title_area = Box(left, canvas.content_top, width, 270)
        title, decision = fit_text(
            content.title,
            max_width=title_area.width,
            max_height=title_area.height,
            initial_size=theme.title_font_size,
            min_size=48,
            max_lines=theme.title_max_lines,
            theme=theme,
        )
        if decision:
            decisions.append(f"标题：{decision}")
        title_box = Box(left, title_area.y, width, title.height)

        subtitle_area = Box(left, canvas.content_bottom - 170, width, 150)
        subtitle, subtitle_decision = fit_text(
            content.subtitle,
            max_width=subtitle_area.width,
            max_height=subtitle_area.height,
            initial_size=theme.subtitle_font_size,
            min_size=28,
            max_lines=theme.subtitle_max_lines,
            theme=theme,
        ) if content.subtitle else (None, None)
        if subtitle_decision:
            decisions.append(f"副标题：{subtitle_decision}")

        image_region = Box(
            left,
            title_box.bottom + 44,
            width,
            max(240, subtitle_area.y - title_box.bottom - 76),
        )
        geometry = asset_geometry(image_content)
        image_box = fit_aspect(geometry.visible_width, geometry.visible_height, image_region)
        elements = [
            ElementLayout(
                element_id=title_source.element_id if title_source else "title",
                element_type="text",
                content=content.title,
                box=title_box,
                start_ms=title_source.start_ms if title_source else 0,
                end_ms=title_source.end_ms if title_source else content.duration_ms,
                z_index=20,
                role="title",
                font_size=title.font_size,
                lines=title.lines,
                animation=AnimationSpec(enter="slide_up", enter_duration_ms=360),
            ),
            ElementLayout(
                element_id=image_source.element_id if image_source else "image_0",
                element_type="image",
                content=image_content,
                box=image_box,
                start_ms=image_source.start_ms if image_source else 0,
                end_ms=image_source.end_ms if image_source else content.duration_ms,
                z_index=10,
                role="main",
                animation=AnimationSpec(enter="fade_scale", enter_after_ms=120),
                metadata=image_metadata(geometry),
            ),
        ]
        if subtitle:
            subtitle_box = Box(left, subtitle_area.y, width, subtitle.height)
            elements.append(
                ElementLayout(
                    element_id="subtitle",
                    element_type="text",
                    content=content.subtitle,
                    box=subtitle_box,
                    start_ms=240,
                    end_ms=content.duration_ms,
                    z_index=30,
                    role="subtitle",
                    font_size=subtitle.font_size,
                    lines=subtitle.lines,
                    animation=AnimationSpec(enter="fade_in", enter_after_ms=240),
                )
            )

        for first_index, first in enumerate(elements):
            for second in elements[first_index + 1 :]:
                if overlaps(first.box, second.box, gap=8) and first.element_type == second.element_type:
                    warnings.append(f"布局重叠：{first.element_id} / {second.element_id}")
        return LayoutResult(self.name, canvas, elements, warnings, decisions)


class FocusHistoryLayout:
    name = "focus_history"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        left = canvas.content_left
        width = canvas.content_right - left
        decisions: list[str] = []
        warnings: list[str] = []
        images = list(content.images)
        if not images:
            warnings.append("focus_history 没有图片")
            return LayoutResult(self.name, canvas, [], warnings, decisions)

        title_height = landscape_title_height(canvas, 190) if content.title else 0
        title_box = Box(left, canvas.content_top, width, title_height)
        main_top = title_box.bottom + (22 if is_landscape(canvas) else 32)
        history_height = 210 if len(images) > 1 and not is_landscape(canvas) else 0
        if is_landscape(canvas) and len(images) > 1:
            history_count = min(4, max(0, len(images) - 1))
            rail_gap = 30
            rail_width = min(360, max(260, round(width * 0.2))) if history_count else 0
            main_region = Box(left, main_top, width - rail_width - rail_gap, canvas.content_bottom - main_top)
            history_region = Box(left + main_region.width + rail_gap, main_top, rail_width, main_region.height)
        else:
            history_count = min(4, max(0, len(images) - 1))
            main_region = Box(left, main_top, width, canvas.content_bottom - main_top - history_height - 32)
            history_region = Box(left, canvas.content_bottom - history_height, width, history_height)
        main_geometry = asset_geometry(images[-1])
        main_box = fit_aspect(main_geometry.visible_width, main_geometry.visible_height, main_region)
        elements: list[ElementLayout] = []

        if content.title:
            title, decision = fit_text(
                content.title,
                max_width=width,
                max_height=title_height,
                initial_size=landscape_title_font_size(canvas, theme),
                min_size=46,
                max_lines=2,
                theme=theme,
            )
            if decision:
                decisions.append(f"标题：{decision}")
            elements.append(ElementLayout(
                "title", "text", content.title, title_box, 0, content.duration_ms,
                30, "title", title.font_size, title.lines,
                AnimationSpec(enter="slide_up"),
            ))

        if len(images) > 5:
            decisions.append("历史图片超过 4 张，仅保留最近 4 张")
        slot_gap = 18
        slot_width = (width - slot_gap * (history_count - 1)) // max(1, history_count)
        for index, image in enumerate(images[-history_count - 1 : -1] if history_count else []):
            if is_landscape(canvas):
                slot_height = (history_region.height - slot_gap * (history_count - 1)) // max(1, history_count)
                slot = Box(history_region.x, history_region.y + index * (slot_height + slot_gap), history_region.width, slot_height)
            else:
                slot = Box(left + index * (slot_width + slot_gap), history_region.y, slot_width, history_height)
            geometry = asset_geometry(image)
            thumbnail = fit_aspect(geometry.visible_width, geometry.visible_height, slot)
            elements.append(ElementLayout(
                element_id=f"history_{index}",
                element_type="image",
                content=image,
                box=thumbnail,
                start_ms=180 + index * 90,
                end_ms=content.duration_ms,
                z_index=10 + index,
                role="history",
                animation=AnimationSpec(enter="slide_left", enter_after_ms=180 + index * 90),
                metadata=image_metadata(geometry),
            ))

        elements.append(ElementLayout(
            element_id="focus_image",
            element_type="image",
            content=images[-1],
            box=main_box,
            start_ms=120,
            end_ms=content.duration_ms,
            z_index=20,
            role="main",
            animation=AnimationSpec(enter="scale_in", enter_after_ms=120),
            metadata={**image_metadata(main_geometry), "history_count": history_count},
        ))

        occupied = [element.box for element in elements]
        if not all(inside(box, canvas) for box in occupied):
            warnings.append("有元素超出安全区")
        if content.subtitle:
            warnings.append("focus_history 当前忽略 subtitle，请使用独立字幕轨道")
        return LayoutResult(self.name, canvas, elements, warnings, decisions)


class SingleSideLayout:
    name = "single_side"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        left = canvas.content_left
        top = canvas.content_top
        width = canvas.content_right - left
        height = canvas.content_bottom - top
        landscape = is_landscape(canvas)
        gap = 42 if not landscape else 48
        image_region = (
            Box(left, top + 90, round(width * 0.58), height - 180)
            if not landscape
            else Box(left, top, round(width * 0.62), height)
        )
        text_region = (
            Box(image_region.right + gap, top + 260, width - image_region.width - gap, 620)
            if not landscape
            else Box(image_region.right + gap, top + 54, width - image_region.width - gap, height - 108)
        )
        image = content.images[0] if content.images else ""
        geometry = asset_geometry(image)
        image_box = fit_aspect(geometry.visible_width, geometry.visible_height, image_region)
        headline = content.title or (content.labels[0] if content.labels else "")
        measured, decision = fit_text(
            headline,
            max_width=text_region.width,
            max_height=text_region.height,
            initial_size=landscape_title_font_size(canvas, theme),
            min_size=38,
            max_lines=6,
            theme=theme,
        )
        elements = [ElementLayout(
            "image_0", "image", image, image_box, 80, content.duration_ms,
            10, "main", animation=AnimationSpec(enter="fade_scale", enter_after_ms=80),
            metadata=image_metadata(geometry),
        )]
        if headline:
            elements.append(ElementLayout(
                "title", "text", headline,
                Box(text_region.x, text_region.y, text_region.width, measured.height),
                0, content.duration_ms, 30, "title", measured.font_size, measured.lines,
                AnimationSpec(enter="slide_up"),
            ))
        decisions = [f"标题：{decision}"] if decision else []
        return LayoutResult(self.name, canvas, elements, [], decisions)


class SingleFocusLayout:
    name = "single_focus"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        left = canvas.content_left
        top = canvas.content_top
        width = canvas.content_right - left
        height = canvas.content_bottom - top
        image = content.images[0] if content.images else ""
        geometry = asset_geometry(image)
        image_region = Box(left, top, width, height) if is_landscape(canvas) else Box(left, top + 80, width, height - 160)
        image_box = fit_aspect(geometry.visible_width, geometry.visible_height, image_region)
        elements = [ElementLayout(
            "image_0", "image", image, image_box, 60, content.duration_ms,
            10, "main", animation=AnimationSpec(enter="scale_in", enter_after_ms=60),
            metadata=image_metadata(geometry),
        )]
        if content.title:
            measured, decision = fit_text(
                content.title,
                max_width=width - 80,
                max_height=landscape_title_height(canvas, 180),
                initial_size=landscape_title_font_size(canvas, theme),
                min_size=38,
                max_lines=3,
                theme=theme,
            )
            elements.append(ElementLayout(
                "title", "text", content.title,
                Box(left + 40, top + (12 if is_landscape(canvas) else 20), width - 80, measured.height),
                0, content.duration_ms, 30, "title", measured.font_size, measured.lines,
                AnimationSpec(enter="fade_in"),
                metadata={"overlay": True},
            ))
            decisions = [f"标题：{decision}"] if decision else []
        else:
            decisions = []
        return LayoutResult(self.name, canvas, elements, [], decisions)


class MultiGridLayout:
    name = "multi_grid"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        images = list(content.images[:6])
        left = canvas.content_left
        top = canvas.content_top
        width = canvas.content_right - left
        landscape = is_landscape(canvas)
        title_height = landscape_title_height(canvas, 170) if content.title else 0
        grid_top = top + title_height + (20 if landscape else 28)
        grid_height = canvas.content_bottom - grid_top
        columns = max(1, min(len(images), 4)) if landscape and len(images) <= 4 else (2 if len(images) <= 4 else 3)
        rows = max(1, (len(images) + columns - 1) // columns)
        gap = 22 if not landscape else 24
        cell_width = (width - gap * (columns - 1)) // columns
        cell_height = (grid_height - gap * (rows - 1)) // rows
        elements: list[ElementLayout] = []
        decisions: list[str] = []
        if content.title:
            measured, decision = fit_text(
                content.title, max_width=width, max_height=title_height,
                initial_size=landscape_title_font_size(canvas, theme), min_size=38, max_lines=3, theme=theme,
            )
            if decision:
                decisions.append(f"标题：{decision}")
            elements.append(ElementLayout(
                "title", "text", content.title, Box(left, top, width, measured.height),
                0, content.duration_ms, 30, "title", measured.font_size, measured.lines,
                AnimationSpec(enter="slide_up"),
            ))
        for index, image in enumerate(images):
            cell = Box(
                left + (index % columns) * (cell_width + gap),
                grid_top + (index // columns) * (cell_height + gap),
                cell_width,
                cell_height,
            )
            geometry = asset_geometry(image)
            elements.append(ElementLayout(
                f"image_{index}", "image", image, fit_aspect(geometry.visible_width, geometry.visible_height, cell),
                100 + index * 100, content.duration_ms, 10 + index, "support",
                animation=AnimationSpec(enter="fade_scale", enter_after_ms=100 + index * 100),
                metadata=image_metadata(geometry),
            ))
        return LayoutResult(self.name, canvas, elements, [], decisions)


class MultiStackLayout:
    name = "multi_stack"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        images = list(content.images[-4:])
        left = canvas.content_left
        top = canvas.content_top
        width = canvas.content_right - left
        landscape = is_landscape(canvas)
        title_height = landscape_title_height(canvas, 170) if content.title else 0
        horizontal_pad = 48 if landscape else 80
        stage = Box(
            left + horizontal_pad,
            top + title_height + (26 if landscape else 40),
            width - horizontal_pad * 2,
            canvas.content_bottom - top - title_height - (52 if landscape else 80),
        )
        offsets = ((-70, -45), (55, -15), (-35, 45), (65, 75)) if not landscape else ((-110, -28), (84, -8), (-58, 34), (116, 54))
        elements: list[ElementLayout] = []
        decisions: list[str] = []
        if content.title:
            measured, decision = fit_text(
                content.title, max_width=width, max_height=title_height,
                initial_size=landscape_title_font_size(canvas, theme), min_size=38, max_lines=3, theme=theme,
            )
            if decision:
                decisions.append(f"标题：{decision}")
            elements.append(ElementLayout(
                "title", "text", content.title, Box(left, top, width, measured.height),
                0, content.duration_ms, 40, "title", measured.font_size, measured.lines,
                AnimationSpec(enter="slide_up"),
            ))
        target_width = round(stage.width * (0.52 if landscape else 0.72))
        target_height = round(stage.height * (0.82 if landscape else 0.68))
        for index, image in enumerate(images):
            offset_x, offset_y = offsets[index]
            target = Box(
                round(stage.center_x - target_width / 2 + offset_x),
                round(stage.center_y - target_height / 2 + offset_y),
                target_width,
                target_height,
            )
            geometry = asset_geometry(image)
            elements.append(ElementLayout(
                f"image_{index}", "image", image, fit_aspect(geometry.visible_width, geometry.visible_height, target),
                120 + index * 150, content.duration_ms, 10 + index, "support" if index < len(images) - 1 else "main",
                animation=AnimationSpec(enter="fade_scale", enter_after_ms=120 + index * 150),
                metadata=image_metadata(geometry),
            ))
        return LayoutResult(self.name, canvas, elements, [], decisions)


class QuoteLayout:
    name = "quote"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        text = content.title or "\n".join(content.labels)
        width = canvas.content_right - canvas.content_left
        if is_landscape(canvas):
            area = Box(
                canvas.content_left + 100,
                canvas.content_top + 80,
                width - 200,
                canvas.content_bottom - canvas.content_top - 160,
            )
        else:
            area = Box(canvas.content_left + 60, canvas.content_top + 340, width - 120, 700)
        measured, decision = fit_text(
            text, max_width=area.width, max_height=area.height,
            initial_size=landscape_title_font_size(canvas, theme, 0.12), min_size=46, max_lines=6, theme=theme,
        )
        element = ElementLayout(
            "quote", "text", text,
            Box(area.x, round(area.center_y - measured.height / 2), area.width, measured.height),
            0, content.duration_ms, 30, "title", measured.font_size, measured.lines,
            AnimationSpec(enter="fade_in"),
        )
        decisions = [f"金句：{decision}"] if decision else []
        return LayoutResult(self.name, canvas, [element], [], decisions)


class SplitCompareLayout:
    name = "split_compare"

    def build(self, content: SceneContent, canvas: Canvas, theme: Theme) -> LayoutResult:
        left = canvas.content_left
        width = canvas.content_right - left
        landscape = is_landscape(canvas)
        gap = 28 if landscape else 24
        column_width = (width - gap) // 2
        title_height = landscape_title_height(canvas, 190)
        title_box = Box(left, canvas.content_top, width, title_height)
        card_top = title_box.bottom + (26 if landscape else 42)
        card_height = canvas.content_bottom - card_top
        cards = (
            Box(left, card_top, column_width, card_height),
            Box(left + column_width + gap, card_top, column_width, card_height),
        )
        elements: list[ElementLayout] = []
        decisions: list[str] = []
        warnings: list[str] = []

        title, decision = fit_text(
            content.title,
            max_width=width,
            max_height=title_height,
            initial_size=landscape_title_font_size(canvas, theme),
            min_size=46,
            max_lines=2,
            theme=theme,
        )
        if decision:
            decisions.append(f"标题：{decision}")
        elements.append(ElementLayout(
            "title", "text", content.title, title_box, 0, content.duration_ms,
            30, "title", title.font_size, title.lines, AnimationSpec(enter="slide_up"),
        ))

        for index, card in enumerate(cards):
            label = content.labels[index] if index < len(content.labels) else ("之前" if index == 0 else "之后")
            label_measure, label_decision = fit_text(
                label,
                max_width=card.width - 40,
                max_height=100,
                initial_size=theme.body_font_size,
                min_size=26,
                max_lines=2,
                theme=theme,
            )
            if label_decision:
                decisions.append(f"对比标签 {index + 1}：{label_decision}")
            elements.append(ElementLayout(
                f"label_{index}", "text", label,
                Box(card.x + 20, card.y + 20, card.width - 40, label_measure.height),
                index * 140, content.duration_ms, 30, "label",
                label_measure.font_size, label_measure.lines,
                AnimationSpec(enter="drop_bounce", enter_after_ms=index * 140),
            ))
            image = content.images[index] if index < len(content.images) else ""
            if not image:
                warnings.append(f"对比卡片 {index + 1} 没有图片，仅保留文字标签")
                continue
            geometry = asset_geometry(image)
            target = Box(card.x + 20, card.y + 150, card.width - 40, card.height - 190)
            if landscape:
                target = Box(card.x + 20, card.y + 112, card.width - 40, card.height - 136)
            image_box = fit_aspect(geometry.visible_width, geometry.visible_height, target)
            elements.append(ElementLayout(
                f"image_{index}", "image", image, image_box,
                120 + index * 140, content.duration_ms, 10, "compare",
                animation=AnimationSpec(enter="fade_scale", enter_after_ms=120 + index * 140),
                metadata=image_metadata(geometry),
            ))

        if overlaps(cards[0], cards[1], gap=0):
            warnings.append("对比卡片发生重叠")
        return LayoutResult(self.name, canvas, elements, warnings, decisions)
