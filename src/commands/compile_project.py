"""Compile a prepared project into one layout result JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..application.project_compiler import compile_project
from ..env import load_env_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--theme", default="", help="兼容参数；当前固定使用白色板书主题")
    parser.add_argument("--orientation", default="", help="画布方向：portrait/landscape 或 竖屏/横屏")
    subtitle_group = parser.add_mutually_exclusive_group()
    subtitle_group.add_argument("--subtitles", dest="include_subtitles", action="store_true")
    subtitle_group.add_argument("--no-subtitles", dest="include_subtitles", action="store_false")
    parser.set_defaults(include_subtitles=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    project_dir = args.project_dir.expanduser().resolve()
    result = compile_project(
        project_dir,
        project_title=args.title.strip() or project_dir.name,
        visual_theme=args.theme,
        orientation=args.orientation,
        include_subtitles=args.include_subtitles,
    )
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)
    print(f"元素：{len(result.elements)}")
    print(f"警告：{len(result.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
