"""Adapter from neutral layout results to pyJianYingDraft."""

from __future__ import annotations

import sys
import random
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat

from ..core.geometry import normalized_center
from ..core.models import Box, ElementLayout, LayoutResult, Theme
from ..core.text_measure import resolve_font, text_width
from ..settings import (
    DEFAULT_KEYWORD_BORDER_COLOR,
    DEFAULT_KEYWORD_BORDER_WIDTH,
    DEFAULT_KEYWORD_FONT,
    DEFAULT_KEYWORD_TEXT_COLOR,
    DEFAULT_TITLE_BACKGROUND_COLOR,
    DEFAULT_TITLE_COLOR,
    DEFAULT_TITLE_FONT,
)
from .sound_effects import (
    CUE_MAX_DURATION_MS,
    CUE_VOLUME,
    choose_sound_asset,
    collect_sound_events,
    load_sound_library,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENDORED_REPO = PROJECT_ROOT / "vendor" / "pyJianYingDraft"
if str(VENDORED_REPO) not in sys.path:
    sys.path.insert(0, str(VENDORED_REPO))

import pyJianYingDraft as draft  # noqa: E402


TEXT_STYLE_SCALE = {
    "title": 1 / 5.5,
    "label": 1 / 5.5,
    "number": 1 / 5.5,
    "subtitle": 1 / 6.25,
}
FINAL_HOLD_MS = 800
TEXT_STYLE_MINIMUM = {
    "title": 7.0,
    "label": 6.0,
    "number": 7.0,
    "subtitle": 6.4,
}
IMAGE_SCALE_MULTIPLIER = 1.10
OVERLAY_IMAGE_SCALE_MULTIPLIER = 1.0
NARRATION_SUBTITLE_TRACK = "narration_subtitles"
SCENE_BACKGROUND_TRACK = "scene_backgrounds"
BACKGROUND_MUSIC_VOLUME = 0.16
BACKGROUND_TRACK_RELATIVE_INDEX = -100
SCENE_TRANSITION_DURATION_MS = 900
COVER_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# Subtle, free transitions suited to a whiteboard sequence. Resource ids are
# stable even when the vendored enum source is decoded with a different locale.
class SceneTransitionEffect(str, Enum):
    DISSOLVE = "6724845717472416269"
    BLUR = "6911569618171597320"
    HORIZONTAL_BLUR = "7450031573958660645"
    VERTICAL_BLUR = "7125661387568714247"


SCENE_TRANSITION_RESOURCE_IDS = tuple(effect.value for effect in SceneTransitionEffect)
BANNED_FONT_NAMES = {
    "\u7ad9\u9177\u9177\u9ed1\u4f53",
    "\u53e4\u5370\u5b8b\u7b80",
}


def parse_hex_color(value: str) -> tuple[float, float, float]:
    raw = value.lstrip("#")
    if len(raw) != 6:
        return 1.0, 1.0, 1.0
    return tuple(int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4))


def _image_richness(path: Path) -> float:
    """Estimate visual information so plain background plates are not chosen."""
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((96, 96), Image.Resampling.BILINEAR)
            if image.width < 2 or image.height < 2:
                return 0.0
            channel_variation = sum(ImageStat.Stat(image).stddev) / 3.0
            gray = image.convert("L")
            width, height = gray.size
            horizontal = ImageChops.difference(
                gray.crop((1, 0, width, height)),
                gray.crop((0, 0, width - 1, height)),
            )
            vertical = ImageChops.difference(
                gray.crop((0, 1, width, height)),
                gray.crop((0, 0, width, height - 1)),
            )
            edge_variation = (
                ImageStat.Stat(horizontal).mean[0]
                + ImageStat.Stat(vertical).mean[0]
            ) / 2.0
            return channel_variation + edge_variation * 2.0
    except (OSError, ValueError):
        return 0.0


def select_cover_image(result: LayoutResult, project_root: Path) -> Path | None:
    """Select the most visually information-dense image in a layout."""
    candidate_roles: dict[Path, bool] = {}
    for element in result.elements:
        if element.element_type != "image":
            continue
        path = Path(element.content).expanduser()
        if not path.is_absolute():
            path = project_root / path
        path = path.resolve()
        if path.suffix.lower() not in COVER_IMAGE_EXTENSIONS or not path.is_file():
            continue
        candidate_roles[path] = candidate_roles.get(path, False) or element.role != "background"
    candidates = [
        (_image_richness(path), path, is_foreground)
        for path, is_foreground in candidate_roles.items()
    ]
    if not candidates:
        return None
    foreground = [item for item in candidates if item[2]]
    return max(foreground or candidates, key=lambda item: item[0])[1]


def text_style_size(font_size: int, role: str) -> float:
    scale = TEXT_STYLE_SCALE.get(role, 1 / 8)
    minimum = TEXT_STYLE_MINIMUM.get(role, 4.5)
    return round(max(minimum, font_size * scale), 2)


def cached_font_path(font_type) -> str | None:
    metadata = font_type.value
    directory = (
        Path.home()
        / "AppData"
        / "Local"
        / "JianyingPro"
        / "User Data"
        / "Cache"
        / "effect"
        / metadata.effect_id
        / metadata.md5
    )
    if not directory.is_dir():
        return None
    return str(next((path for path in directory.iterdir() if path.suffix.lower() in {".ttf", ".otf", ".ttc"}), "")) or None


def image_scale(element: ElementLayout, result: LayoutResult) -> float:
    return image_transform(element, result)[2]


def image_scale_multiplier(element: ElementLayout) -> float:
    """Keep full-frame background plates and cropped overlays at their layout scale."""
    return (
        OVERLAY_IMAGE_SCALE_MULTIPLIER
        if element.role in {"background", "overlay"}
        else IMAGE_SCALE_MULTIPLIER
    )


def image_transform(element: ElementLayout, result: LayoutResult) -> tuple[float, float, float]:
    source = element.metadata.get("source_size", [element.box.width, element.box.height])
    source_width, source_height = int(source[0]), int(source[1])
    source_width = max(1, source_width)
    source_height = max(1, source_height)
    raw_bbox = element.metadata.get("source_bbox", [0, 0, source_width, source_height])
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        raw_bbox = [0, 0, source_width, source_height]
    left, top, right, bottom = (int(value) for value in raw_bbox)
    visible_width = max(1, right - left)
    visible_height = max(1, bottom - top)
    pixel_scale = min(element.box.width / visible_width, element.box.height / visible_height)
    base_scale = min(result.canvas.width / source_width, result.canvas.height / source_height)
    target_scale = pixel_scale / base_scale * image_scale_multiplier(element)
    visible_center_x = (left + right) / 2
    visible_center_y = (top + bottom) / 2
    source_center_x = element.box.center_x - (visible_center_x - source_width / 2) * pixel_scale
    source_center_y = element.box.center_y - (visible_center_y - source_height / 2) * pixel_scale
    x = (source_center_x - result.canvas.width / 2) / (result.canvas.width / 2)
    y = (result.canvas.height / 2 - source_center_y) / (result.canvas.height / 2)
    return round(x, 5), round(y, 5), target_scale


def add_enter_keyframes(segment, element: ElementLayout, result: LayoutResult, target_scale: float) -> None:
    x, y = (
        image_transform(element, result)[:2]
        if element.element_type == "image"
        else normalized_center(element.box, result.canvas)
    )
    duration_ms = min(element.animation.enter_duration_ms, max(1, element.end_ms - element.start_ms - 34))
    duration = f"{duration_ms / 1000:.3f}s"
    style = element.animation.enter
    start_x, start_y, start_scale = x, y, target_scale

    if style == "slide_up":
        start_y = y - 0.10
    elif style == "slide_left":
        start_x = x + 0.16
    elif style == "drop_bounce":
        start_y = y + 0.14
        start_scale = target_scale * 0.92
    elif style in {"fade_scale", "scale_in"}:
        start_scale = target_scale * 0.86

    segment.add_keyframe(draft.KeyframeProperty.position_x, "0s", start_x)
    segment.add_keyframe(draft.KeyframeProperty.position_x, duration, x)
    segment.add_keyframe(draft.KeyframeProperty.position_y, "0s", start_y)
    segment.add_keyframe(draft.KeyframeProperty.position_y, duration, y)
    segment.add_keyframe(draft.KeyframeProperty.uniform_scale, "0s", max(0.01, start_scale))
    segment.add_keyframe(draft.KeyframeProperty.uniform_scale, duration, target_scale)
    if element.element_type == "image" and style in {"fade_in", "fade_scale", "scale_in"}:
        segment.add_keyframe(draft.KeyframeProperty.alpha, "0s", 0.0)
        segment.add_keyframe(draft.KeyframeProperty.alpha, duration, 1.0)


def add_layout_keyframes(segment, element: ElementLayout, result: LayoutResult) -> None:
    raw_keyframes = element.metadata.get("layout_keyframes", [])
    if not isinstance(raw_keyframes, list) or not raw_keyframes:
        return
    previous_box = element.box
    previous_scale = image_scale(replace_box(element, previous_box), result)
    for raw in raw_keyframes:
        if not isinstance(raw, dict):
            continue
        raw_box = raw.get("box")
        if not isinstance(raw_box, list) or len(raw_box) != 4:
            continue
        offset_ms = int(raw.get("offset_ms", 0))
        target_box = Box(*(int(value) for value in raw_box))
        target_element = replace_box(element, target_box)
        target_x, target_y, target_scale = image_transform(target_element, result)
        hold_ms = max(element.animation.enter_duration_ms, offset_ms - 180)
        end_ms = min(element.end_ms - element.start_ms - 34, offset_ms + 260)
        if end_ms <= hold_ms:
            previous_box = target_box
            previous_scale = target_scale
            continue
        previous_x, previous_y, _ = image_transform(replace_box(element, previous_box), result)
        hold = f"{hold_ms / 1000:.3f}s"
        end = f"{end_ms / 1000:.3f}s"
        segment.add_keyframe(draft.KeyframeProperty.position_x, hold, previous_x)
        segment.add_keyframe(draft.KeyframeProperty.position_y, hold, previous_y)
        segment.add_keyframe(draft.KeyframeProperty.uniform_scale, hold, previous_scale)
        segment.add_keyframe(draft.KeyframeProperty.position_x, end, target_x)
        segment.add_keyframe(draft.KeyframeProperty.position_y, end, target_y)
        segment.add_keyframe(draft.KeyframeProperty.uniform_scale, end, target_scale)
        previous_box = target_box
        previous_scale = target_scale


def add_hold_motion(segment, element: ElementLayout, result: LayoutResult) -> None:
    duration_ms = element.end_ms - element.start_ms
    if duration_ms < 900:
        return
    x, y, scale = image_transform(element, result)
    start_ms = min(max(element.animation.enter_duration_ms, 320), duration_ms - 200)
    end_ms = duration_ms - 34
    if end_ms <= start_ms:
        return
    end_x, end_y, end_scale = x, y, scale
    motion = str(element.metadata.get("hold_motion", "drift"))
    if motion == "static":
        return
    if motion == "push_in":
        end_scale = scale * 1.07
    elif motion == "pull_out":
        end_scale = scale * 0.95
    elif motion == "pan":
        end_x = x + 0.045
        end_scale = scale * 1.025
    else:
        end_y = y + 0.012
        end_scale = scale * 1.025
    start = f"{start_ms / 1000:.3f}s"
    end = f"{end_ms / 1000:.3f}s"
    segment.add_keyframe(draft.KeyframeProperty.position_x, start, x)
    segment.add_keyframe(draft.KeyframeProperty.position_x, end, end_x)
    segment.add_keyframe(draft.KeyframeProperty.position_y, start, y)
    segment.add_keyframe(draft.KeyframeProperty.position_y, end, end_y)
    segment.add_keyframe(draft.KeyframeProperty.uniform_scale, start, scale)
    segment.add_keyframe(draft.KeyframeProperty.uniform_scale, end, end_scale)


def replace_box(element: ElementLayout, box: Box) -> ElementLayout:
    return ElementLayout(
        element_id=element.element_id,
        element_type=element.element_type,
        content=element.content,
        box=box,
        start_ms=element.start_ms,
        end_ms=element.end_ms,
        z_index=element.z_index,
        role=element.role,
        font_size=element.font_size,
        lines=element.lines,
        animation=element.animation,
        metadata=element.metadata,
    )


def stabilize_final_element(
    element: ElementLayout,
    *,
    content_end_ms: int,
    final_end_ms: int,
) -> ElementLayout:
    if element.end_ms != content_end_ms:
        return element
    metadata = dict(element.metadata)
    metadata.pop("text_outro", None)
    metadata.pop("video_outro", None)
    metadata.pop("text_loop", None)
    return replace(element, end_ms=final_end_ms, metadata=metadata)


def enum_member(enum_type, name: str):
    if not name:
        return None
    member = getattr(enum_type, name, None)
    if member is not None:
        return member
    # Some Jianying display names contain spaces while their Python enum keys
    # use underscores, for example "冲刺 II" -> "冲刺_II".
    return getattr(enum_type, name.replace(" ", "_"), None)


def transition_member_by_resource_id(resource_id: str):
    return next(
        (
            member
            for member in draft.TransitionType
            if str(member.value.resource_id) == resource_id and not member.value.is_vip
        ),
        None,
    )


def scene_transition_for_index(index: int, *, randomize: bool = False, previous_resource_id: str = ""):
    if randomize:
        candidates = [resource_id for resource_id in SCENE_TRANSITION_RESOURCE_IDS if resource_id != previous_resource_id]
        resource_id = random.SystemRandom().choice(candidates or list(SCENE_TRANSITION_RESOURCE_IDS))
    else:
        resource_id = SCENE_TRANSITION_RESOURCE_IDS[index % len(SCENE_TRANSITION_RESOURCE_IDS)]
    transition = transition_member_by_resource_id(resource_id)
    if transition is None:
        raise RuntimeError(f"missing Jianying scene transition resource: {resource_id}")
    return transition


def normalize_scene_backgrounds(
    elements: list[ElementLayout],
    *,
    content_end_ms: int,
    final_end_ms: int,
) -> list[ElementLayout]:
    """Make scene plates adjacent so Jianying can place native transitions."""
    backgrounds = sorted(
        (element for element in elements if element.role == "background"),
        key=lambda element: (element.start_ms, element.element_id),
    )
    normalized: list[ElementLayout] = []
    for index, element in enumerate(backgrounds):
        next_start_ms = backgrounds[index + 1].start_ms if index + 1 < len(backgrounds) else None
        end_ms = next_start_ms if next_start_ms is not None else element.end_ms
        if next_start_ms is None and element.end_ms == content_end_ms:
            end_ms = final_end_ms
        metadata = dict(element.metadata)
        if index > 0:
            # Native transitions already introduce later scene plates. Keeping
            # the old per-image intro here would apply two effects at once.
            metadata.pop("video_intro", None)
            metadata.pop("scene_transition", None)
        normalized.append(replace(element, end_ms=max(element.start_ms + 34, end_ms), metadata=metadata))
    return normalized


def fitted_animation_duration(
    animation_type,
    requested_ms: int,
    total_ms: int,
    *,
    max_fraction: float,
    cap_ms: int,
) -> int:
    default_ms = animation_type.value.duration // 1000
    preferred_ms = max(requested_ms, min(default_ms, cap_ms))
    return max(100, min(preferred_ms, round(total_ms * max_fraction)))


def apply_text_animations(segment, element: ElementLayout) -> bool:
    intro = enum_member(draft.TextIntro, str(element.metadata.get("text_intro", "")))
    is_keyword = element.role in {"label", "number"}
    outro = None if is_keyword else enum_member(draft.TextOutro, str(element.metadata.get("text_outro", "")))
    loop = None if is_keyword else enum_member(draft.TextLoopAnim, str(element.metadata.get("text_loop", "")))
    total_ms = element.end_ms - element.start_ms
    applied = False
    if intro is not None:
        intro_ms = fitted_animation_duration(
            intro,
            element.animation.enter_duration_ms,
            total_ms,
            max_fraction=0.45,
            cap_ms=900,
        )
        segment.add_animation(intro, f"{intro_ms / 1000:.3f}s")
        applied = True
    if outro is not None and total_ms >= 500:
        outro_ms = fitted_animation_duration(
            outro,
            element.animation.exit_duration_ms,
            total_ms,
            max_fraction=0.35,
            cap_ms=700,
        )
        segment.add_animation(outro, f"{outro_ms / 1000:.3f}s")
    if loop is not None and total_ms >= 1200:
        segment.add_animation(loop)
    return applied


def apply_video_animations(segment, element: ElementLayout, *, allow_intro: bool = True) -> bool:
    intro = enum_member(draft.IntroType, str(element.metadata.get("video_intro", "")))
    outro = enum_member(draft.OutroType, str(element.metadata.get("video_outro", "")))
    total_ms = element.end_ms - element.start_ms
    applied_intro = False
    if intro is not None and allow_intro:
        intro_ms = fitted_animation_duration(
            intro,
            element.animation.enter_duration_ms,
            total_ms,
            max_fraction=0.45,
            cap_ms=900,
        )
        segment.add_animation(intro, f"{intro_ms / 1000:.3f}s")
        applied_intro = True
    if outro is not None and total_ms >= 650:
        outro_ms = fitted_animation_duration(
            outro,
            element.animation.exit_duration_ms,
            total_ms,
            max_fraction=0.35,
            cap_ms=700,
        )
        segment.add_animation(outro, f"{outro_ms / 1000:.3f}s")
    return applied_intro


def title_transform_y(canvas_width: int, canvas_height: int, center_ratio: float = 0.14) -> float:
    """Convert the renderer-owned title anchor from pixels to Jianying space."""
    del canvas_width
    title_center_y = round(canvas_height * center_ratio)
    return round((canvas_height / 2 - title_center_y) / (canvas_height / 2), 2)


TITLE_Y = title_transform_y(1080, 1920)
TITLE_TEXT_STYLE_SIZE = 17.0
TITLE_FONT_SIZE = round(TITLE_TEXT_STYLE_SIZE * 5.5)
TITLE_BAR_HEIGHT = 180
TITLE_BAR_HORIZONTAL_PADDING = 60
TITLE_BAR_MAX_WIDTH = 936
TITLE_LETTER_SPACING = 5
TITLE_MIN_STYLE_SIZE = 10.0
LANDSCAPE_TITLE_BAR_MIN_WIDTH_RATIO = 0.84
LANDSCAPE_TITLE_STYLE_SCALE = 0.82
LANDSCAPE_TITLE_BAR_HEIGHT_SCALE = 0.82
COMPACT_TITLE_STYLE_SCALE = 0.82
COMPACT_TITLE_STYLE_BOOST = 2.0
COMPACT_TITLE_BAR_HEIGHT = 104
COMPACT_TITLE_LINE_HEIGHT = 6
SUBTITLE_BACKGROUND_WIDTH = 0.24
SUBTITLE_BACKGROUND_HEIGHT = 0.20


@dataclass(frozen=True)
class GlobalTitlePresentation:
    text: str
    style_size: float
    letter_spacing: int
    bar_width: int
    bar_height: int


def _title_line_width(line: str, style_size: float, letter_spacing: int, font_path: str | None) -> int:
    font_size = round(style_size * 5.5)
    font = resolve_font(font_path, font_size)
    spacing_width = round(max(0, len(line) - 1) * font_size * letter_spacing * 0.05)
    return text_width(line, font) + spacing_width


def _title_break_candidates(title: str) -> list[int]:
    candidates = [
        index + 1
        for index, character in enumerate(title[:-1])
        if character in "\uFF1F?!\uFF01\uFF1A:\uFF0C,\uFF1B;"
    ]
    candidates.extend(
        index
        for index in range(1, len(title))
        if not (title[index - 1].isascii() and title[index - 1].isalnum() and title[index].isascii() and title[index].isalnum())
    )
    return sorted(set(candidates))


def _balanced_title_lines(title: str, font_path: str | None) -> tuple[str, str]:
    candidates = _title_break_candidates(title)
    if not candidates:
        midpoint = max(1, len(title) // 2)
        return title[:midpoint], title[midpoint:]
    scored = []
    for index in candidates:
        first, second = title[:index].strip(), title[index:].strip()
        if not first or not second:
            continue
        widths = (
            _title_line_width(first, TITLE_TEXT_STYLE_SIZE, 2, font_path),
            _title_line_width(second, TITLE_TEXT_STYLE_SIZE, 2, font_path),
        )
        punctuation_bonus = 0 if title[index - 1] in "\uFF1F?!\uFF01\uFF1A:\uFF0C,\uFF1B;" else 1
        scored.append(((punctuation_bonus, max(widths), abs(widths[0] - widths[1])), (first, second)))
    return min(scored, key=lambda item: item[0])[1] if scored else (title, "")


def resolve_font_type(font_name: str, fallback: str = DEFAULT_TITLE_FONT):
    return enum_member(draft.FontType, font_name) or enum_member(draft.FontType, fallback)


def global_title_presentation(
    title: str,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    *,
    font_name: str = DEFAULT_TITLE_FONT,
    variant: str = "default",
) -> GlobalTitlePresentation:
    normalized = " ".join(title.split()).strip()
    font_path = cached_font_path(resolve_font_type(font_name))
    height_scale = min(1.0, canvas_height / 1920)
    landscape = canvas_width > canvas_height
    compact = variant == "compact"
    if variant not in {"default", "compact"}:
        raise ValueError(f"unsupported global title variant: {variant}")
    variant_scale = COMPACT_TITLE_STYLE_SCALE if compact else 1.0
    title_letter_spacing = 0 if compact else TITLE_LETTER_SPACING
    base_style_size = max(
        7.2,
        TITLE_TEXT_STYLE_SIZE * height_scale * (LANDSCAPE_TITLE_STYLE_SCALE if landscape else 1.0) * variant_scale
        + (COMPACT_TITLE_STYLE_BOOST if compact else 0),
    )
    min_style_size = max(
        5.8,
        TITLE_MIN_STYLE_SIZE * height_scale * (LANDSCAPE_TITLE_STYLE_SCALE if landscape else 1.0) * variant_scale,
    )
    horizontal_padding = max(28, round((36 if compact else TITLE_BAR_HORIZONTAL_PADDING) * height_scale))
    bar_height = max(
        72 if compact else 76 if landscape else 96,
        round(
            (COMPACT_TITLE_BAR_HEIGHT if compact else TITLE_BAR_HEIGHT)
            * height_scale
            * (LANDSCAPE_TITLE_BAR_HEIGHT_SCALE if landscape else 1.0)
        ),
    )
    max_bar_width = min(
        round(canvas_width * (0.84 if compact else 0.76)),
        round(TITLE_BAR_MAX_WIDTH * canvas_width / 1080),
    )
    max_text_width = max_bar_width - horizontal_padding * 2
    one_line_width = _title_line_width(normalized, base_style_size, title_letter_spacing, font_path)
    minimum_bar_width = (
        round(canvas_width * LANDSCAPE_TITLE_BAR_MIN_WIDTH_RATIO)
        if canvas_width > canvas_height
        else 0
    )
    if one_line_width <= max_text_width:
        return GlobalTitlePresentation(
            normalized,
            base_style_size,
            title_letter_spacing,
            max(minimum_bar_width, one_line_width + horizontal_padding * 2),
            bar_height,
        )

    lines = _balanced_title_lines(normalized, font_path)
    for half_steps in range(0, round((base_style_size - min_style_size) * 2) + 1):
        style_size = base_style_size - half_steps * 0.5
        line_widths = [_title_line_width(line, style_size, 0 if compact else 2, font_path) for line in lines if line]
        if line_widths and max(line_widths) <= max_text_width:
            font_size = round(style_size * 5.5)
            fitted_bar_height = max(
                bar_height + (1 if len(line_widths) > 1 else 0),
                round(len(line_widths) * font_size * 1.18 + 44 * height_scale),
            )
            return GlobalTitlePresentation(
                "\n".join(line for line in lines if line),
                style_size,
                0 if compact else 2,
                max(minimum_bar_width, max(line_widths) + horizontal_padding * 2),
                fitted_bar_height,
            )

    style_size = min_style_size
    line_widths = [_title_line_width(line, style_size, 0, font_path) for line in lines if line]
    font_size = round(style_size * 5.5)
    return GlobalTitlePresentation(
        "\n".join(line for line in lines if line),
        style_size,
        0,
        max(minimum_bar_width, min(max_bar_width, max(line_widths) + horizontal_padding * 2)),
        max(
            bar_height + (1 if len(line_widths) > 1 else 0),
            round(len(line_widths) * font_size * 1.18 + 44 * height_scale),
        ),
    )


def title_bar_width(
    title: str,
    canvas_width: int = 1080,
    *,
    font_path: str | None = None,
    font_name: str = DEFAULT_TITLE_FONT,
) -> int:
    if font_path is None:
        return global_title_presentation(title, canvas_width, font_name=font_name).bar_width
    measured_width = _title_line_width(title.strip(), TITLE_TEXT_STYLE_SIZE, TITLE_LETTER_SPACING, font_path)
    return min(TITLE_BAR_MAX_WIDTH, measured_width + TITLE_BAR_HORIZONTAL_PADDING * 2)


def create_title_bar_asset(
    path: Path,
    title: str,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    *,
    font_name: str = DEFAULT_TITLE_FONT,
    background_color: str = DEFAULT_TITLE_BACKGROUND_COLOR,
    variant: str = "default",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    presentation = global_title_presentation(
        title,
        canvas_width,
        canvas_height,
        font_name=font_name,
        variant=variant,
    )
    width = presentation.bar_width
    image = Image.new("RGBA", (canvas_width, presentation.bar_height), (0, 0, 0, 0))
    left = (canvas_width - width) // 2
    draw = ImageDraw.Draw(image)
    fill = (*tuple(round(channel * 255) for channel in parse_hex_color(background_color)), 255)
    if variant == "compact":
        # The compact underline is a title-length cue: longer titles get a
        # visibly longer rule while short titles remain visually light.
        line_width = max(96, min(round(canvas_width * 0.72), round(width * 0.82)))
        line_left = (canvas_width - line_width) // 2
        line_top = presentation.bar_height - COMPACT_TITLE_LINE_HEIGHT - 2
        draw.rounded_rectangle(
            (line_left, line_top, line_left + line_width, line_top + COMPACT_TITLE_LINE_HEIGHT),
            radius=COMPACT_TITLE_LINE_HEIGHT // 2,
            fill=fill,
        )
    else:
        draw.rounded_rectangle(
            (left, 0, left + width, presentation.bar_height - 1),
            radius=6,
            fill=fill,
        )
    image.save(path)
    return path


def global_title_bar_scale(title: str, canvas_width: int = 1080) -> float:
    return round(max(0.12, title_bar_width(title, canvas_width) / canvas_width), 5)


def make_global_title_segment(
    title: str,
    total_duration_ms: int,
    *,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    font_name: str = DEFAULT_TITLE_FONT,
    text_color: str = DEFAULT_TITLE_COLOR,
    transform_y: float = TITLE_Y,
    variant: str = "default",
):
    presentation = global_title_presentation(
        title,
        canvas_width,
        canvas_height,
        font_name=font_name,
        variant=variant,
    )
    return draft.TextSegment(
        presentation.text,
        draft.trange("0s", f"{total_duration_ms / 1000:.3f}s"),
        font=resolve_font_type(font_name),
        style=draft.TextStyle(
            size=presentation.style_size,
            bold=True,
            color=parse_hex_color(text_color),
            align=1,
            auto_wrapping=False,
            underline=variant != "compact",
            letter_spacing=presentation.letter_spacing,
            line_spacing=0,
        ),
        clip_settings=draft.ClipSettings(transform_x=0.0, transform_y=transform_y),
        border=draft.TextBorder(alpha=0.0, width=0),
    )


class JianyingRenderer:
    def __init__(self, *, theme: Theme | None = None, project_root: Path | None = None):
        self.theme = theme or Theme()
        self.project_root = project_root or PROJECT_ROOT

    def render(
        self,
        result: LayoutResult,
        *,
        draft_folder: Path,
        draft_name: str,
        background: Path | None = None,
        foreground_video: Path | None = None,
        foreground_round_corner: float = 0.0,
        foreground_scale: float = 1.0,
        audio_path: Path | None = None,
        background_music_path: Path | None = None,
        include_sound_effects: bool = True,
        global_title: str = "",
        global_title_variant: str = "default",
        global_title_center_ratio: float = 0.14,
        title_font: str = DEFAULT_TITLE_FONT,
        title_color: str = DEFAULT_TITLE_COLOR,
        title_background_color: str = DEFAULT_TITLE_BACKGROUND_COLOR,
        extra_hold_ms: int = FINAL_HOLD_MS,
        cover_image: Path | None = None,
        replace: bool = False,
    ) -> Path:
        draft_folder = draft_folder.expanduser().resolve()
        draft_folder.mkdir(parents=True, exist_ok=True)
        folder = draft.DraftFolder(str(draft_folder))
        script = folder.create_draft(
            draft_name,
            width=result.canvas.width,
            height=result.canvas.height,
            fps=30,
            allow_replace=replace,
        )

        foreground_material = None
        foreground_duration_ms = 0
        if foreground_video:
            foreground_video = self._resolve_path(foreground_video)
            if not foreground_video.is_file():
                raise FileNotFoundError("missing file")
            foreground_material = draft.VideoMaterial(str(foreground_video), material_name=foreground_video.stem)
            foreground_duration_ms = max(1, foreground_material.duration // 1000)

        content_end_ms = max((item.end_ms for item in result.elements), default=4000)
        content_duration_ms = content_end_ms + extra_hold_ms if result.elements else content_end_ms
        total_duration_ms = max(content_duration_ms, foreground_duration_ms)
        if background:
            background = self._resolve_path(background)
            if not background.exists():
                raise FileNotFoundError(f"missing background: {background}")
            script.add_track(
                draft.TrackType.video,
                "background",
                relative_index=BACKGROUND_TRACK_RELATIVE_INDEX,
            )
            script.add_segment(
                draft.VideoSegment(str(background), draft.trange("0s", f"{total_duration_ms / 1000:.3f}s")),
                "background",
            )

        if foreground_material is not None:
            if not 0.0 <= foreground_round_corner <= 100.0:
                raise ValueError("foreground round corner must be between 0 and 100")
            if foreground_scale <= 0:
                raise ValueError("foreground scale must be greater than zero")
            if foreground_material.width <= 0 or foreground_material.height <= 0:
                raise ValueError("invalid foreground dimensions")
            if foreground_material.width <= foreground_material.height:
                raise ValueError("foreground video must use a landscape aspect ratio")
            automatic_fit = min(
                result.canvas.width / foreground_material.width,
                result.canvas.height / foreground_material.height,
            )
            scale = (result.canvas.width / foreground_material.width) / automatic_fit * foreground_scale
            script.add_track(draft.TrackType.video, "foreground_video", relative_index=0)
            foreground_segment = draft.VideoSegment(
                foreground_material,
                draft.trange("0s", f"{foreground_duration_ms / 1000:.3f}s"),
                clip_settings=draft.ClipSettings(
                    scale_x=scale,
                    scale_y=scale,
                    transform_x=0.0,
                    transform_y=0.0,
                ),
            )
            if foreground_round_corner > 0:
                foreground_segment.add_mask(
                    draft.MaskType.矩形,
                    size=1.0,
                    rect_width=1.0,
                    round_corner=foreground_round_corner,
                )
            script.add_segment(foreground_segment, "foreground_video")

        if audio_path:
            audio_path = self._resolve_path(audio_path)
            if audio_path.exists():
                material = draft.AudioMaterial(str(audio_path), material_name=audio_path.stem)
                audio_duration_ms = min(total_duration_ms, material.duration // 1000)
                script.add_track(draft.TrackType.audio, "narration", relative_index=0)
                narration = draft.AudioSegment(
                    material,
                    draft.trange("0s", f"{audio_duration_ms / 1000:.3f}s"),
                    volume=2.0,
                )
                narration.add_fade("0.08s", "0.12s")
                script.add_segment(narration, "narration")

        if background_music_path:
            self._add_background_music(script, background_music_path, total_duration_ms)

        if include_sound_effects:
            self._add_sound_effects(script, result, total_duration_ms)

        if global_title.strip():
            if not 0.0 < global_title_center_ratio < 0.5:
                raise ValueError("global title center ratio must be between zero and 0.5")
            asset_root = draft_folder / draft_name / "Resources"
            title_bar = create_title_bar_asset(
                asset_root / "title_bar_yellow_adaptive.png",
                global_title.strip(),
                result.canvas.width,
                result.canvas.height,
                font_name=title_font,
                background_color=title_background_color,
                variant=global_title_variant,
            )
            script.add_track(draft.TrackType.video, "global_title_bar", relative_index=900)
            script.add_track(draft.TrackType.text, "global_title", relative_index=910)
            bar = draft.VideoSegment(
                str(title_bar),
                draft.trange("0s", f"{total_duration_ms / 1000:.3f}s"),
                clip_settings=draft.ClipSettings(
                    transform_x=0.0,
                    transform_y=title_transform_y(
                        result.canvas.width,
                        result.canvas.height,
                        global_title_center_ratio,
                    ),
                    scale_x=1.0,
                    scale_y=1.0,
                ),
            )
            script.add_segment(bar, "global_title_bar")
            title_segment = make_global_title_segment(
                global_title.strip(),
                total_duration_ms,
                canvas_width=result.canvas.width,
                canvas_height=result.canvas.height,
                font_name=title_font,
                text_color=title_color,
                transform_y=title_transform_y(
                    result.canvas.width,
                    result.canvas.height,
                    global_title_center_ratio,
                ),
                variant=global_title_variant,
            )
            script.add_segment(title_segment, "global_title")

        if any(element.role == "subtitle" for element in result.elements):
            script.add_track(draft.TrackType.text, NARRATION_SUBTITLE_TRACK, relative_index=1000)

        scene_backgrounds = normalize_scene_backgrounds(
            result.elements,
            content_end_ms=content_end_ms,
            final_end_ms=total_duration_ms,
        )
        if scene_backgrounds:
            script.add_track(draft.TrackType.video, SCENE_BACKGROUND_TRACK, relative_index=1)
            previous_transition_resource_id = ""
            for background_index, element in enumerate(scene_backgrounds):
                segment = self._make_segment(element, result)
                if background_index + 1 < len(scene_backgrounds):
                    duration_ms = min(
                        SCENE_TRANSITION_DURATION_MS,
                        max(180, (element.end_ms - element.start_ms) // 4),
                    )
                    transition = scene_transition_for_index(
                        background_index,
                        randomize=True,
                        previous_resource_id=previous_transition_resource_id,
                    )
                    segment.add_transition(
                        transition,
                        duration=f"{duration_ms / 1000:.3f}s",
                    )
                    previous_transition_resource_id = str(transition.value.resource_id)
                script.add_segment(segment, SCENE_BACKGROUND_TRACK)

        foreground_elements = [element for element in result.elements if element.role != "background"]
        for index, element in enumerate(sorted(foreground_elements, key=lambda item: (item.z_index, item.start_ms, item.element_id))):
            element = stabilize_final_element(
                element,
                content_end_ms=content_end_ms,
                final_end_ms=total_duration_ms,
            )
            track_name = NARRATION_SUBTITLE_TRACK if element.role == "subtitle" else f"layout_{index:02d}_{element.element_id}"
            track_type = draft.TrackType.text if element.element_type == "text" else draft.TrackType.video
            if element.role != "subtitle":
                script.add_track(track_type, track_name, relative_index=max(1, element.z_index))
            segment = self._make_segment(element, result)
            script.add_segment(segment, track_name)

        draft_path = draft_folder / draft_name
        cover_source = (
            self._resolve_path(cover_image)
            if cover_image is not None
            else select_cover_image(result, self.project_root)
        )
        if cover_source is not None and cover_source.is_file():
            cover_asset = self._prepare_cover_asset(
                cover_source,
                draft_path,
                result.canvas.width,
                result.canvas.height,
            )
            script.set_cover_image(str(cover_asset))
        script.save()
        return draft_path

    def _prepare_cover_asset(
        self,
        source: Path,
        draft_path: Path,
        width: int,
        height: int,
    ) -> Path:
        """Create the two local cover sizes expected by the Jianying index."""
        draft_path.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            cover = ImageOps.fit(
                image,
                (max(1, width), max(1, height)),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            cover_path = draft_path / "draft_cover.jpg"
            cover.save(cover_path, format="JPEG", quality=95, optimize=True)
            local_path = draft_path / "draft_local_cover.jpg"
            cover.resize(
                (max(1, width // 4), max(1, height // 4)),
                Image.Resampling.LANCZOS,
            ).save(local_path, format="JPEG", quality=90, optimize=True)
        return cover_path

    def _add_background_music(self, script, path: Path, total_duration_ms: int) -> None:
        path = self._resolve_path(path)
        if not path.exists():
                raise FileNotFoundError("missing file")
        probe = draft.AudioMaterial(str(path), material_name="background_music")
        source_duration_ms = probe.duration // 1000
        if source_duration_ms < 34:
                raise ValueError("invalid media value")

        script.add_track(draft.TrackType.audio, "background_music", relative_index=-10)
        cursor_ms = 0
        while cursor_ms < total_duration_ms:
            duration_ms = min(source_duration_ms, total_duration_ms - cursor_ms)
            material = draft.AudioMaterial(str(path), material_name="background_music")
            segment = draft.AudioSegment(
                material,
                draft.trange(f"{cursor_ms / 1000:.3f}s", f"{duration_ms / 1000:.3f}s"),
                volume=BACKGROUND_MUSIC_VOLUME,
            )
            is_first = cursor_ms == 0
            is_last = cursor_ms + duration_ms >= total_duration_ms
            fade_in_ms = min(1200 if is_first else 40, max(0, duration_ms // 3))
            fade_out_ms = min(1500 if is_last else 40, max(0, duration_ms // 3))
            segment.add_fade(f"{fade_in_ms / 1000:.3f}s", f"{fade_out_ms / 1000:.3f}s")
            script.add_segment(segment, "background_music")
            cursor_ms += duration_ms

    def _add_sound_effects(self, script, result: LayoutResult, total_duration_ms: int) -> None:
        events = collect_sound_events(result)
        if not events:
            return
        library = load_sound_library(self.project_root)
        track_added = False
        previous_path: Path | None = None
        previous_end_ms = -1
        for event in events:
            asset = choose_sound_asset(event, library, previous_path=previous_path)
            if asset is None or event.start_ms >= total_duration_ms:
                continue
            material = draft.AudioMaterial(str(asset.path), material_name=asset.name)
            duration_ms = min(
                material.duration // 1000,
                CUE_MAX_DURATION_MS.get(event.cue, 700),
                total_duration_ms - event.start_ms,
            )
            if duration_ms < 34 or event.start_ms < previous_end_ms:
                continue
            if not track_added:
                script.add_track(draft.TrackType.audio, "sound_effects", relative_index=10)
                track_added = True
            segment = draft.AudioSegment(
                material,
                draft.trange(f"{event.start_ms / 1000:.3f}s", f"{duration_ms / 1000:.3f}s"),
                volume=CUE_VOLUME.get(event.cue, 0.24),
            )
            fade_out_ms = min(100, max(20, duration_ms // 4))
            segment.add_fade("0.015s", f"{fade_out_ms / 1000:.3f}s")
            script.add_segment(segment, "sound_effects")
            previous_path = asset.path
            previous_end_ms = event.start_ms + duration_ms

    def _make_segment(self, element: ElementLayout, result: LayoutResult):
        duration_ms = max(34, element.end_ms - element.start_ms)
        timerange = draft.trange(f"{element.start_ms / 1000:.3f}s", f"{duration_ms / 1000:.3f}s")
        x, y = normalized_center(element.box, result.canvas)

        if element.element_type == "text":
            text = "\n".join(element.lines) if element.lines else element.content
            font_size = element.font_size or self.theme.body_font_size
            style_size = text_style_size(font_size, element.role)
            requested_style_size = element.metadata.get("jianying_text_size")
            if requested_style_size is not None:
                try:
                    requested_style_size = float(requested_style_size)
                except (TypeError, ValueError):
                    requested_style_size = 0.0
                if requested_style_size > 0:
                    style_size = round(requested_style_size, 2)
            color = str(element.metadata.get("text_color", self.theme.text_color))
            font_name = str(element.metadata.get("font_name", ""))
            if element.role in {"label", "number"}:
                color = str(element.metadata.get("text_color", DEFAULT_KEYWORD_TEXT_COLOR))
                font_name = DEFAULT_KEYWORD_FONT
            if font_name in BANNED_FONT_NAMES:
                font_name = "ResourceHanRoundedCN_Md"
            font = enum_member(draft.FontType, font_name)
            segment = draft.TextSegment(
                text,
                timerange,
                font=font,
                style=draft.TextStyle(
                    size=style_size,
                    bold=element.role in {"title", "label", "number"},
                    color=parse_hex_color(color),
                    fill_alpha=1.0,
                    align=1,
                    auto_wrapping=False,
                    max_line_width=max(0.1, min(1.0, (element.box.width - 32) / result.canvas.width)),
                    line_spacing=0,
                ),
                clip_settings=draft.ClipSettings(transform_x=x, transform_y=y),
                border=(
                    draft.TextBorder(
                        alpha=1.0,
                        color=parse_hex_color(DEFAULT_KEYWORD_BORDER_COLOR),
                        width=DEFAULT_KEYWORD_BORDER_WIDTH,
                    )
                    if element.role in {"label", "number"}
                    else None
                ),
                background=draft.TextBackground(
                    color=str(element.metadata.get(
                        "subtitle_background_color",
                        self.theme.subtitle_background_color,
                    )),
                    alpha=1.0,
                    round_radius=0.0,
                    height=SUBTITLE_BACKGROUND_HEIGHT,
                    width=SUBTITLE_BACKGROUND_WIDTH,
                ) if element.role == "subtitle" else None,
                shadow=(
                    draft.TextShadow(alpha=0.25, diffuse=8, distance=2)
                    if element.role == "subtitle"
                    else draft.TextShadow(alpha=0.16, diffuse=3, distance=1)
                    if element.role == "title"
                    else None
                ),
            )
            if not apply_text_animations(segment, element):
                add_enter_keyframes(segment, element, result, 1.0)
            return segment

        if not element.content.strip():
            raise FileNotFoundError(f"\u7f3a\u5c11\u56fe\u7247\u7d20\u6750\uff1a{element.element_id}")
        asset_path = self._resolve_path(Path(element.content))
        if not asset_path.is_file():
            raise FileNotFoundError(f"\u7f3a\u5c11\u56fe\u7247\u7d20\u6750\uff1a{asset_path}")
        x, y, scale = image_transform(element, result)
        segment = draft.VideoSegment(
            str(asset_path),
            timerange,
            clip_settings=draft.ClipSettings(transform_x=x, transform_y=y, scale_x=scale, scale_y=scale),
        )
        # Picture effects are currently paused. Keep any legacy metadata
        # readable, but do not write a scene effect into newly built drafts.
        has_reflow = bool(element.metadata.get("layout_keyframes"))
        has_native_intro = apply_video_animations(segment, element, allow_intro=not has_reflow)
        if has_reflow or not has_native_intro:
            add_enter_keyframes(segment, element, result, scale)
        if has_reflow:
            add_layout_keyframes(segment, element, result)
        else:
            add_hold_motion(segment, element, result)
        return segment

    def _resolve_path(self, path: Path) -> Path:
        return path if path.is_absolute() else self.project_root / path
