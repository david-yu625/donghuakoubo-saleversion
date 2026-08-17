"""Build a portrait wrapper draft around an exported landscape video."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..application import build_portrait_package
from ..env import load_env_file
from ..paths import default_draft_folder


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path, help="横屏项目目录，例如 output/<主题>/landscape")
    parser.add_argument("source_video", type=Path, help="已经导出的横屏视频文件")
    parser.add_argument("--title", default="")
    parser.add_argument("--draft-folder", type=Path, default=default_draft_folder())
    parser.add_argument("--draft-name", default="portrait_package")
    parser.add_argument("--theme", default="")
    parser.add_argument("--no-subtitles", action="store_true")
    parser.add_argument("--no-background", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    result = build_portrait_package(
        args.project_dir,
        source_video=args.source_video,
        draft_folder=args.draft_folder,
        draft_name=args.draft_name,
        project_title=args.title.strip(),
        visual_theme=args.theme,
        include_subtitles=not args.no_subtitles,
        include_background=not args.no_background,
        replace=args.replace,
    )
    print(result.path)
    print(f"source_video={result.source_video}")
    print(f"subtitle_elements={sum(item.role == 'subtitle' for item in result.layout.elements)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
