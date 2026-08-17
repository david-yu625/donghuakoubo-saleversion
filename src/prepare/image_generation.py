"""Text-to-image service for the src workflow."""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

from openai import OpenAI
from PIL import Image, ImageChops

DEFAULT_IMAGE_BASE_URL = "https://api.mpltop.xyz/v1"
DEFAULT_JIMENG_MODEL = "jimeng_seedream46_cvtob"
DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-2"
DEFAULT_IMAGE_MODEL = DEFAULT_JIMENG_MODEL
BACKGROUND_CONTENT_BOUNDS_NAME = "background_content_bounds.json"
BACKGROUND_CONTENT_THRESHOLD = 24
IMAGE_MODEL_CHOICES = (DEFAULT_JIMENG_MODEL, DEFAULT_OPENAI_IMAGE_MODEL)
OPENAI_COMPATIBLE_HEADERS = {
    # The configured image proxy blocks the OpenAI SDK's default user agent at Cloudflare.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36",
}
ORIGINALS_FOLDER_NAME = "originals"


def visual_service():
    try:
        from volcengine.visual.VisualService import VisualService
    except ModuleNotFoundError as exc:
        raise RuntimeError("缺少 volcengine SDK，请先运行: pip install volcengine") from exc

    access_key = os.getenv("VOLC_ACCESSKEY") or os.getenv("VOLC_AK")
    secret_key = os.getenv("VOLC_SECRETKEY") or os.getenv("VOLC_SK")
    if not access_key or not secret_key:
        raise RuntimeError("缺少鉴权信息，请在 .env 中设置 VOLC_ACCESSKEY 和 VOLC_SECRETKEY")

    service = VisualService()
    service.set_ak(access_key)
    service.set_sk(secret_key)
    return service


def generate_image(
    *,
    prompt: str,
    output_path: Path,
    width: int,
    height: int,
    req_key: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
    quality: str = "",
    visual_theme: str = "",
    max_attempts: int = 3,
    retry_delay_seconds: float = 2.0,
) -> Path:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("提示词不能为空")
    if width <= 0 or height <= 0:
        raise ValueError("图片宽高必须大于 0")
    if max_attempts <= 0:
        raise ValueError("最大尝试次数必须大于 0")

    selected_model = resolve_image_model(model or req_key)
    use_jimeng = bool(req_key.strip() and not model.strip()) or is_jimeng_model(selected_model)
    if use_jimeng:
        if len(prompt) > 800:
            raise ValueError("生图提示词超过即梦接口的 800 字符限制")
        image_bytes = generate_jimeng_image_bytes(
            prompt=prompt,
            width=width,
            height=height,
            req_key=selected_model,
            max_attempts=max_attempts,
            retry_delay_seconds=retry_delay_seconds,
        )
    else:
        image_bytes = generate_openai_image_bytes(
            prompt=prompt,
            width=width,
            height=height,
            model=selected_model,
            api_key=api_key or os.getenv("IMAGE_API_KEY", ""),
            base_url=base_url or os.getenv("IMAGE_BASE_URL", DEFAULT_IMAGE_BASE_URL),
            quality=quality or os.getenv("IMAGE_QUALITY", ""),
            max_attempts=max_attempts,
            retry_delay_seconds=retry_delay_seconds,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = original_image_path(output_path)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(image_bytes)
    del visual_theme
    is_shot_background = is_shot_background_prompt(prompt)
    if is_shot_background:
        preserve_white_background(source_path, output_path, width=width, height=height)
        record_background_content_bounds(output_path)
        validate_white_background_png(output_path)
    else:
        crop_white_background(source_path, output_path)
        validate_white_background_png(output_path)
    return output_path


def original_image_path(output_path: Path) -> Path:
    return output_path.parent / ORIGINALS_FOLDER_NAME / output_path.name


def is_valid_image_file(path: Path) -> bool:
    """Return whether a generated asset is a readable, non-empty image."""
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
        with Image.open(path) as image:
            image.verify()
    except (OSError, SyntaxError, ValueError):
        return False
    return True


def resolve_image_model(value: str = "") -> str:
    return (
        value.strip()
        or os.getenv("IMAGE_MODEL", "").strip()
        or os.getenv("JIMENG_REQ_KEY", "").strip()
        or DEFAULT_IMAGE_MODEL
    )


def is_jimeng_model(model: str) -> bool:
    return model.strip().lower().startswith("jimeng_")


def is_shot_background_prompt(prompt: str) -> bool:
    return (
        "#元素图生成" not in prompt
        and "图片元素设计：" not in prompt
        and (
            "#背景图生成" in prompt
            or "#资产：分镜背景图" in prompt
            or "唯一允许出现的文字" in prompt
            or "分镜设计：" in prompt
            or "背景内容设计：" in prompt
            or "生成背景图" in prompt
            or "场景背景图" in prompt
            or "MG 动画风格的背景图" in prompt
        )
    )


def uses_white_background_prompt(prompt: str) -> bool:
    return any(
        marker in prompt
        for marker in (
            "纯白色背景",
            "背景保持纯白色",
            "白色背景",
        )
    )


def generate_jimeng_image_bytes(
    *,
    prompt: str,
    width: int,
    height: int,
    req_key: str,
    max_attempts: int,
    retry_delay_seconds: float,
) -> bytes:
    service = visual_service()
    request = {
        "req_key": req_key,
        "prompt": prompt,
        "sequential_image_generation": "auto",
        "max_images": 1,
        "width": width,
        "height": height,
        "watermark": False,
        "force_single": False,
    }
    for attempt in range(1, max_attempts + 1):
        try:
            response = service.cv_process(request)
            break
        except Exception:
            if attempt >= max_attempts:
                raise
            print(f"图片生成请求失败，{retry_delay_seconds:g} 秒后重试（{attempt}/{max_attempts}）")
            time.sleep(retry_delay_seconds)
    if response.get("code") != 10000:
        raise RuntimeError(f"图片生成失败: {response}")
    images = response.get("data", {}).get("binary_data_base64", [])
    if not images:
        raise RuntimeError("图片生成成功，但接口没有返回图片数据")
    return base64.b64decode(images[0].split(",", 1)[-1])


def generate_openai_image_bytes(
    *,
    prompt: str,
    width: int,
    height: int,
    model: str,
    api_key: str,
    base_url: str,
    quality: str,
    max_attempts: int,
    retry_delay_seconds: float,
) -> bytes:
    if not api_key.strip():
        raise ValueError("缺少 IMAGE_API_KEY")
    client = OpenAI(
        api_key=api_key.strip(),
        base_url=normalize_base_url(base_url),
        timeout=180.0,
        default_headers=OPENAI_COMPATIBLE_HEADERS,
    )
    request: dict[str, object] = {
        "model": model,
        "prompt": prompt,
        "size": f"{width}x{height}",
        "n": 1,
    }
    if quality.strip():
        request["quality"] = quality.strip()

    image_url = ""
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.images.generate(**request)
            if not response.data:
                raise RuntimeError("接口响应成功，但没有返回图片数据")
            image = response.data[0]
            b64_json = getattr(image, "b64_json", None)
            if b64_json:
                return base64.b64decode(b64_json)
            image_url = getattr(image, "url", None)
            if image_url:
                break
            raise RuntimeError("接口没有返回 b64_json 或图片 URL")
        except Exception:
            if attempt >= max_attempts:
                raise
            print(f"图片生成请求失败，{retry_delay_seconds:g} 秒后重试（{attempt}/{max_attempts}）")
            time.sleep(retry_delay_seconds)
    return download_image_bytes(
        image_url,
        max_attempts=max_attempts,
        retry_delay_seconds=retry_delay_seconds,
    )


def download_image_bytes(
    image_url: str,
    *,
    max_attempts: int,
    retry_delay_seconds: float,
) -> bytes:
    """Download a generated image without paying for another generation retry."""
    request = Request(
        image_url,
        headers={
            **OPENAI_COMPATIBLE_HEADERS,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=120) as download:
                return download.read()
        except Exception:
            if attempt >= max_attempts:
                raise
            print(f"图片下载失败，{retry_delay_seconds:g} 秒后重试（{attempt}/{max_attempts}）")
            time.sleep(retry_delay_seconds)
    raise RuntimeError("图片下载失败")
    raise RuntimeError("图片生成失败")


def normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not base_url:
        raise ValueError("IMAGE_BASE_URL 不能为空")
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


def crop_white_background(source_path: Path, output_path: Path) -> None:
    """Crop unused white canvas while preserving an opaque white background."""
    with Image.open(source_path) as source:
        image = source.convert("RGB")
        image.load()

    image = normalize_near_white_background(image)

    white = Image.new("RGB", image.size, "#ffffff")
    difference = ImageChops.difference(image, white).convert("L")
    content_mask = difference.point(lambda value: 255 if value > 10 else 0)
    bbox = content_mask.getbbox()
    if bbox is None:
        raise RuntimeError(f"白底图片没有可识别主体：{source_path}")
    # Keep only a tiny antialiasing margin; layout should size the visible
    # subject, not a generated white frame around it.
    padding = 2
    content = image.crop(bbox)
    padded = Image.new(
        "RGB",
        (content.width + padding * 2, content.height + padding * 2),
        "#ffffff",
    )
    padded.paste(content, (padding, padding))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    padded.save(output_path, format="PNG", optimize=True)


def normalize_near_white_background(image: Image.Image) -> Image.Image:
    """Turn neutral near-white paper texture into white without bleaching color fills."""
    red, green, blue = image.convert("RGB").split()
    minimum = ImageChops.darker(ImageChops.darker(red, green), blue)
    maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    bright = minimum.point(lambda value: 255 if value >= 238 else 0)
    neutral = ImageChops.subtract(maximum, minimum).point(lambda value: 255 if value <= 18 else 0)
    mask = ImageChops.multiply(bright, neutral)
    result = image.convert("RGB")
    result.paste("#ffffff", mask=mask)
    return result


def flatten_white_background(source_path: Path, output_path: Path) -> None:
    """Flatten an image onto opaque white without removing any white pixels."""
    with Image.open(source_path) as source:
        rgba = source.convert("RGBA")
        rgba.load()
    white = Image.new("RGBA", rgba.size, "#ffffff")
    white.alpha_composite(rgba)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    white.convert("RGB").save(output_path, format="PNG", optimize=True)


def preserve_white_background(
    source_path: Path,
    output_path: Path,
    *,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Preserve the complete generated background on the requested white canvas."""
    with Image.open(source_path) as source:
        image = source.convert("RGB")
        image.load()
    image = normalize_near_white_background(image)
    target_width = width or image.width
    target_height = height or image.height
    image.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_width, target_height), "#ffffff")
    left = (target_width - image.width) // 2
    top = (target_height - image.height) // 2
    canvas.paste(image, (left, top))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=True)


def background_content_bottom_ratio(path: Path) -> float:
    """Return the lower edge of non-white background content as a canvas ratio."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.load()
    difference = ImageChops.difference(image, Image.new("RGB", image.size, "#ffffff")).convert("L")
    mask = difference.point(lambda value: 255 if value > BACKGROUND_CONTENT_THRESHOLD else 0)
    bbox = mask.getbbox()
    return 0.0 if bbox is None else round(bbox[3] / image.height, 6)


def record_background_content_bounds(path: Path) -> None:
    """Persist generated background content bounds for the following layout step."""
    manifest_path = path.parent / BACKGROUND_CONTENT_BOUNDS_NAME
    data: dict[str, dict[str, float]] = {}
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            data = {}
    data[path.name] = {"content_bottom_ratio": background_content_bottom_ratio(path)}
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_white_background_png(path: Path) -> None:
    with Image.open(path) as image:
        if image.mode != "RGB":
            raise RuntimeError(f"白底裁边结果不是 RGB：{path}")
        if image.width < 2 or image.height < 2:
            raise RuntimeError(f"白底裁边结果尺寸无效：{path}")
