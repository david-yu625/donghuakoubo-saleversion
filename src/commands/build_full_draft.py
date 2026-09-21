"""Build one complete Jianying draft from an existing project output folder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..application import build_project_draft
from ..core.models import LayoutResult
from ..env import load_env_file
from ..paths import default_draft_folder


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--layout", type=Path, help="第07步生成的 layout_result.json；默认读取项目目录下同名文件")
    parser.add_argument("--title", default="")
    parser.add_argument("--draft-folder", type=Path, default=default_draft_folder())
    parser.add_argument("--draft-name", default="src_完整布局草稿")
    parser.add_argument("--background", type=Path)
    parser.add_argument("--no-background", action="store_true")
    parser.add_argument("--bgm", type=Path, help="背景音乐源文件，默认使用 audio/bgm/bgm2[Sub Title].mp3")
    parser.add_argument("--audio", type=Path, help="旁白音频文件；默认使用项目目录下的 narration.wav")
    parser.add_argument("--theme", default="", help="兼容参数；当前固定使用白色板书主题")
    parser.add_argument("--orientation", default="", help="画布方向：portrait/landscape 或 竖屏/横屏")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--no-bgm", action="store_true")
    parser.add_argument("--no-sound-effects", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    project_dir = args.project_dir.expanduser().resolve()
    layout_path = (
        args.layout.expanduser().resolve()
        if args.layout is not None
        else project_dir / "layout_result.json"
    )
    if not layout_path.is_file():
        raise FileNotFoundError(f"第07步布局文件不存在：{layout_path}")
    layout = LayoutResult.from_dict(json.loads(layout_path.read_text(encoding="utf-8-sig")))

    build = build_project_draft(
        project_dir,
        layout=layout,
        draft_folder=args.draft_folder,
        draft_name=args.draft_name,
        project_title=args.title.strip(),
        background=args.background,
        background_music=args.bgm,
        narration_audio=args.audio,
        include_audio=not args.no_audio,
        include_background_music=not args.no_bgm,
        include_background=not args.no_background,
        include_sound_effects=not args.no_sound_effects,
        visual_theme=args.theme,
        orientation=args.orientation,
        replace=args.replace,
    )
    print(f"布局：{layout_path}")
    print(build.path)
    print(f"背景：{build.background}")
    if build.background_music is not None:
        print(f"背景音乐：{build.background_music}")
    if build.narration_audio is not None:
        print(f"旁白：{build.narration_audio}")
    print(f"元素：{len(build.layout.elements)}")
    print(f"警告：{len(build.layout.warnings)}")
    for warning in build.layout.warnings:
        print(f"警告：{warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
