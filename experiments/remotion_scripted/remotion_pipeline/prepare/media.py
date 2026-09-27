from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from ..contracts import VISUAL_STYLE_ID
from .image_style import build_image_prompt


def normalize_white_background(path: Path) -> None:
    """Keep the Jianying asset contract: opaque white, no accidental cutout."""
    with Image.open(path) as source:
        image = source.convert("RGBA")
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        background.alpha_composite(image)
        background.convert("RGB").save(path, format="PNG", optimize=True)


def generate_image(shot: dict[str, Any], output: Path, values: dict[str, str]) -> None:
    key = values.get("IMAGE_API_KEY")
    if not key:
        raise ValueError("image generation requires IMAGE_API_KEY")
    base = values.get("IMAGE_BASE_URL", "https://api.mpltop.xyz/v1").rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    prompt = build_image_prompt(shot)
    request = {
        "model": values.get("IMAGE_MODEL", "gpt-image-2"),
        "prompt": prompt,
        "size": "1536x864",
        "quality": values.get("IMAGE_QUALITY", values.get("REMOTION_IMAGE_QUALITY", "high")),
        "n": 1,
    }
    response = None
    for attempt in range(3):
        response = requests.post(
            f"{base}/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            json=request,
            timeout=(20, 180),
        )
        if response.status_code < 500:
            break
        if attempt < 2:
            time.sleep(2 ** attempt)
    assert response is not None
    response.raise_for_status()
    item = response.json()["data"][0]
    output.parent.mkdir(parents=True, exist_ok=True)
    if item.get("b64_json"):
        output.write_bytes(base64.b64decode(item["b64_json"]))
        return
    if item.get("url"):
        image_response = requests.get(item["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=180)
        image_response.raise_for_status()
        output.write_bytes(image_response.content)
        return
    raise RuntimeError("image endpoint response contained neither b64_json nor url")


def prepare_media(shots: list[dict[str, Any]], output_dir: Path, values: dict[str, str], reuse: bool = False) -> dict[str, dict[str, str]]:
    media: dict[str, dict[str, str]] = {}
    for index, shot in enumerate(shots):
        if shot.get("asset_type") == "video" and shot.get("source"):
            source = Path(str(shot["source"])).expanduser().resolve()
            if not source.is_file():
                raise FileNotFoundError(f"video source does not exist: {source}")
            rel = f"videos/{source.name}"
            target = output_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            media[shot["id"]] = {"asset": rel, "mediaType": "video", "assetSource": "user_video", "styleId": VISUAL_STYLE_ID, "cacheBust": str(target.stat().st_mtime_ns)}
            continue
        rel = f"shot_{index + 1:02d}.png"
        target = output_dir / "assets" / rel
        if not (reuse and target.is_file()):
            generate_image(shot, target, values)
        normalize_white_background(target)
        media[shot["id"]] = {"asset": rel, "mediaType": "image", "assetSource": "cached" if reuse else "image_model", "styleId": VISUAL_STYLE_ID, "assetCount": 1, "cacheBust": str(target.stat().st_mtime_ns)}
    return media
