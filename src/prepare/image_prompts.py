#!/usr/bin/env python3
"""Step 05: add visual style rules to Step 04 content designs.

This module must not reinterpret the narration or invent visual objects.  The
``content`` field is the semantic contract produced by Step 04; this step only
adds rendering style, canvas orientation, theme and model-limit constraints.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from pathlib import Path

from ..core.models import normalize_orientation
from ..env import load_env_file
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSET_LIBRARY = PROJECT_ROOT / "mg_asset_library" / "images"


def make_even(value: int) -> int:
    if value <= 0:
        raise ValueError(f"图片尺寸必须大于 0：{value}")
    return value if value % 2 == 0 else value + 1


ELEMENT_INPUT_FIELDS = [
    "element_id",
    "shot_id",
    "type",
    "role",
    "content",
    "start_ms",
    "end_ms",
]
LEGACY_ELEMENT_INPUT_FIELDS = [field for field in ELEMENT_INPUT_FIELDS if field != "role"]
ELEMENT_ASSET_FIELDS = [*ELEMENT_INPUT_FIELDS, "asset_path"]
LEGACY_ELEMENT_ASSET_FIELDS = [*LEGACY_ELEMENT_INPUT_FIELDS, "asset_path"]
PROMPT_FIELDS = ["element_id", "shot_id", "role", "content", "width", "height", "asset_path", "prompt"]
DEFAULT_IMAGE_WIDTH = 1024
DEFAULT_IMAGE_HEIGHT = 1536
LANDSCAPE_IMAGE_WIDTH = 1536
LANDSCAPE_IMAGE_HEIGHT = 864
MAX_PROMPT_CHARS = 790

BACKGROUND_IMAGE_PROMPT = (
    "#背景图生成\n"
    "#图片内容\n{content}\n"
    "#背景\n"
    "1. 面向抖音的专业白板科普短视频。\n"
    "#目标\n"
    "1. MG 动画风格，手绘白板元素感。\n"
    "#要求\n"
    "1. 图片中不要出现 Excalidraw 字样。\n"
    "2. 画笔线条稍微粗一些。\n"
    "3. 图片背景是纯白色背景\n"
    "4. 标题醒目清晰，可用简单彩色横线、虚线分隔下方内容区。\n"
    "5. 标题的最后几个字可以蓝色、黄色交叉，前面的字是黑色，不要加粗。\n"
    "6. 背景只保留标题、少量文字和装饰线；严禁绘制任何具体对象或插图，包括人物、设备、图标、节点、连线、箭头、流程图、关系图、场景图。\n"
    "7. 标题、文字、装饰线只能在顶部 1/5，必须以画布水平中心为轴居中对齐，不得进入中下部。\n"
    "8. 下方 4/5 必须是纯白空白，禁止文字、图形、装饰或插图，供后续元素图独立播放。\n"
    "9. 不要把元素图中的对象、动作或关系画进背景图。"
)
ELEMENT_IMAGE_PROMPT = (
    "#元素图生成\n"
    "#图片内容\n{content}\n"
    "#背景\n"
    "1. 我是一名计算机资深从业者，硕士毕业，从事多年软件技术研发。\n"
    "2. 现在想做抖音自媒体短视频。通过将科普知识以专业白板形式讲出来。\n"
    "#目标\n"
    "1. 请按提示词做 MG 动画风格的图片。\n"
    "2. 图片中的元素风格像 Excalidraw 生成的一样。\n"
    "#要求\n"
    "1. 图片中不要出现 Excalidraw 字样。\n"
    "2. 图片是纯白色背景。\n"
    "3. 画笔线条稍微粗一些。\n"
    "4. 元素图生成要在图中合适位置增加关键字。"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为 src 元素表生成文生图提示词和 asset_path。")
    parser.add_argument("element_csv", type=Path)
    parser.add_argument("--prompt-output", type=Path, help="默认 image_prompts_plus.csv")
    parser.add_argument("--element-output", type=Path, help="默认 element_timeline_with_assets.csv")
    parser.add_argument("--asset-dir", type=Path, help="默认 element CSV 同目录 generated_assets_plus/")
    parser.add_argument(
        "--image-source",
        choices=("generate", "library"),
        default="generate",
        help="generate: 写入待生成图片路径；library: 优先从 mg_asset_library/images 匹配现有图片。",
    )
    parser.add_argument("--asset-library", type=Path, default=DEFAULT_ASSET_LIBRARY, help="素材库图片目录，默认 mg_asset_library/images")
    parser.add_argument("--width", type=int, default=0, help=f"默认竖屏：{DEFAULT_IMAGE_WIDTH}；横屏：{LANDSCAPE_IMAGE_WIDTH}")
    parser.add_argument("--height", type=int, default=0, help=f"默认竖屏：{DEFAULT_IMAGE_HEIGHT}；横屏：{LANDSCAPE_IMAGE_HEIGHT}")
    parser.add_argument("--model", default="", help="兼容参数；所有模型统一使用纯色背景提示词")
    parser.add_argument("--theme", default="white", help="固定为白色板书主题")
    parser.add_argument("--orientation", default="", help="画布方向：portrait/landscape 或 竖屏/横屏")
    parser.add_argument(
        "--mode",
        choices=("jianying", "remotion"),
        default="jianying",
        help="素材策略；remotion 为每个场景输出一张合成图，剪映模式保持背景+元素多图",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        load_env_file(PROJECT_ROOT / ".env")
        element_csv = args.element_csv.expanduser().resolve()
        asset_dir = args.asset_dir.expanduser().resolve() if args.asset_dir else element_csv.with_name("generated_assets_plus")
        prompt_output = args.prompt_output.expanduser().resolve() if args.prompt_output else element_csv.with_name("image_prompts_plus.csv")
        element_output = args.element_output.expanduser().resolve() if args.element_output else element_csv.with_name("element_timeline_with_assets.csv")
        rows = read_elements(element_csv)
        if args.mode == "remotion":
            rows = collapse_remotion_rows(rows)
        library_assets = scan_asset_library(args.asset_library.expanduser().resolve()) if args.image_source == "library" else []
        asset_dir.mkdir(parents=True, exist_ok=True)
        default_width, default_height = default_image_size(args.orientation)

        prompt_rows: list[dict[str, object]] = []
        output_rows: list[dict[str, str]] = []
        for row in rows:
            new_row = {field: row.get(field, "") for field in ELEMENT_INPUT_FIELDS}
            new_row["asset_path"] = row.get("asset_path", "")
            if row["type"] == "image":
                width = make_even(args.width or default_width)
                height = make_even(args.height or default_height)
                is_background = row["role"] == "background"
                library_match = (
                    match_library_asset(row["content"], library_assets)
                    if library_assets and not is_background else None
                )
                asset_path = library_match or asset_dir / safe_filename(row["shot_id"], row["element_id"], row["content"])
                prompt = build_prompt(
                    element_id=row["element_id"], role=row["role"], content=row["content"],
                    shot_text="", width=width, height=height,
                    visual_theme=args.theme, orientation=args.orientation,
                )
                new_row["asset_path"] = str(asset_path)
                if library_match is None:
                    prompt_rows.append(
                        {
                            "element_id": row["element_id"],
                            "shot_id": row["shot_id"],
                            "role": row["role"],
                            "content": row["content"],
                            "width": width,
                            "height": height,
                            "asset_path": str(asset_path),
                            "prompt": prompt,
                        }
                    )
            output_rows.append(new_row)

        write_csv(prompt_output, PROMPT_FIELDS, prompt_rows)
        write_csv(element_output, ELEMENT_ASSET_FIELDS, output_rows)
    except Exception as exc:
        print(f"错误：{exc}")
        return 1

    print(f"生图提示词 CSV: {prompt_output}")
    print(f"带素材路径元素 CSV: {element_output}")
    return 0


def collapse_remotion_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Collapse one Jianying storyboard into one composite image per shot.

    Step 04 still produces the detailed semantic plan. Remotion only needs a
    single visual anchor per camera shot, so the image model receives the
    background summary and all element descriptions in one prompt.
    """
    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for row in rows:
        shot_id = row["shot_id"]
        if shot_id not in grouped:
            grouped[shot_id] = []
            order.append(shot_id)
        grouped[shot_id].append(row)

    collapsed: list[dict[str, str]] = []
    for shot_id in order:
        shot_rows = grouped[shot_id]
        background = next((row for row in shot_rows if row["role"] == "background"), None)
        elements = [row for row in shot_rows if row["role"] == "element"]
        if background is None and not elements:
            raise ValueError(f"Shot {shot_id} 没有可用的视觉内容")
        source = background or elements[0]
        parts: list[str] = []
        if background is not None:
            parts.append(f"场景背景与标题：{_compact_remotion_text(background['content'], 170)}")
        if elements:
            descriptions = "；".join(_compact_remotion_text(row["content"], 120) for row in elements)
            parts.append(f"同一画面中的主体和关系：{descriptions}")
        content = _compact_remotion_text("；".join(parts), 500)
        collapsed.append({
            "element_id": f"s{shot_id}_img01",
            "shot_id": shot_id,
            "type": "image",
            "role": "element",
            "content": content,
            "start_ms": source["start_ms"],
            "end_ms": source["end_ms"],
        })
    return collapsed


def _compact_remotion_text(value: str, limit: int) -> str:
    value = visual_only_content(value)
    return value if len(value) <= limit else value[: max(1, limit - 1)].rstrip("，。；、 ") + "…"


def read_elements(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames not in (
            ELEMENT_INPUT_FIELDS, ELEMENT_ASSET_FIELDS,
            LEGACY_ELEMENT_INPUT_FIELDS, LEGACY_ELEMENT_ASSET_FIELDS,
        ):
            raise ValueError(f"元素 CSV 列名不匹配：{reader.fieldnames}")
        rows = [
            {key: (row.get(key) or "").strip() for key in [*ELEMENT_INPUT_FIELDS, "asset_path"]}
            for row in reader
        ]
    if not rows:
        raise ValueError(f"元素 CSV 没有有效行：{path}")
    for row in rows:
        if not row["role"]:
            row["role"] = legacy_role(row["element_id"], row["type"])
    return rows


def build_prompt(
    *,
    element_id: str = "",
    role: str = "",
    content: str,
    shot_text: str,
    width: int,
    height: int,
    visual_theme: str = "",
    orientation: str = "",
) -> str:
    # Keep these arguments in the public API for callers and tests.  They are
    # deliberately not used to rewrite content: Step 05 is style-only.
    del shot_text, width, height
    design = visual_only_content(content)
    resolved_role = role or legacy_role(element_id, "image")
    if resolved_role in {"overview_diagram", "subpoint_diagram"}:
        resolved_role = "element"
    if resolved_role not in {"background", "element"}:
        raise ValueError(f"图片元素 role 不支持生图：{resolved_role or '<empty>'}")
    canvas = "16:9 横屏" if normalize_orientation(orientation) == "landscape" else "竖屏"
    template = BACKGROUND_IMAGE_PROMPT if resolved_role == "background" else ELEMENT_IMAGE_PROMPT
    prompt = build_structured_prompt(template, design, canvas)
    del visual_theme
    return prompt



def build_structured_prompt(template: str, content: str, canvas: str) -> str:
    """Keep the Step 04 content and every # section intact."""
    before, marker, after = template.partition("{content}")
    if not marker:
        raise ValueError("生图提示词模板缺少 {content} 占位符")
    prompt = f"#画布\n{canvas}\n" + before + content + after
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(
            f"完整生图提示词共 {len(prompt)} 字符，超过接口限制 {MAX_PROMPT_CHARS}；"
            "第05步不会截断第04步生成的图片内容"
        )
    return prompt


def compact_prompt(
    prompt: str,
    max_chars: int = MAX_PROMPT_CHARS,
    visual_theme: str = "",
) -> str:
    """Keep prompts below the image service limit without mixing in older prompt rules."""
    del visual_theme
    prompt = normalize_prompt(prompt.strip())
    if len(prompt) <= max_chars:
        return prompt
    return prompt[:max_chars].rstrip()


def normalize_prompt(prompt: str, *, visual_theme: str = "") -> str:
    """Normalize whitespace only; older prompt fragments are intentionally not reused."""
    del visual_theme
    return prompt.strip()


def visual_only_content(content: str) -> str:
    """Preserve the model-authored design; only normalize whitespace."""
    return re.sub(r"\s+", " ", content).strip()


def is_background_prompt(prompt: str) -> bool:
    return (
        "#元素图生成" not in prompt
        and (
            "#背景图生成" in prompt
            or
            "分镜设计：" in prompt
            or "背景内容设计：" in prompt
            or "分镜背景图" in prompt
            or "场景背景图" in prompt
            or "标题设计成醒目的大标题" in prompt
        )
    )


def is_background_element(element_id: str) -> bool:
    return bool(re.search(r"_bg\d+$", element_id.strip(), re.IGNORECASE))


def legacy_role(element_id: str, element_type: str) -> str:
    if element_type != "image":
        return ""
    return "background" if is_background_element(element_id) else "element"


def calculated_default_size() -> tuple[int, int]:
    return DEFAULT_IMAGE_WIDTH, DEFAULT_IMAGE_HEIGHT


def default_image_size(orientation: str = "") -> tuple[int, int]:
    if normalize_orientation(orientation) == "landscape":
        return LANDSCAPE_IMAGE_WIDTH, LANDSCAPE_IMAGE_HEIGHT
    return DEFAULT_IMAGE_WIDTH, DEFAULT_IMAGE_HEIGHT


def safe_filename(shot_id: str, element_id: str, content: str) -> str:
    del content
    name = element_id.strip() or f"s{shot_id}_image"
    name = re.sub(r'[^A-Za-z0-9_-]+', "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return f"{name}.png"


def scan_asset_library(root: Path) -> list[Path]:
    if not root.exists():
        return []
    suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def match_library_asset(content: str, assets: list[Path]) -> Path | None:
    content_name = normalize_asset_name(content)
    if not content_name:
        return None
    best_path: Path | None = None
    best_score = 0.0
    for path in assets:
        label = normalize_asset_name(path.stem)
        if not label:
            continue
        if content_name != label and is_complex_asset_request(content):
            continue
        score = asset_match_score(content_name, label)
        if score > best_score:
            best_score = score
            best_path = path
    return best_path if best_score >= 1.0 else None


def normalize_asset_name(text: str) -> str:
    cleaned = re.sub(r"[_-]?\d+x\d+", "", text)
    cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z]+", "", cleaned)
    stop_words = [
        "一个",
        "一颗",
        "一张",
        "一只",
        "一位",
        "两个",
        "表情",
        "标签",
        "文字",
        "画面",
        "示意图",
        "价格",
    ]
    for word in stop_words:
        cleaned = cleaned.replace(word, "")
    return cleaned


def is_complex_asset_request(text: str) -> bool:
    complex_markers = [
        "价格",
        "标签",
        "数字",
        "买",
        "购",
        "花",
        "总",
        "平均",
        "成本",
        "示意",
        "操作",
        "箭头",
        "从",
        "到",
        "看着",
        "想着",
        "想",
        "和",
        "与",
    ]
    return any(marker in text for marker in complex_markers) or bool(re.search(r"\d", text))


def asset_match_score(content: str, label: str) -> float:
    if content == label:
        return 3.0
    if content in label and len(content) >= 2:
        return 2.0
    if label in content and len(content) <= len(label) + 3:
        return 1.5
    return 0.0


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
