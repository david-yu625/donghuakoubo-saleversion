#!/bin/zsh

set -u

PROJECT_ROOT="$(cd -- "$(dirname -- "$0")" && pwd -P)"
cd "$PROJECT_ROOT" || exit 1

typeset -a python_candidates=()
if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  python_candidates+=("$PROJECT_ROOT/.venv/bin/python")
fi
if command -v python3 >/dev/null 2>&1; then
  python_candidates+=("$(command -v python3)")
fi
if command -v python >/dev/null 2>&1; then
  python_candidates+=("$(command -v python)")
fi

for python_cmd in "${python_candidates[@]}"; do
  if "$python_cmd" -c 'import PySide6' >/dev/null 2>&1; then
    # Package entrypoint: python3 -m src
    exec "$python_cmd" -m src
  fi
done

printf '%s\n' '[ERROR] 未找到可用的 Python 3 或 PySide6。'
printf '%s\n' '请先在项目目录运行：python3 -m pip install -r requirements.txt'
exit 1
