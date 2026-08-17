"""Discovery and persisted selection for landscape projects."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}


@dataclass(frozen=True)
class LandscapeProject:
    topic: str
    project_dir: Path
    timeline_path: Path
    modified_ns: int


@dataclass
class PortraitPackageState:
    selected_project: str = ""
    source_videos: dict[str, str] = field(default_factory=dict)


def discover_landscape_projects(output_root: Path) -> list[LandscapeProject]:
    """Return usable landscape projects, newest first, including legacy layouts."""
    output_root = output_root.expanduser().resolve()
    if not output_root.is_dir():
        return []

    projects: list[LandscapeProject] = []
    for topic_dir in output_root.iterdir():
        if not topic_dir.is_dir():
            continue
        scoped_dir = topic_dir / "landscape"
        if (scoped_dir / "timeline.csv").is_file():
            project_dir = scoped_dir
        elif (topic_dir / "timeline.csv").is_file():
            project_dir = topic_dir
        else:
            continue
        timeline_path = project_dir / "timeline.csv"
        modified_ns = max(
            [project_dir.stat().st_mtime_ns]
            + [path.stat().st_mtime_ns for path in project_dir.iterdir() if path.is_file()]
        )
        projects.append(LandscapeProject(
            topic=topic_dir.name,
            project_dir=project_dir.resolve(),
            timeline_path=timeline_path.resolve(),
            modified_ns=modified_ns,
        ))
    return sorted(projects, key=lambda item: (-item.modified_ns, item.topic.casefold()))


def load_portrait_package_state(path: Path) -> PortraitPackageState:
    path = path.expanduser().resolve()
    if not path.is_file():
        return PortraitPackageState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        package = payload.get("portrait_package", {})
        videos = package.get("source_videos", {})
        return PortraitPackageState(
            selected_project=str(package.get("selected_project", "")),
            source_videos={str(key): str(value) for key, value in videos.items()},
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return PortraitPackageState()


def save_portrait_package_state(path: Path, state: PortraitPackageState) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "portrait_package": {
            "selected_project": state.selected_project,
            "source_videos": state.source_videos,
        }
    }
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def find_matching_landscape_video(
    project: LandscapeProject,
    *,
    project_root: Path,
    home: Path | None = None,
) -> Path | None:
    """Find the newest likely export without selecting an unrelated video."""
    project_root = project_root.expanduser().resolve()
    home = (home or Path.home()).expanduser().resolve()
    topic_root = project.project_dir.parent if project.project_dir.name == "landscape" else project.project_dir
    search_roots = [
        (topic_root, True),
        (project_root / "exports", True),
        (project_root, False),
        (home / "Videos", False),
        (home / "Desktop", False),
        (home / "Downloads", False),
    ]

    candidates: dict[Path, int] = {}
    for root, recursive in search_roots:
        if not root.is_dir():
            continue
        paths = root.rglob("*") if recursive else root.glob("*")
        for candidate in paths:
            if not candidate.is_file() or candidate.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            score = _topic_match_score(project.topic, candidate.stem)
            if score > 0:
                candidates[candidate.resolve()] = score
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda path: (candidates[path], path.stat().st_mtime_ns),
    )


def _topic_match_score(topic: str, filename: str) -> int:
    topic_key = _normalized_name(topic)
    file_key = _normalized_name(filename)
    if not topic_key or not file_key:
        return 0
    if topic_key in file_key:
        return 1000 + len(topic_key)
    if len(file_key) >= 6 and file_key in topic_key:
        return 800 + len(file_key)
    tokens = [_normalized_name(token) for token in re.split(r"[^\w\u4e00-\u9fff]+", topic)]
    longest = max((len(token) for token in tokens if len(token) >= 6 and token in file_key), default=0)
    return 500 + longest if longest else 0


def _normalized_name(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())
