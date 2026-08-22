"""Generate a standalone cover image for a topic."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from PIL import Image

from ..env import load_env_file
from .image_generation import DEFAULT_IMAGE_MODEL, generate_image, resolve_image_model


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COVER_SIZE_OPTIONS = (
    ("portrait", "1080×1920（竖版）", 1080, 1920, "9:16", "竖版"),
    ("landscape", "1920×1080（横版）", 1920, 1080, "16:9", "横版"),
    ("square", "1080×1080（正方形）", 1080, 1080, "1:1", "正方形"),
    ("portrait_1440", "1080×1440（竖版）", 1080, 1440, "3:4", "竖版"),
)
COVER_SIZE_KEYS = tuple(item[0] for item in COVER_SIZE_OPTIONS)
COVER_WIDTH = COVER_SIZE_OPTIONS[0][2]
COVER_HEIGHT = COVER_SIZE_OPTIONS[0][3]
COVER_PROMPT_TEMPLATE = """#封面图生成
#画布
1. 生成一张 {width}×{height}、{ratio} 的{orientation}科普短视频作品封面。

#主题
主题文字：{topic}

#图片内容
围绕“{topic}”设计一幅具有明确主题含义的科普视觉画面。使用与主题直接相关的多个具体对象、结构或关系，形成一幅完整、易懂、有视觉冲击力的白板科普插画。突出主题核心，不加入无关装饰。

#视觉风格
MG 动画风格，手绘白板元素感，整体风格类似 Excalidraw 生成的手绘信息图。纯白色背景，黑色手绘线条，线条稍微粗一些，可以少量使用蓝色、黄色作为重点强调色。画面简洁、清晰，适合作品封面。

#文字要求
必须在图片上准确、完整、清晰地写出主题文字“{topic}”。主题文字放在画面上方或上方偏中间位置，字号醒目，保证 {width}×{height} 尺寸下清楚可读。主题文字可以使用黑色，并用蓝色或黄色突出最后几个字。除主题文字和少量必要关键词外，不要出现其他文字、乱码、英文或无意义字符。不要出现“Excalidraw”字样。

#构图要求
1. 在画面最外围绘制一个完整、清晰的黑色手绘圆角矩形边框。边框从画布四周向内缩约 3%，线条粗细与画面中的手绘线条协调，四个圆角弧度自然一致。边框不能贴边、缺角、断开或被画布裁切，不要添加阴影、双层边框或复杂装饰。
2. 主题文字和所有视觉内容必须完整放在圆角边框内部，并与边框保持舒适间距，任何文字和图形都不能压住或越过边框。
3. 主题文字位于顶部约五分之一区域。主题相关的主要视觉内容位于中部和下部，占据画面大部分空间。对象之间的关系要清楚，画面要有层次，不能只画孤立的小图标。不要留出大面积无意义空白，也不要让对象过小。
{context}"""


def safe_topic(value: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\s]+', "", value.strip())
    return name or "未命名主题"


def resolve_cover_size(value: str = "") -> tuple[str, str, int, int, str, str]:
    normalized = value.strip().casefold()
    for option in COVER_SIZE_OPTIONS:
        _key, label, width, height, _ratio, _orientation = option
        aliases = {
            _key.casefold(),
            label.casefold(),
            f"{width}x{height}",
            f"{width}*{height}",
            f"{width}×{height}",
        }
        if normalized in aliases:
            return option
    if not normalized:
        return COVER_SIZE_OPTIONS[0]
    raise ValueError(f"不支持的封面尺寸：{value}")


def build_cover_prompt(topic: str, context: str = "", cover_size: str = "") -> str:
    topic = topic.strip()
    if not topic:
        raise ValueError("主题不能为空")
    _key, _label, width, height, ratio, orientation = resolve_cover_size(cover_size)
    context_text = (
        f"\n#补充要求\n结合以下上下文理解主题，但不要把上下文原文直接写到图片上：{context.strip()}"
        if context.strip()
        else ""
    )
    return COVER_PROMPT_TEMPLATE.format(
        topic=topic,
        context=context_text,
        width=width,
        height=height,
        ratio=ratio,
        orientation=orientation,
    ).strip()


def default_cover_path(topic: str, output_root: Path | None = None, cover_size: str = "") -> Path:
    root = (output_root or PROJECT_ROOT / "output").expanduser().resolve()
    key, _label, width, height, _ratio, _orientation = resolve_cover_size(cover_size)
    del key
    return root / safe_topic(topic) / "cover" / f"{safe_topic(topic)}_cover_{width}x{height}.png"


def enforce_cover_dimensions(path: Path, width: int, height: int) -> Path:
    """Resize only the pixel dimensions, without cropping, padding, or color cleanup."""
    with Image.open(path) as source:
        source.load()
        if source.size == (width, height):
            return path
        original_size = source.size
        resized = source.resize((width, height), Image.Resampling.LANCZOS)
        temporary = path.with_name(f".{path.stem}.resize{path.suffix}")
        try:
            resized.save(temporary, format="PNG", optimize=True)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"封面像素校正：{original_size[0]}x{original_size[1]} -> {width}x{height}")
    return path


def generate_cover(
    *,
    topic: str,
    output_path: Path,
    context: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
    quality: str = "",
    visual_theme: str = "white",
    cover_size: str = "",
    overwrite: bool = False,
) -> Path:
    _key, _label, width, height, _ratio, _orientation = resolve_cover_size(cover_size)
    prompt = build_cover_prompt(topic, context, cover_size)
    output_path = output_path.expanduser().resolve()
    if output_path.is_file() and not overwrite:
        print(f"封面已存在，跳过：{output_path}")
        return output_path
    print(f"封面尺寸：{width}x{height}")
    print(f"图片模型：{resolve_image_model(model)}")
    print(f"生成封面：{topic} -> {output_path}")
    result = generate_image(
        prompt=prompt,
        output_path=output_path,
        width=width,
        height=height,
        model=model,
        api_key=api_key or os.getenv("IMAGE_API_KEY", ""),
        base_url=base_url or os.getenv("IMAGE_BASE_URL", ""),
        quality=quality or os.getenv("IMAGE_QUALITY", ""),
        visual_theme=visual_theme,
        postprocess=False,
    )
    return enforce_cover_dimensions(result, width, height)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成独立的多尺寸作品封面。")
    parser.add_argument("topic", help="封面主题")
    parser.add_argument("--output", type=Path, help="封面 PNG 输出路径")
    parser.add_argument("--context", default="", help="可选的主题上下文")
    parser.add_argument("--model", default="", help=f"图片模型，默认读取 IMAGE_MODEL 或 {DEFAULT_IMAGE_MODEL}")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--quality", default="")
    parser.add_argument("--theme", default="white")
    parser.add_argument("--size", choices=COVER_SIZE_KEYS, default=COVER_SIZE_KEYS[0])
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        load_env_file(PROJECT_ROOT / ".env")
        output = (
            args.output.expanduser().resolve()
            if args.output
            else default_cover_path(args.topic, cover_size=args.size)
        )
        generate_cover(
            topic=args.topic,
            output_path=output,
            context=args.context,
            model=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            quality=args.quality,
            visual_theme=args.theme,
            cover_size=args.size,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"错误：{exc}")
        return 1
    print(f"封面生成完成：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
