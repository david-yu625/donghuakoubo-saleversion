"""Structured local application settings, separate from API environment values."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = (
    Path(os.environ["DONGHUA_PROJECT_ROOT"]).expanduser().resolve()
    if os.environ.get("DONGHUA_PROJECT_ROOT")
    else Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)
APP_SETTINGS_PATH = PROJECT_ROOT / "settings.json"
APP_SETTING_KEYS = (
    "INDUSTRY",
    "VISUAL_THEME",
    "TITLE_COLOR",
    "TITLE_BACKGROUND_COLOR",
    "SUBTITLE_COLOR",
    "SUBTITLE_BACKGROUND_COLOR",
    "BACKGROUND_IMAGE",
    "BACKGROUND_MUSIC",
    "DRAFT_FOLDER",
    "TITLE_FONT",
    "SUBTITLE_FONT",
    "VIDEO_ORIENTATION",
)


def load_app_settings(path: Path = APP_SETTINGS_PATH) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: str(payload[key]).strip()
        for key in APP_SETTING_KEYS
        if key in payload and payload[key] is not None
    }


def save_app_settings(values: dict[str, str], path: Path = APP_SETTINGS_PATH) -> None:
    normalized = {
        key: str(values.get(key, "")).strip()
        for key in APP_SETTING_KEYS
        if key in values
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def migrate_legacy_app_settings(
    env_path: Path,
    settings_path: Path = APP_SETTINGS_PATH,
) -> dict[str, str]:
    """Move legacy application settings out of .env while preserving API lines."""
    current = load_app_settings(settings_path)
    if not env_path.is_file():
        return current

    legacy: dict[str, str] = {}
    retained: list[str] = []
    changed = False
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if stripped and "=" in stripped else ""
        if key in APP_SETTING_KEYS:
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            legacy[key] = value
            changed = True
            continue
        retained.append(line)

    merged = {**legacy, **current}
    if merged != current:
        save_app_settings(merged, settings_path)
    if changed:
        while retained and not retained[-1].strip():
            retained.pop()
        temporary = env_path.with_name(f".{env_path.name}.tmp")
        temporary.write_text("\n".join(retained) + "\n", encoding="utf-8")
        temporary.replace(env_path)
    return merged
