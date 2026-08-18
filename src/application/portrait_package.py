"""Build a portrait wrapper draft around an exported landscape video."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..core.models import Box, LayoutResult, Theme, canvas_for_orientation
from ..layouts.engine import LayoutEngine
from ..layouts.regions import subtitle_area
from ..paths import portrait_package_dir
from ..pipeline.project_reader import read_copy_lines, read_subtitles
from ..prepare import ensure_project_background
from ..renderers.jianying_renderer import JianyingRenderer, select_cover_image
from ..settings import load_render_settings
from .project_compiler import build_subtitle_elements, without_opening_title_subtitle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PORTRAIT_PACKAGE_SIZE = (1080, 1920)
PORTRAIT_PACKAGE_BACKGROUND = PROJECT_ROOT / "picturies" / "background" / "background_1.png"
PORTRAIT_PACKAGE_VIDEO_ROUND_CORNER = 10.0
PORTRAIT_PACKAGE_VIDEO_SCALE = 1.15
PORTRAIT_PACKAGE_TITLE_CENTER_RATIO = 0.27
PORTRAIT_PACKAGE_TITLE_FONT = "ResourceHanRoundedCN_Bold"
PORTRAIT_PACKAGE_SUBTITLE_OFFSET_Y = -72


@dataclass(frozen=True)
class PortraitPackageResult:
    path: Path
    package_dir: Path
    source_video: Path
    layout: LayoutResult


def build_portrait_package(
    project_dir: Path,
    *,
    source_video: Path,
    draft_folder: Path,
    draft_name: str,
    project_title: str = "",
    visual_theme: str = "",
    include_subtitles: bool = True,
    include_background: bool = True,
    replace: bool = False,
) -> PortraitPackageResult:
    """Create a 1080x1920 wrapper without rebuilding the landscape scenes."""
    project_dir = project_dir.expanduser().resolve()
    source_video = source_video.expanduser().resolve()
    if not source_video.is_file():
        raise FileNotFoundError(f"横屏导出视频不存在：{source_video}")

    package_dir = portrait_package_dir(project_dir)
    settings = load_render_settings(visual_theme)
    canvas = canvas_for_orientation("portrait")
    theme = Theme(
        subtitle_font=settings.subtitle_font,
        subtitle_color=settings.subtitle_color,
        subtitle_background_color=settings.subtitle_background_color,
    )
    engine = LayoutEngine(theme=theme, canvas=canvas)

    subtitle_rows: list[tuple[str, int, int]] = []
    timeline_path = project_dir / "timeline.csv"
    if include_subtitles:
        subtitle_rows = without_opening_title_subtitle(
            read_subtitles(timeline_path, read_copy_lines(project_dir / "wenan.txt")),
            project_title,
        )
    subtitle_box = subtitle_area(canvas)
    subtitle_box = Box(
        subtitle_box.x,
        subtitle_box.y + PORTRAIT_PACKAGE_SUBTITLE_OFFSET_Y,
        subtitle_box.width,
        subtitle_box.height,
    )
    elements = build_subtitle_elements(
        subtitle_rows,
        engine,
        box=subtitle_box,
    )
    layout = LayoutResult(
        template="portrait_package",
        canvas=canvas,
        elements=elements,
        decisions=[
            "横屏导出视频作为完整画面层，不重新计算分镜布局",
            "横屏视频按宽度适配到 1080px，垂直居中，上下展示包装背景",
            "标题和字幕复用原生竖屏的位置、字号与自适应规则",
            "包装层不重复添加原横屏视频中的配音、BGM 或音效",
        ],
    )
    package_background = None
    if include_background:
        package_background = ensure_project_background(
            package_dir,
            PROJECT_ROOT,
            source=PORTRAIT_PACKAGE_BACKGROUND,
            size=PORTRAIT_PACKAGE_SIZE,
        )
    cover_image = None
    landscape_layout_path = project_dir / "layout_result.json"
    if landscape_layout_path.is_file():
        try:
            landscape_layout = LayoutResult.from_dict(
                json.loads(landscape_layout_path.read_text(encoding="utf-8-sig"))
            )
            cover_image = select_cover_image(landscape_layout, project_dir)
        except (OSError, ValueError, json.JSONDecodeError):
            # A missing or stale landscape layout must not block packaging.
            cover_image = None
    path = JianyingRenderer(project_root=PROJECT_ROOT).render(
        layout,
        draft_folder=draft_folder,
        draft_name=draft_name,
        background=package_background,
        foreground_video=source_video,
        foreground_round_corner=PORTRAIT_PACKAGE_VIDEO_ROUND_CORNER,
        foreground_scale=PORTRAIT_PACKAGE_VIDEO_SCALE,
        include_sound_effects=False,
        global_title=project_title.strip(),
        global_title_variant="compact",
        global_title_center_ratio=PORTRAIT_PACKAGE_TITLE_CENTER_RATIO,
        title_font=PORTRAIT_PACKAGE_TITLE_FONT,
        title_color="#FFFFFF",
        title_background_color=settings.title_background_color,
        extra_hold_ms=0,
        cover_image=cover_image,
        replace=replace,
    )
    return PortraitPackageResult(
        path=path,
        package_dir=package_dir,
        source_video=source_video,
        layout=layout,
    )
