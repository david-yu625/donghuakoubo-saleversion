"""The isolated Remotion copy of Jianying's image style contract."""

from __future__ import annotations

from typing import Any

from ..contracts import VISUAL_STYLE_ID


STYLE_PROMPT = (
    "Copy the exact Jianying white-board explainer illustration language. "
    "Use a pure #FFFFFF paper canvas and a hand-drawn marker look: bold black "
    "outlines with visibly uneven, slightly wobbly strokes, rounded corners, "
    "simple flat marker fills, and small hand-drawn arrows, dots, underlines or "
    "circles when they clarify the relationship. The result must look like a "
    "clean Excalidraw-style teaching board made with a black felt-tip pen, not "
    "a polished vector illustration, 3D render, glossy icon set, watercolor or "
    "photograph. Use the Jianying accent colors sparingly: cobalt blue, teal, "
    "yellow, orange and occasional purple or green; black remains the dominant "
    "structural line color. Keep large areas of untouched white space and a "
    "clear left-to-right or top-to-bottom explanation. Make one composite scene "
    "with only the concrete objects needed to explain the claim, connected by "
    "simple hand-drawn lines or arrows. A single irregular marker outline is "
    "allowed around an object group, but never a glossy UI card, drop shadow or "
    "decorative border. Do not render the word Excalidraw. Do not render long "
    "titles, subtitles, paragraphs, logos, watermarks, browser chrome or tiny "
    "decorative detail; the video renderer adds text separately."
)


def build_image_prompt(shot: dict[str, Any]) -> str:
    visual = shot.get("visual") or shot.get("title", "")
    elements = shot.get("storyboard_elements") or [visual]
    element_text = "; ".join(str(item) for item in elements)
    summary = shot.get("background_summary", "")
    return (
        f"Create one 16:9 illustration for a Chinese educational short video. "
        f"Scene claim: {shot.get('title', '')}. Short board summary: {summary}. Visual content: {visual}. "
        f"Concrete element content: {element_text}. "
        f"{STYLE_PROMPT} Keep the main drawing centered with generous margins; "
        "the video renderer will add titles, keywords and subtitles separately."
    )
