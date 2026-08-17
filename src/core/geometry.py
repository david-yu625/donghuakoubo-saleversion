"""Geometry helpers used by layout templates."""

from __future__ import annotations

from .models import Box, Canvas


def overlaps(first: Box, second: Box, gap: int = 0) -> bool:
    return not (
        first.right + gap <= second.x
        or second.right + gap <= first.x
        or first.bottom + gap <= second.y
        or second.bottom + gap <= first.y
    )


def inside(box: Box, canvas: Canvas) -> bool:
    return (
        box.x >= canvas.content_left
        and box.y >= canvas.content_top
        and box.right <= canvas.content_right
        and box.bottom <= canvas.content_bottom
    )


def clamp_box(box: Box, canvas: Canvas) -> Box:
    x = max(canvas.content_left, min(box.x, canvas.content_right - box.width))
    y = max(canvas.content_top, min(box.y, canvas.content_bottom - box.height))
    return Box(x, y, box.width, box.height)


def fit_aspect(source_width: int, source_height: int, target: Box) -> Box:
    if source_width <= 0 or source_height <= 0:
        return target
    scale = min(target.width / source_width, target.height / source_height)
    width = max(1, round(source_width * scale))
    height = max(1, round(source_height * scale))
    return Box(
        round(target.center_x - width / 2),
        round(target.center_y - height / 2),
        width,
        height,
    )


def normalized_center(box: Box, canvas: Canvas) -> tuple[float, float]:
    x = (box.center_x - canvas.width / 2) / (canvas.width / 2)
    y = (canvas.height / 2 - box.center_y) / (canvas.height / 2)
    return round(x, 5), round(y, 5)
