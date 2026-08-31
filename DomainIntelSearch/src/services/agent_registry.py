"""Discover local agent runtimes without reading private application state.

The registry is intentionally capability based.  Detection means that a public
command is present; it never means that a GUI account or paid quota is usable.
Only adapters with a verified non-interactive contract may execute research.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from .capability_manifest import AGENT_SPECS

AGENTS = AGENT_SPECS  # compatibility alias


def _find(commands: tuple[str, ...]) -> str:
    for command in commands:
        resolved = shutil.which(command)
        if resolved:
            return resolved
    return ""


def _run_status(command: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )


def discover_agents(*, check_auth: bool = True) -> list[dict]:
    """Return redaction-safe diagnostics for known and custom agent bridges."""
    rows: list[dict] = []
    for spec in AGENTS:
        executable = _find(spec.commands)
        row = {**spec.public(),
               "installed": bool(executable), "authenticated": None,
               "ready": False, "executable": executable, "detail": ""}
        if not executable:
            row["detail"] = "未在 PATH 中检测到公开 CLI"
        elif spec.id == "codex" and check_auth:
            try:
                result = _run_status([executable, "login", "status"])
                row["authenticated"] = result.returncode == 0
                row["ready"] = result.returncode == 0
                detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
                row["detail"] = detail[-800:] or ("已登录" if row["ready"] else "未登录")
            except (OSError, subprocess.SubprocessError) as exc:
                row["authenticated"] = False
                row["detail"] = f"状态检测失败：{type(exc).__name__}"
        elif spec.id == "claude" and check_auth:
            try:
                result = _run_status([executable, "auth", "status"])
                row["authenticated"] = result.returncode == 0
                row["ready"] = result.returncode == 0
                detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
                row["detail"] = detail[-800:] or ("已登录" if row["ready"] else "未登录")
            except (OSError, subprocess.SubprocessError) as exc:
                row["authenticated"] = False
                row["detail"] = f"状态检测失败：{type(exc).__name__}"
        elif spec.id not in {"codex", "claude"}:
            row["ready"] = spec.execution in {"handoff", "experimental"}
            row["detail"] = "已检测；通过 IntDog MCP 或任务包交接"
        else:
            row["detail"] = "已检测；等待公开登录状态检查"
        rows.append(row)

    custom = os.environ.get("INTDOG_CUSTOM_AGENT_COMMAND", "").strip()
    if custom:
        executable = _find((custom,))
        rows.append({
            "id": "custom", "name": "Custom CLI", "region": "custom",
            "commands": [custom], "connection": "custom", "execution": "handoff",
            "docs_url": "", "note": "User-configured command; no private state is read.",
            "installed": bool(executable), "authenticated": None,
            "ready": bool(executable), "executable": executable,
            "detail": "已检测自定义命令" if executable else "自定义命令不在 PATH 中",
        })
    return rows
