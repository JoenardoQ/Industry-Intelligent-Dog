#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export DOMAIN_INTEL_DATA_ROOT="$project_root/DomainIntelData"
export INTDOG_PROJECT_ROOT="$project_root"
export PYTHONUTF8=1

# WSLg's Linux Tk does not automatically see Windows CJK fonts. Without this,
# Chinese labels render as tofu/garbled glyphs even though all files are UTF-8.
fontconfig_file="$project_root/DomainIntelApp/app/fontconfig-wsl.conf"
if [[ -f "$fontconfig_file" && -d /mnt/c/Windows/Fonts ]]; then
  export FONTCONFIG_FILE="$fontconfig_file"
fi

bootstrap_python="${INTDOG_BOOTSTRAP_PYTHON:-}"
if [[ -z "$bootstrap_python" ]]; then
  for candidate in /usr/bin/python3 "$HOME/miniconda3/bin/python" python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import tkinter' >/dev/null 2>&1; then
      bootstrap_python="$candidate"
      break
    fi
  done
fi

if [[ -z "$bootstrap_python" ]]; then
  echo "IntDog requires a Python installation with tkinter." >&2
  echo "Install python3-tk or set INTDOG_BOOTSTRAP_PYTHON." >&2
  exit 1
fi

exec "$bootstrap_python" "$project_root/DomainIntelApp/launch_intdog.py" "$@"
