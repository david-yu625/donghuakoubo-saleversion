"""Command-line layout preview for src."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..layouts.engine import LayoutEngine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    layout_parser = subparsers.add_parser("layout", help="计算场景布局")
    layout_parser.add_argument("input", type=Path, help="场景 JSON 文件")
    layout_parser.add_argument("--template", choices=["auto", "title_image", "focus_history", "split_compare"], default="auto")
    layout_parser.add_argument("--output", type=Path, help="布局 JSON 输出路径")

    args = parser.parse_args()
    if args.command == "layout":
        content = json.loads(args.input.read_text(encoding="utf-8"))
        engine = LayoutEngine()
        result = engine.auto_build(content) if args.template == "auto" else engine.build(args.template, content)
        output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output + "\n", encoding="utf-8")
            print(args.output)
        else:
            print(output)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
