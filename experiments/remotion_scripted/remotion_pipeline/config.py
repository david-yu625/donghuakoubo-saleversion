from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = EXPERIMENT_ROOT / "runs"
PUBLIC_ROOT = EXPERIMENT_ROOT / "public"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return {**values, **os.environ}
