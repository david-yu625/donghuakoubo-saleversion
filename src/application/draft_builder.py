"""Build a complete editable draft from one prepared project directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.models import LayoutResult
from ..prepare import ensure_project_background, ensure_project_background_music
from ..renderers.jianying_renderer import JianyingRenderer
from ..settings import default_background_image, load_render_settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DraftBuildResult:
    path: Path
    layout: LayoutResult
    background: Path | None
    background_music: Path | None
    narration_audio: Path | None


def build_project_draft(
    project_dir: Path,
    *,
    layout: LayoutResult,
    draft_folder: Path,
    draft_name: str,
    project_title: str = "",
    background: Path | None = None,
    background_music: Path | None = None,
    narration_audio: Path | None = None,
    include_audio: bool = True,
    include_background_music: bool = True,
    include_background: bool = True,
    include_sound_effects: bool = True,
    visual_theme: str = "",
    orientation: str = "",
    replace: bool = False,
) -> DraftBuildResult:
    project_dir = project_dir.expanduser().resolve()
    settings = load_render_settings(visual_theme)
    del orientation
    background_path: Path | None = None
    if include_background:
        background_source = (
            background.expanduser().resolve()
            if background is not None
            else default_background_image(PROJECT_ROOT, settings.visual_theme.key)
        )
        background_path = ensure_project_background(
            project_dir,
            PROJECT_ROOT,
            source=background_source,
            size=(layout.canvas.width, layout.canvas.height),
        )
        if not background_path.exists():
            raise FileNotFoundError(f"背景文件不存在：{background_path}")

    audio_path: Path | None = None
    if include_audio:
        if narration_audio is not None:
            audio_path = narration_audio.expanduser().resolve()
            if not audio_path.is_file():
                raise FileNotFoundError(f"旁白音频不存在：{audio_path}")
        else:
            project_audio = project_dir / "narration.wav"
            audio_path = project_audio if project_audio.is_file() else None
    background_music_path = (
        ensure_project_background_music(
            project_dir,
            PROJECT_ROOT,
            source=background_music,
        )
        if include_background_music
        else None
    )
    path = JianyingRenderer(project_root=PROJECT_ROOT).render(
        layout,
        draft_folder=draft_folder,
        draft_name=draft_name,
        background=background_path,
        audio_path=audio_path,
        background_music_path=background_music_path,
        include_sound_effects=include_sound_effects,
        global_title=project_title.strip(),
        title_font=settings.title_font,
        title_color=settings.title_color,
        title_background_color=settings.title_background_color,
        replace=replace,
    )
    return DraftBuildResult(
        path=path,
        layout=layout,
        background=background_path,
        background_music=background_music_path,
        narration_audio=audio_path,
    )
