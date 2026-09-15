from __future__ import annotations

import os
import re
import sys
from pathlib import Path, PureWindowsPath


VIDEO_EXPORT_VARIANTS = ("landscape", "portrait", "portrait_package")


def safe_topic(value: str) -> str:
    """Return the directory-safe topic spelling used throughout output/."""
    name = re.sub(r'[\\/:*?"<>|\s]+', "", value.strip())
    return name or "未命名"


def video_export_path(output_root: Path, topic: str, variant: str) -> Path:
    """Return the canonical final-video path for one topic and video variant."""
    if variant not in VIDEO_EXPORT_VARIANTS:
        raise ValueError(f"不支持的视频版本：{variant}")
    name = safe_topic(topic)
    return (output_root.expanduser().resolve() / name / variant / f"{name}_{variant}.mp4")


def default_draft_folder(
    *,
    platform: str | None = None,
    home: Path | None = None,
    local_app_data: str | None = None,
) -> Path:
    platform = platform or sys.platform
    home = home or Path.home()
    if platform == "win32":
        local_value = local_app_data or os.getenv("LOCALAPPDATA")
        local_root = Path(local_value) if local_value else home / "AppData" / "Local"
        return local_root / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"
    return home / "Movies" / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"


def resolve_draft_folder(
    value: str | Path | None,
    *,
    platform: str | None = None,
    home: Path | None = None,
    local_app_data: str | None = None,
) -> Path:
    """Ignore a configured draft path that belongs to another operating system."""
    platform = platform or sys.platform
    home = home or Path.home()
    fallback = default_draft_folder(
        platform=platform,
        home=home,
        local_app_data=local_app_data,
    )
    raw = str(value or "").strip()
    if not raw:
        return fallback

    windows_path = PureWindowsPath(raw)
    if platform == "win32":
        if raw.startswith("/") and not windows_path.drive:
            return fallback
    elif windows_path.drive or "\\" in raw:
        return fallback
    return Path(raw).expanduser()


def portrait_package_dir(project_dir: Path) -> Path:
    """Keep package artifacts beside both legacy and orientation-scoped projects."""
    project_dir = project_dir.expanduser().resolve()
    if project_dir.name == "landscape":
        return project_dir.parent / "portrait_package"
    return project_dir / "portrait_package"
