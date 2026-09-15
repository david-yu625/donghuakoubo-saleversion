"""Build coordinate-free scene facts from prepared project rows."""

from __future__ import annotations

from pathlib import Path
import re

from ..core.models import SceneElement, SceneFacts
from .project_reader import ProjectSource


def build_scene_facts(source: ProjectSource) -> list[SceneFacts]:
    rows_by_shot: dict[str, list[dict[str, str]]] = {}
    for row in source.element_rows:
        rows_by_shot.setdefault(row.get("shot_id", ""), []).append(row)

    scenes: list[SceneFacts] = []
    for index, shot in enumerate(source.shot_rows):
        shot_id = shot.get("shot_id", str(index + 1)).strip()
        start_ms = parse_time(shot, "开始时间ms")
        end_ms = parse_time(shot, "结束时间ms")
        if end_ms <= start_ms:
            raise ValueError(f"Shot {shot_id} 结束时间必须晚于开始时间")

        rows = rows_by_shot.get(shot_id, [])
        elements = tuple(build_element(row, start_ms, end_ms, shot_id) for row in rows)
        source_text = shot.get("分镜对应原始文案内容", "").strip()
        title = shot.get("分镜标题", "").strip()
        scenes.append(SceneFacts(
            scene_id=f"scene_{int(shot_id):03d}" if shot_id.isdigit() else f"scene_{index:03d}",
            scene_index=index,
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=end_ms - start_ms,
            title=title,
            source_text=source_text,
            elements=elements,
            semantic_role=infer_semantic_role(index, source_text, elements),
        ))
    return scenes


def build_element(row: dict[str, str], scene_start_ms: int, scene_end_ms: int, shot_id: str) -> SceneElement:
    start_ms = int(row.get("start_ms", "0") or 0)
    end_ms = int(row.get("end_ms", "0") or 0)
    if start_ms < scene_start_ms or end_ms > scene_end_ms:
        raise ValueError(
            f"Shot {shot_id} 元素 {row.get('element_id', '')} 超出范围："
            f"{start_ms}-{end_ms} 不在 {scene_start_ms}-{scene_end_ms}"
        )
    if end_ms <= start_ms:
        raise ValueError(f"Shot {shot_id} 元素 {row.get('element_id', '')} 时间无效")
    kind = row.get("type", "").strip()
    source_content = row.get("content", "").strip()
    content = row.get("asset_path", "").strip() if kind == "image" else source_content
    if kind == "image" and (not content or not Path(content).exists()):
        missing = content or source_content
        raise FileNotFoundError(
            f"Shot {shot_id} 图片素材不存在：{missing}。"
            f"请先运行第06步（生成图片）补齐素材，再执行第07步。"
        )
    return SceneElement(
        element_id=row.get("element_id", "").strip(),
        element_type=kind,
        content=content,
        start_ms=start_ms - scene_start_ms,
        end_ms=end_ms - scene_start_ms,
        source_content=source_content,
        role=(row.get("role") or "").strip() or element_role(row.get("element_id", ""), kind),
    )


def element_role(element_id: str, element_type: str) -> str:
    if element_type != "image":
        return ""
    if re.search(r"_bg\d+$", element_id.strip(), re.IGNORECASE):
        return "background"
    if re.search(r"_img\d+$", element_id.strip(), re.IGNORECASE):
        return "overlay"
    return ""


def parse_time(row: dict[str, str], field: str) -> int:
    value = (row.get(field) or "").strip()
    if not value.isdigit():
        raise ValueError(f"Shot {row.get('shot_id', '')} {field} 不是整数：{value}")
    return int(value)


def infer_semantic_role(index: int, source_text: str, elements: tuple[SceneElement, ...]) -> str:
    has_background = any(element.role == "background" for element in elements)
    has_board_elements = any(element.role == "element" for element in elements)
    if has_background and has_board_elements:
        return "board_progressive"
    if index == 0:
        return "overview"
    if any(element.role in {"major_title", "subpoint_label"} for element in elements):
        return "board_section"
    labels = " ".join(element.content for element in elements if element.element_type == "text")
    if re.search(r"\d+[\.．]\d+", labels):
        return "board_section"
    combined = f"{source_text} {labels}"
    if any(marker in combined for marker in ("风险", "亏损", "反而", "损失")):
        return "risk"
    if any(marker in combined for marker in ("流程", "步骤", "先借", "再买", "等跌")):
        return "process"
    if any(marker in combined for marker in ("对比", "之前", "之后", "一边", "另一边", "分别")):
        return "compare"
    starts = {element.start_ms for element in elements}
    if len(starts) > 1:
        return "sequence"
    return "explain"
