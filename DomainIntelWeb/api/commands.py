"""Resolve research subprocess commands for source and packaged runtimes."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def search_command(args: list[str]) -> list[str]:
    executable = os.environ.get("INTDOG_SEARCH_EXECUTABLE", "").strip()
    if executable:
        return [str(Path(executable)), "cli", *args]
    return [sys.executable, "-u", "-m", "src.main", *args]


def search_cwd(default: Path) -> Path:
    configured = os.environ.get("INTDOG_SEARCH_ROOT", "").strip()
    return Path(configured) if configured else Path(default)
