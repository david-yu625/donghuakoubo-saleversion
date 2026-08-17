"""Render layout results to PNG for fast visual review."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from ..core.models import ElementLayout, LayoutResult, Theme
from ..core.text_measure import resolve_font
from ..settings import (
    DEFAULT_KEYWORD_BORDER_COLOR,
    DEFAULT_KEYWORD_TEXT_COLOR,
    default_background_image,
    load_render_settings,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def render_preview(
    result: LayoutResult,
    output: Path,
    *,
    theme: Theme | None = None,
    visual_theme: str = "",
) -> Path:
    settings = load_render_settings(visual_theme)
    theme = theme or Theme(
        subtitle_font=settings.subtitle_font,
        subtitle_color=settings.subtitle_color,
        subtitle_background_color=settings.subtitle_background_color,
    )
    background = default_background_image(PROJECT_ROOT, settings.visual_theme.key)
    if background.exists():
        with Image.open(background) as source:
            image = ImageOps.fit(
                source.convert("RGB"),
                (result.canvas.width, result.canvas.height),
                Image.Resampling.LANCZOS,
            )
    else:
        image = Image.new("RGB", (result.canvas.width, result.canvas.height), theme.panel_color)
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (
            result.canvas.content_left,
            result.canvas.content_top,
            result.canvas.content_right,
            result.canvas.content_bottom,
        ),
        outline="#303641",
        width=2,
    )

    for element in sorted(result.elements, key=lambda item: item.z_index):
        if element.element_type == "image":
            _draw_image(image, draw, element)
        else:
            _draw_text(draw, element, theme)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output


def _draw_image(canvas: Image.Image, draw: ImageDraw.ImageDraw, element: ElementLayout) -> None:
    path = Path(element.content)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    box = element.box
    draw.rounded_rectangle((box.x, box.y, box.right, box.bottom), radius=8, fill="#20242D", outline="#505866", width=2)
    if not path.exists():
        draw.line((box.x, box.y, box.right, box.bottom), fill="#8B94A3", width=3)
        draw.line((box.right, box.y, box.x, box.bottom), fill="#8B94A3", width=3)
        return
    with Image.open(path) as source:
        source = source.convert("RGBA")
        bbox = source.getchannel("A").getbbox()
        if bbox:
            source = source.crop(bbox)
        source.thumbnail((box.width, box.height), Image.Resampling.LANCZOS)
        x = round(box.center_x - source.width / 2)
        y = round(box.center_y - source.height / 2)
        canvas.paste(source, (x, y), source)


def _draw_text(draw: ImageDraw.ImageDraw, element: ElementLayout, theme: Theme) -> None:
    font = resolve_font(theme.font_path, element.font_size or theme.body_font_size)
    text = "\n".join(element.lines) if element.lines else element.content
    fill = str(element.metadata.get("text_color", theme.text_color if element.role != "subtitle" else theme.muted_color))
    box = element.box
    line_spacing = round((element.font_size or theme.body_font_size) * (theme.line_height - 1))
    text_box = draw.multiline_textbbox((0, 0), text, font=font, spacing=line_spacing, align="center")
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    x = box.center_x - text_width / 2
    y = box.center_y - text_height / 2 - text_box[1]
    if element.role in {"label", "number"}:
        fill = str(element.metadata.get("text_color", DEFAULT_KEYWORD_TEXT_COLOR))
    if element.role == "subtitle":
        padding_x = 24
        padding_y = 12
        draw.rectangle(
            (x - padding_x, y + text_box[1] - padding_y, x + text_width + padding_x, y + text_box[3] + padding_y),
            fill=str(element.metadata.get("subtitle_background_color", theme.subtitle_background_color)),
        )
        fill = str(element.metadata.get("text_color", theme.subtitle_color))
    stroke_width = 3 if element.role == "title" else 3 if element.role in {"label", "number"} else 0
    draw.multiline_text(
        (x, y),
        text,
        font=font,
        fill=fill,
        spacing=line_spacing,
        align="center",
        stroke_width=stroke_width,
        stroke_fill=DEFAULT_KEYWORD_BORDER_COLOR if element.role in {"label", "number"} else "#1D1712",
    )
