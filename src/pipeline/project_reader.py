"""Read existing project files into scene source rows."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from ..security_guard.secure_files import read_text as secure_read_text


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
    shots = read_shots(project_dir / "shot_timeline_source_time.csv")
    elements = read_elements(project_dir / "element_timeline_with_assets.csv")
    validate_element_timing(elements, shots)
    copy_lines = read_copy_lines(project_dir / "wenan.txt")
    return ProjectSource(
        project_dir=project_dir,
        element_rows=assign_fallback_assets(elements, project_dir),
        shot_rows=shots,
        subtitle_rows=read_subtitles(project_dir / "timeline.csv", copy_lines),
        copy_lines=copy_lines,
    )


def validate_element_timing(
    elements: list[dict[str, str]],
    shots: list[dict[str, str]],
) -> None:
    """Reject an element table generated for a different shot timeline.

    Step 07 combines these two CSVs.  A stale element table otherwise fails much
    later in the layout builder with an opaque out-of-range error.
    """
    shot_ranges: dict[str, tuple[int, int]] = {}
    for shot in shots:
        shot_id = (shot.get("shot_id") or "").strip()
        try:
            shot_ranges[shot_id] = (int(shot["开始时间ms"]), int(shot["结束时间ms"]))
        except (KeyError, TypeError, ValueError):
            # read_shots/build_scene_facts will report malformed shot data in
            # its normal validation path.
            continue

    for row in elements:
        shot_id = (row.get("shot_id") or "").strip()
        element_id = (row.get("element_id") or "").strip()
        if shot_id not in shot_ranges:
            raise ValueError(
                "element_timeline_with_assets.csv 与最新分镜不一致："
                f"元素 {element_id or '<未知>'} 引用了不存在的 Shot {shot_id or '<空>'}。"
                "请重新运行第05步（生图提示词）后再编译。"
            )
        try:
            start_ms = int(row.get("start_ms", "") or 0)
            end_ms = int(row.get("end_ms", "") or 0)
        except (TypeError, ValueError):
            raise ValueError(
                "element_timeline_with_assets.csv 时间格式无效："
                f"元素 {element_id or '<未知>'}。请重新运行第05步（生图提示词）后再编译。"
            ) from None
        shot_start, shot_end = shot_ranges[shot_id]
        if start_ms < shot_start or end_ms > shot_end or end_ms <= start_ms:
            raise ValueError(
                "element_timeline_with_assets.csv 与最新分镜时间范围不一致："
                f"Shot {shot_id} 元素 {element_id or '<未知>'} 为 {start_ms}-{end_ms}，"
                f"当前分镜范围为 {shot_start}-{shot_end}。"
                "请重新运行第05步（生图提示词）后再编译。"
            )


def read_copy_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in secure_read_text(path).splitlines() if line.strip()]


def read_rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(secure_read_text(path))))


def read_shots(path: Path) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(secure_read_text(path)))
    if reader.fieldnames != SHOT_FIELDS:
        raise ValueError(f"Shot CSV 列名不匹配：{reader.fieldnames}")
    rows = list(reader)
    return sorted(rows, key=lambda row: int(row["开始时间ms"]))


def read_elements(path: Path) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(secure_read_text(path)))
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
    reader = csv.reader(io.StringIO(secure_read_text(path)))
    next(reader, None)
    for parts in reader:
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
