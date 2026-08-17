"""Read generated-image review items without exposing processed images as originals."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ..prepare.image_generation import original_image_path
from ..prepare.image_prompts import PROMPT_FIELDS


@dataclass(frozen=True)
class ImageReviewItem:
    element_id: str
    content: str
    asset_path: Path
    original_path: Path


def load_image_review_items(prompt_csv: Path, project_root: Path) -> list[ImageReviewItem]:
    prompt_csv = prompt_csv.expanduser().resolve()
    with prompt_csv.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != PROMPT_FIELDS:
            raise ValueError(f"提示词 CSV 列名不匹配：{reader.fieldnames}")
        rows = list(reader)

    items: list[ImageReviewItem] = []
    for row in rows:
        element_id = (row.get("element_id") or "").strip()
        raw_asset_path = (row.get("asset_path") or "").strip()
        if not element_id or not raw_asset_path:
            continue
        asset_path = Path(raw_asset_path).expanduser()
        if not asset_path.is_absolute():
            asset_path = (project_root / asset_path).resolve()
        items.append(ImageReviewItem(
            element_id=element_id,
            content=(row.get("content") or "").strip(),
            asset_path=asset_path,
            original_path=original_image_path(asset_path),
        ))
    return items
