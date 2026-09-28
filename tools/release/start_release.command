#!/bin/zsh
set -e
PROJECT_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd -P)"
cd "$PROJECT_ROOT"
exec python3 tools/release/release_gui.py
