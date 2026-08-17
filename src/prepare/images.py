#!/usr/bin/env python3
"""Step 06: generate styled background and element assets."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
from pathlib import Path

from PIL import Image

from ..env import load_env_file
from . import generate_native_graphic, native_graphic_kind
from .image_generation import (
    DEFAULT_IMAGE_MODEL,
    flatten_white_background,
    generate_image,
    original_image_path,
    resolve_image_model,
)
from .image_prompts import compact_prompt, legacy_role


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPT_FIELDS = ["element_id", "shot_id", "role", "content", "width", "height", "asset_path", "prompt"]
LEGACY_PROMPT_FIELDS = [field for field in PROMPT_FIELDS if field != "role"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 image_prompts_plus.csv 批量生成图片。")
    parser.add_argument("prompt_csv", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="只生成前 N 张，0 表示全部")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--req-key", default="")
    parser.add_argument("--model", default="", help=f"图片模型，默认读取 IMAGE_MODEL 或 {DEFAULT_IMAGE_MODEL}")
    parser.add_argument("--base-url", default="", help="OpenAI 兼容图片接口地址，默认读取 IMAGE_BASE_URL")
    parser.add_argument("--api-key", default="", help="OpenAI 兼容图片接口密钥，默认读取 IMAGE_API_KEY")
    parser.add_argument("--quality", default="", help="可选图片质量，例如 medium 或 high")
    parser.add_argument("--theme", default="white", help="固定为白色板书主题")
    parser.add_argument(
        "--element-id",
        action="append",
        default=[],
        help="只生成指定 element_id，可重复传入",
    )
    parser.add_argument("--native-only", action="store_true", help="只生成确定性图形素材，不调用文生图接口")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        load_env_file(PROJECT_ROOT / ".env")
        prompt_csv = args.prompt_csv.expanduser().resolve()
        rows = read_rows(prompt_csv)
        rows = select_rows(rows, args.element_id)
        if args.limit > 0:
            rows = rows[: args.limit]
        if not rows:
            print(f"没有需要生成的图片：{prompt_csv}")
            return 0
        model = resolve_image_model(args.model or args.req_key)
        print(f"图片模型：{model}")
        failures: list[tuple[str, Exception]] = []
        for index, row in enumerate(rows, start=1):
            output = Path(row["asset_path"]).expanduser()
            if not output.is_absolute():
                output = (PROJECT_ROOT / output).resolve()
            if output.exists() and not args.overwrite:
                print(f"[{index}/{len(rows)}] 已存在，跳过：{output}")
                continue
            if row["role"] in {"overview_diagram", "subpoint_diagram"}:
                row["role"] = "element"
            if row["role"] not in {"background", "element"}:
                failures.append((row["element_id"], ValueError(f"不支持的图片 role：{row['role']}")))
                continue
            native_kind = None if row["role"] == "background" else native_graphic_kind(row["content"])
            if args.native_only and native_kind is None:
                continue
            prompt = compact_prompt(
                row["prompt"],
                visual_theme=args.theme,
            )
            if prompt != row["prompt"]:
                print(f"[{index}/{len(rows)}] 提示词已按统一背景策略规范到 {len(prompt)} 字符")
            print(f"[{index}/{len(rows)}] 生成：{row['element_id']} -> {output}")
            try:
                if native_kind is not None:
                    generate_native_graphic(
                        row["content"], output, int(row["width"]), int(row["height"]),
                    )
                    flatten_white_background(output, output)
                    original = original_image_path(output)
                    original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(output, original)
                    print(f"[{index}/{len(rows)}] 原生图形：{native_kind}")
                    continue
                generate_image(
                    prompt=prompt,
                    output_path=output,
                    width=int(row["width"]),
                    height=int(row["height"]),
                    model=model,
                    api_key=args.api_key or os.getenv("IMAGE_API_KEY", ""),
                    base_url=args.base_url or os.getenv("IMAGE_BASE_URL", ""),
                    quality=args.quality or os.getenv("IMAGE_QUALITY", ""),
                    visual_theme=args.theme,
                )
            except Exception as exc:
                failures.append((row["element_id"], exc))
                print(f"[{index}/{len(rows)}] 失败：{row['element_id']}：{exc}")
        if failures:
            print(f"图片生成结束，共 {len(failures)} 张失败：")
            for element_id, error in failures:
                print(f"- {element_id}: {error}")
            return 1
    except Exception as exc:
        print(f"错误：{exc}")
        return 1
    print("图片生成完成")
    return 0


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames not in (PROMPT_FIELDS, LEGACY_PROMPT_FIELDS):
            raise ValueError(f"提示词 CSV 列名不匹配：{reader.fieldnames}")
        rows = [{field: (row.get(field) or "").strip() for field in PROMPT_FIELDS} for row in reader]
    for row in rows:
        if not row["role"]:
            row["role"] = legacy_role(row["element_id"], "image")
    return rows


def generate_white_background(output: Path, width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError(f"背景尺寸必须大于 0：{width}x{height}")
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), "white").save(output)
    original = original_image_path(output)
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, original)


def select_rows(rows: list[dict[str, str]], element_ids: list[str]) -> list[dict[str, str]]:
    selected = {element_id.strip() for element_id in element_ids if element_id.strip()}
    if not selected:
        return rows
    available = {row["element_id"] for row in rows}
    missing = sorted(selected - available)
    if missing:
        raise ValueError(f"提示词 CSV 中不存在元素：{', '.join(missing)}")
    return [row for row in rows if row["element_id"] in selected]


if __name__ == "__main__":
    raise SystemExit(main())
