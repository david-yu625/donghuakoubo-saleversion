"""Prepare the project-wide background used by the draft renderer."""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps


BACKGROUND_SIZE = (1080, 1920)
BACKGROUND_NAME = "background_1080x1920.png"


def ensure_solid_background(
    project_dir: Path,
    *,
    size: tuple[int, int],
    color: str = "#000000",
) -> Path:
    """Create a deterministic project-local solid background for packaging."""
    safe_color = color.lstrip("#")
    if len(safe_color) != 6:
        raise ValueError("solid background color must be a six-digit hex value")
    target = project_dir / "prepared_assets" / f"solid_{safe_color.lower()}_{size[0]}x{size[1]}.png"
    if valid_background(target, size):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, f"#{safe_color}").save(target, format="PNG", optimize=True)
    return target


def ensure_project_background(
    project_dir: Path,
    project_root: Path,
    *,
    source: Path | None = None,
    size: tuple[int, int] = BACKGROUND_SIZE,
) -> Path:
    target = project_dir / "prepared_assets" / background_name(size)
    if source is not None:
        source = source.expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"背景文件不存在：{source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            prepared = ImageOps.fit(image.convert("RGB"), size, Image.Resampling.LANCZOS)
        prepared.save(target, format="PNG", optimize=True)
        return target

    reference = project_root / "src" / "demos" / "background_1_1080x1920.png"
    if size == BACKGROUND_SIZE and valid_background(reference, size):
        target.parent.mkdir(parents=True, exist_ok=True)
        if not valid_background(target, size) or not filecmp.cmp(reference, target, shallow=False):
            shutil.copy2(reference, target)
        return target
    if valid_background(target, size):
        return target

    source = project_root / "mg_asset_library" / "background" / "background_1.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        with Image.open(source) as image:
            texture = ImageOps.fit(image.convert("RGB"), size, Image.Resampling.LANCZOS)
            texture = ImageOps.autocontrast(ImageOps.grayscale(texture), cutoff=2)
    else:
        texture = Image.new("L", size, 128)
        draw = ImageDraw.Draw(texture)
        for offset in range(-size[1], size[0], 96):
            draw.line((offset, 0, offset + size[1], size[1]), fill=124, width=2)

    colored = ImageOps.colorize(texture, black="#1E2B28", white="#52615A")
    colored = ImageEnhance.Contrast(colored).enhance(0.72)
    colored = Image.blend(Image.new("RGB", size, "#34423D"), colored, 0.42)
    colored.save(target, optimize=True)
    return target


def background_name(size: tuple[int, int]) -> str:
    if size == BACKGROUND_SIZE:
        return BACKGROUND_NAME
    return f"background_{size[0]}x{size[1]}.png"


def valid_background(path: Path, size: tuple[int, int] = BACKGROUND_SIZE) -> bool:
    if not path.exists():
        return False
    try:
        with Image.open(path) as image:
            return image.size == size and image.mode == "RGB"
    except OSError:
        return False
