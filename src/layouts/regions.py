"""Shared pixel regions for the composition layout."""

from __future__ import annotations

from ..core.models import Box, Canvas


LANDSCAPE_SUBTITLE_BOX_HEIGHT = 62
LANDSCAPE_SUBTITLE_BOTTOM_GAP = 32


def visual_stage(canvas: Canvas) -> Box:
    """Return the area available to scene imagery and scene labels."""
    return Box(
        canvas.content_left,
        canvas.content_top,
        canvas.content_right - canvas.content_left,
        canvas.content_bottom - canvas.content_top,
    )


def subtitle_area(canvas: Canvas) -> Box:
    """Keep narration subtitles below the visual stage without touching the edge."""
    if canvas.width > canvas.height:
        height = LANDSCAPE_SUBTITLE_BOX_HEIGHT
        center_y = canvas.height - LANDSCAPE_SUBTITLE_BOTTOM_GAP - height // 2
    else:
        height = max(92, min(160, round(canvas.height * 0.083)))
        height += height % 2
        center_y = canvas.content_bottom + round(54 * canvas.height / 1920)
    return Box(
        canvas.content_left,
        round(center_y - height / 2),
        canvas.content_right - canvas.content_left,
        height,
    )
