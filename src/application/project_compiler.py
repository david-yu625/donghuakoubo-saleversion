"""Compile prepared project files through the visual layout pipeline."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
import unicodedata

from ..core.models import AnimationSpec, Box, ElementLayout, LayoutResult, SceneContent, Theme, canvas_for_orientation
from ..core.text_measure import fit_text
from ..layouts.engine import LayoutEngine
from ..layouts.regions import subtitle_area
from ..pipeline import build_scene_facts, load_project
from ..settings import load_render_settings
from ..visual_direction.apply import apply_visual_plan
from ..visual_direction.director import VisualDirector
from ..visual_direction.sound_design import apply_sound_design
from ..core.models import SceneFacts


STRONG_SUBTITLE_PUNCTUATION = "。！？!?"
WEAK_SUBTITLE_PUNCTUATION = "，,；;：:、—"
SEMANTIC_BREAK_BEFORE = (
    "但是", "可是", "不过", "然而", "于是", "然后", "所以", "因此",
    "如果", "要是", "只要", "结果", "其实", "同时", "另外", "接着",
    "最后", "反而", "还给", "拿到", "换成", "变成", "导致", "说明",
    "意味着", "赚到", "亏掉", "等到", "先", "再", "又", "但", "却",
)
ACTION_BREAK_BEFORE = (
    "还给", "拿到", "买回", "卖掉", "借来", "赚到", "亏掉", "涨到",
    "跌到", "换来", "换成", "变成",
)
SEMANTIC_BREAK_AFTER = ("以后", "之后", "后来", "当时", "这时", "目前", "后")
LANDSCAPE_SUBTITLE_FONT_SIZE = 32
LANDSCAPE_SUBTITLE_MIN_SIZE = 26


def compile_project(
    project_dir: Path,
    *,
    project_title: str = "",
    visual_theme: str = "",
    orientation: str = "",
    include_subtitles: bool | None = None,
) -> LayoutResult:
    source = load_project(project_dir)
    settings = load_render_settings(visual_theme)
    scenes = build_scene_facts(source)
    director = VisualDirector()
    engine = LayoutEngine(theme=Theme(
        subtitle_font=settings.subtitle_font,
        subtitle_color=settings.subtitle_color,
        subtitle_background_color=settings.subtitle_background_color,
    ), canvas=canvas_for_orientation(orientation))
    if include_subtitles is None:
        include_subtitles = engine.canvas.width <= engine.canvas.height
    rendered: list[tuple[PreparedScene, LayoutResult]] = []
    previous_keyword_color = ""
    for scene in scenes:
        plan = director.plan(scene)
        plan = replace(
            plan,
            typography=replace(
                plan.typography,
                title_font=settings.title_font,
                subtitle_font=settings.subtitle_font,
            ),
        )
        layout = engine.build(plan.layout.template, SceneContent.from_facts(scene))
        styled = apply_visual_plan(layout, plan, previous_keyword_color=previous_keyword_color)
        scene_keyword_colors = [
            str(element.metadata.get("text_color", ""))
            for element in styled.elements
            if element.element_type == "text" and element.role in {"label", "number"}
        ]
        if scene_keyword_colors:
            previous_keyword_color = scene_keyword_colors[-1]
        rendered.append((scene, styled))

    result = apply_sound_design(merge_scenes(rendered, engine))
    if include_subtitles:
        result.elements.extend(build_subtitle_elements(
            without_opening_title_subtitle(source.subtitle_rows, project_title),
            engine,
        ))
    result.elements.sort(key=lambda item: (item.z_index, item.start_ms, item.element_id))
    if project_title:
        result.decisions.insert(0, f"项目标题：{project_title}")
    return result


def without_opening_title_subtitle(
    rows: list[tuple[str, int, int]],
    project_title: str = "",
) -> list[tuple[str, int, int]]:
    """Drop a zero-based opening row only when it is actually the project title."""
    normalized_title = normalize_subtitle_identity(project_title)
    if (
        rows
        and rows[0][1] == 0
        and normalized_title
        and normalize_subtitle_identity(rows[0][0]) == normalized_title
    ):
        return rows[1:]
    return rows


def normalize_subtitle_identity(text: str) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text).casefold()

def merge_scenes(
    scenes: list[tuple[SceneFacts, LayoutResult]],
    engine: LayoutEngine,
) -> LayoutResult:
    elements: list[ElementLayout] = []
    warnings: list[str] = []
    decisions: list[str] = []
    for scene, result in scenes:
        for element in result.elements:
            elements.append(replace(
                element,
                element_id=f"{scene.scene_id}_{element.element_id}",
                start_ms=scene.start_ms + element.start_ms,
                end_ms=scene.start_ms + element.end_ms,
            ))
        warnings.extend(f"{scene.scene_id}: {warning}" for warning in result.warnings)
        decisions.extend(f"{scene.scene_id}: {decision}" for decision in result.decisions)
    return LayoutResult(
        template="project_sequence",
        canvas=engine.canvas,
        elements=elements,
        warnings=warnings,
        decisions=decisions,
    )


def build_subtitle_elements(
    rows: list[tuple[str, int, int]],
    engine: LayoutEngine,
    *,
    box: Box | None = None,
) -> list[ElementLayout]:
    elements: list[ElementLayout] = []
    canvas = engine.canvas
    theme = engine.theme
    landscape = canvas.width > canvas.height
    subtitle_box = box or subtitle_area(canvas)
    subtitle_center_y = subtitle_box.center_y
    box = subtitle_box
    for index, (text, start_ms, end_ms) in enumerate(rows):
        chunks = split_subtitle_text(text, max_chars=24 if landscape else 14)
        timings = distribute_subtitle_timing(chunks, start_ms, end_ms)
        for chunk_index, (chunk, (chunk_start_ms, chunk_end_ms)) in enumerate(zip(chunks, timings)):
            measured, decision = fit_text(
                chunk,
                max_width=box.width,
                max_height=box.height,
                initial_size=LANDSCAPE_SUBTITLE_FONT_SIZE if landscape else theme.subtitle_font_size,
                min_size=LANDSCAPE_SUBTITLE_MIN_SIZE if landscape else 40,
                max_lines=1,
                theme=theme,
            )
            metadata = {
                "font_name": theme.subtitle_font,
                "text_color": theme.subtitle_color,
                "subtitle_background_color": theme.subtitle_background_color,
                "text_intro": "渐显",
                "text_outro": "渐隐",
                "source_subtitle": text,
                "semantic_chunk_index": chunk_index,
                "semantic_chunk_count": len(chunks),
            }
            if decision:
                metadata["subtitle_decision"] = decision
            elements.append(ElementLayout(
                element_id=f"subtitle_{index:04d}_{chunk_index:02d}",
                element_type="text",
                content=chunk,
                box=Box(box.x, round(subtitle_center_y - measured.height / 2), box.width, measured.height),
                start_ms=chunk_start_ms,
                end_ms=chunk_end_ms,
                z_index=1000,
                role="subtitle",
                font_size=measured.font_size,
                lines=measured.lines,
                animation=AnimationSpec(enter="fade_in", enter_duration_ms=180),
                metadata=metadata,
            ))
    return elements


def split_subtitle_text(text: str, max_chars: int = 14) -> list[str]:
    if max_chars <= 0:
        raise ValueError("字幕单行字数必须大于零")
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    clauses: list[str] = []
    current = ""
    for character in normalized:
        if character in WEAK_SUBTITLE_PUNCTUATION:
            _append_subtitle_chunk(clauses, current)
            current = ""
        elif character in STRONG_SUBTITLE_PUNCTUATION:
            current += character
            _append_subtitle_chunk(clauses, current)
            current = ""
        else:
            current += character
    _append_subtitle_chunk(clauses, current)

    chunks: list[str] = []
    for clause in _merge_tiny_subtitle_clauses(clauses):
        chunks.extend(_split_long_subtitle_clause(clause, max_chars))
    return [cleaned for chunk in chunks if (cleaned := remove_subtitle_punctuation(chunk))]


def distribute_subtitle_timing(
    chunks: list[str],
    start_ms: int,
    end_ms: int,
) -> list[tuple[int, int]]:
    if not chunks:
        return []
    if end_ms - start_ms < len(chunks):
        raise ValueError("字幕时长不足以分配语义短句")

    weights = [max(0.5, subtitle_display_width(_timed_characters(chunk))) for chunk in chunks]
    total_weight = sum(weights)
    duration_ms = end_ms - start_ms
    timings: list[tuple[int, int]] = []
    cursor = start_ms
    cumulative_weight = 0.0
    for index, weight in enumerate(weights):
        if index == len(chunks) - 1:
            chunk_end_ms = end_ms
        else:
            cumulative_weight += weight
            proportional_end = start_ms + round(duration_ms * cumulative_weight / total_weight)
            remaining_chunks = len(chunks) - index - 1
            chunk_end_ms = max(cursor + 1, min(proportional_end, end_ms - remaining_chunks))
        timings.append((cursor, chunk_end_ms))
        cursor = chunk_end_ms
    return timings


def subtitle_display_width(text: str) -> float:
    width = 0.0
    for character in text:
        if character.isspace():
            width += 0.5
        elif unicodedata.east_asian_width(character) in {"W", "F", "A"}:
            width += 1.0
        else:
            width += 0.55
    return width


def remove_subtitle_punctuation(text: str) -> str:
    return "".join(
        character
        for character in text
        if not unicodedata.category(character).startswith("P")
    ).strip()


def _append_subtitle_chunk(chunks: list[str], text: str) -> None:
    chunk = text.strip().strip(WEAK_SUBTITLE_PUNCTUATION).strip()
    if chunk:
        chunks.append(chunk)


def _merge_tiny_subtitle_clauses(clauses: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(clauses):
        clause = clauses[index]
        if subtitle_display_width(clause) < 4 and index + 1 < len(clauses):
            merged.append(clause + clauses[index + 1])
            index += 2
        elif subtitle_display_width(clause) < 4 and merged:
            merged[-1] += clause
            index += 1
        else:
            merged.append(clause)
            index += 1
    return merged


def _split_long_subtitle_clause(text: str, max_chars: int) -> list[str]:
    remaining = text.strip()
    chunks: list[str] = []
    while subtitle_display_width(remaining) > max_chars:
        split_at = _semantic_split_position(remaining, max_chars)
        if split_at is None:
            split_at = _balanced_split_position(remaining, max_chars)
        left = remaining[:split_at].strip().strip(WEAK_SUBTITLE_PUNCTUATION).strip()
        right = remaining[split_at:].strip().strip(WEAK_SUBTITLE_PUNCTUATION).strip()
        if not left or not right:
            break
        chunks.append(left)
        remaining = right
    if remaining:
        chunks.append(remaining)
    return chunks


def _semantic_split_position(text: str, max_chars: int) -> int | None:
    break_groups = (
        {
            index + len(token)
            for token in SEMANTIC_BREAK_AFTER
            for index in _token_positions(text, token)
        },
        {
            index
            for token in SEMANTIC_BREAK_BEFORE
            for index in _token_positions(text, token)
        },
        {
            index
            for token in ACTION_BREAK_BEFORE
            for index in _token_positions(text, token)
        },
    )
    for raw_positions in break_groups:
        positions = {
            index
            for index in raw_positions
            if index > 0
            and subtitle_display_width(text[:index]) <= max_chars
            and subtitle_display_width(text[:index]) >= 4
        }
        if positions:
            return max(positions, key=lambda index: subtitle_display_width(text[:index]))
    return None


def _token_positions(text: str, token: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        index = text.find(token, start)
        if index < 0:
            return positions
        positions.append(index)
        start = index + len(token)


def _balanced_split_position(text: str, max_chars: int) -> int:
    total_width = subtitle_display_width(text)
    target_width = max_chars if total_width > max_chars * 2 else total_width / 2
    width = 0.0
    for index, character in enumerate(text, start=1):
        next_width = width + subtitle_display_width(character)
        if next_width > target_width and index > 1:
            return index - 1
        width = next_width
    return max(1, len(text) - 1)


def _timed_characters(text: str) -> str:
    punctuation = STRONG_SUBTITLE_PUNCTUATION + WEAK_SUBTITLE_PUNCTUATION + "…（）()《》“”‘’"
    return text.translate(str.maketrans("", "", punctuation)).replace(" ", "")
