from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    os.environ.setdefault(
        "DONGHUA_PROJECT_ROOT",
        str(Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))),
    )

from src.commands.gui import main


def _run_internal_module() -> int | None:
    """Dispatch pipeline child commands from a frozen PyInstaller executable."""
    args = sys.argv[1:]
    if not args or args[0] != "--internal-run":
        return None
    if len(args) < 2:
        raise SystemExit("--internal-run requires a module name")
    module = importlib.import_module(args[1])
    sys.argv[:] = [sys.argv[0], *args[2:]]
    entrypoint = getattr(module, "main", None)
    if entrypoint is None:
        raise SystemExit(f"模块没有 main() 入口：{args[1]}")
    return int(entrypoint())


if __name__ == "__main__":
    internal_result = _run_internal_module()
    raise SystemExit(main() if internal_result is None else internal_result)
