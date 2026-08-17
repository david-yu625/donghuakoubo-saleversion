from __future__ import annotations

import os
import sys
from pathlib import Path


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


def portrait_package_dir(project_dir: Path) -> Path:
    """Keep package artifacts beside both legacy and orientation-scoped projects."""
    project_dir = project_dir.expanduser().resolve()
    if project_dir.name == "landscape":
        return project_dir.parent / "portrait_package"
    return project_dir / "portrait_package"
