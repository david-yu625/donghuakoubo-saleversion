#!/bin/zsh
set -e
PROJECT_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd -P)"
cd "$PROJECT_ROOT"
exec python3 -m tools.license.issuer_dialog
