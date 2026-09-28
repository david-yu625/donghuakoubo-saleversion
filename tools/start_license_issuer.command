#!/bin/zsh
set -e
cd "$(dirname "$0")/.."
exec python3 -m src.security_guard.issuer_dialog
