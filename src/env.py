"""Environment loading helpers for src."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _runtime_env_path(path: Path) -> Path:
    """Prefer a customer-supplied config beside a frozen application."""
    if not getattr(sys, "frozen", False):
        return path
    executable = Path(sys.executable).expanduser().resolve()
    candidates: list[Path] = []
    if sys.platform == "darwin" and executable.parent.name == "MacOS":
        app_root = executable.parent.parent.parent
        candidates.extend((app_root.parent / path.name, app_root / path.name))
    else:
        candidates.append(executable.parent / path.name)
    candidates.append(path)
    return next((candidate for candidate in candidates if candidate.is_file()), path)


def load_env_file(path: Path, *, override: bool = True) -> None:
    """Load project settings from ``.env``.

    The project keeps API credentials and model settings in this file.  Local
    values should be deterministic during testing, so they override inherited
    process values by default.  Callers that intentionally need process-level
    precedence can pass ``override=False``.
    """
    path = _runtime_env_path(path.expanduser().resolve())
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value
