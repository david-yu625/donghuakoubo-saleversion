from __future__ import annotations

from typing import Any

from ..contracts import validate_layout, validate_scene_facts


def layout_world(facts: dict[str, Any], canvas: tuple[int, int] = (1920, 1080)) -> dict[str, Any]:
    validate_scene_facts(facts)
    width, height = canvas
    columns = 3
    x_step, y_step = 3000, 2300
    center_x, center_y = 4600, 2050
    placements = []
    for index, shot in enumerate(facts["shots"]):
        row, column = divmod(index, columns)
        visual_column = column if row % 2 == 0 else columns - 1 - column
        placements.append({
            "shot_id": shot["id"],
            "x": center_x + (visual_column - 1) * x_step,
            "y": center_y + row * y_step,
            "width": 1240,
            "height": 698,
        })
    return validate_layout({
        "canvas": {"width": width, "height": height},
        "viewport": {"width": 1920, "height": 704, "headerHeight": 192},
        "world": {"width": 11000, "height": 6800},
        "infiniteCanvas": True,
        "subtitle_safe_area": {"left": 160, "right": 160, "bottom": 42},
        "shots": placements,
    }, [shot["id"] for shot in facts["shots"]])
