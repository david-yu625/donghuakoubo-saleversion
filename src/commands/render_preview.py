"""Render one scene JSON as a PNG layout preview."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..layouts.engine import LayoutEngine
from ..renderers.preview import render_preview


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--template", choices=["auto", "title_image", "focus_history", "split_compare"], default="auto")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--theme", default="", help="兼容参数；当前固定使用白色板书主题")
    args = parser.parse_args()

    content = json.loads(args.input.read_text(encoding="utf-8"))
    engine = LayoutEngine()
    result = engine.auto_build(content) if args.template == "auto" else engine.build(args.template, content)
    print(render_preview(result, args.output, visual_theme=args.theme))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
