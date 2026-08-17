"""Read existing project files into scene source rows."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


TIME_RE = re.compile(r"\[\s*([0-9.]+)\s*,\s*([0-9.]+)")
ELEMENT_FIELDS = [
    "element_id",
    "shot_id",
    "type",
    "role",
    "content",
    "start_ms",
    "end_ms",
    "asset_path",
]
LEGACY_ELEMENT_FIELDS = [field for field in ELEMENT_FIELDS if field != "role"]
SHOT_FIELDS = ["shot_id", "分镜标题", "开始时间ms", "结束时间ms", "分镜对应原始文案内容"]


@dataclass(frozen=True)
class ProjectSource:
    project_dir: Path
    element_rows: list[dict[str, str]]
    shot_rows: list[dict[str, str]]
    subtitle_rows: list[tuple[str, int, int]]
    copy_lines: list[str]


def load_project(project_dir: Path) -> ProjectSource:
    project_dir = project_dir.expanduser().resolve()
    elements = read_elements(project_dir / "element_timeline_with_assets.csv")
    copy_lines = read_copy_lines(project_dir / "wenan.txt")
    return ProjectSource(
        project_dir=project_dir,
        element_rows=assign_fallback_assets(elements, project_dir),
        shot_rows=read_shots(project_dir / "shot_timeline_source_time.csv"),
        subtitle_rows=read_subtitles(project_dir / "timeline.csv", copy_lines),
        copy_lines=copy_lines,
    )


def read_copy_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_shots(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != SHOT_FIELDS:
            raise ValueError(f"Shot CSV 列名不匹配：{reader.fieldnames}")
        rows = list(reader)
    return sorted(rows, key=lambda row: int(row["开始时间ms"]))


def read_elements(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames not in (ELEMENT_FIELDS, LEGACY_ELEMENT_FIELDS):
            raise ValueError(f"元素素材 CSV 列名不匹配：{reader.fieldnames}")
        rows = list(reader)
    for row in rows:
        row["role"] = (row.get("role") or "").strip()
    return sorted(
        rows,
        key=lambda row: (int(row["shot_id"]), int(row["start_ms"]), row["element_id"]),
    )


def read_subtitles(path: Path, copy_lines: list[str] | None = None) -> list[tuple[str, int, int]]:
    subtitles: list[tuple[str, int, int]] = []
    punctuation_map = {
        normalize_sentence(line): line
        for line in (copy_lines or [])
        if normalize_sentence(line)
    }
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        rows = reader
        for parts in rows:
            if len(parts) < 3:
                continue
            time_index = next(
                (index for index, value in enumerate(parts[1:], start=1) if value.lstrip().startswith("[")),
                2,
            )
            if time_index >= len(parts):
                continue
            text = ",".join(parts[1:time_index]).strip().strip("{}")
            time_value = ",".join(parts[time_index:])
            match = TIME_RE.search(time_value)
            if not match:
                continue
            text = punctuation_map.get(normalize_sentence(text), text)
            start_ms = round(float(match.group(1)) * 1000)
            end_ms = round(float(match.group(2)) * 1000)
            if text and end_ms > start_ms:
                subtitles.append((text, start_ms, end_ms))
    return subtitles


def normalize_sentence(text: str) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text)


def assign_fallback_assets(rows: list[dict[str, str]], project_dir: Path) -> list[dict[str, str]]:
    library_images: list[Path] | None = None
    next_rows: list[dict[str, str]] = []
    library_index = 0
    for row in rows:
        next_row = dict(row)
        if row["type"] != "image":
            next_rows.append(next_row)
            continue
        if row.get("role") == "background":
            next_rows.append(next_row)
            continue
        raw_path = (row.get("asset_path") or "").strip()
        if raw_path and Path(raw_path).exists():
            next_rows.append(next_row)
            continue
        if library_images is None:
            asset_library = next(
                (
                    parent / "mg_asset_library" / "images"
                    for parent in (project_dir, *project_dir.parents)
                    if (parent / "mg_asset_library" / "images").is_dir()
                ),
                None,
            )
            library_images = sorted(
                path for path in asset_library.rglob("*")
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ) if asset_library is not None else []
        if library_images:
            next_row["asset_path"] = str(library_images[library_index % len(library_images)])
            library_index += 1
        else:
            element_id = row.get("element_id", "").strip()
            candidates = sorted((project_dir / "placeholder_assets_plus").glob(f"{element_id}_*.png"))
            if candidates:
                next_row["asset_path"] = str(candidates[0])
        next_rows.append(next_row)
    return next_rows
