"""Use a locally authenticated Codex CLI as a subscription-backed research model."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class CodexCLIError(RuntimeError):
    pass


@dataclass
class CodexResult:
    text: str
    provider: str = "codex_subscription"
    model: str = "subscription_default"
    response_id: str = ""
    usage: dict | None = None


def windows_to_wsl(path: str | Path) -> str:
    raw = str(path)
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if not match:
        return str(Path(raw).resolve()).replace("\\", "/")
    drive, rest = match.groups()
    return f"/mnt/{drive.lower()}/{rest.replace(chr(92), '/')}"


class CodexCLIService:
    """Run ephemeral, read-only Codex tasks using the user's ChatGPT login."""

    def __init__(self, config: dict, workspace: str | Path):
        cfg = config.get("codex", {}) or {}
        self.workspace = Path(workspace).resolve()
        self.timeout = int(cfg.get("timeout_seconds", 1800))
        self.model = str(cfg.get("model") or "").strip()
        self._windows = os.name == "nt"
        self.executable = "wsl.exe" if self._windows else (shutil.which("codex") or "")
        self.codex_command = "codex"
        self.codex_home = ""
        if self._windows:
            windows_codex_home = Path.home() / ".codex"
            self.codex_home = windows_to_wsl(windows_codex_home)
            candidates = list((windows_codex_home / "bin" / "wsl").glob("*/codex"))
            if candidates:
                newest = max(candidates, key=lambda path: path.stat().st_mtime)
                self.codex_command = windows_to_wsl(newest)
        if not self.executable:
            raise CodexCLIError("未找到 Codex CLI；请先安装并用 ChatGPT 套餐登录")

    def _paths(self, output: Path) -> tuple[str, str]:
        if self._windows:
            return windows_to_wsl(self.workspace), windows_to_wsl(output)
        return str(self.workspace), str(output)

    def build_command(self, output: Path) -> list[str]:
        workspace, result_file = self._paths(output)
        codex_args = [
            self.codex_command, "--search", "--ask-for-approval", "never", "exec",
            "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
            "--cd", workspace, "--color", "never",
            "--output-last-message", result_file,
        ]
        if self.model:
            codex_args.extend(["--model", self.model])
        codex_args.append("-")
        if self._windows:
            return [self.executable, "--cd", workspace, "env",
                    f"CODEX_HOME={self.codex_home}", *codex_args]
        return [self.executable, *codex_args[1:]]

    def login_status(self) -> str:
        prefix = [self.executable] if not self._windows else [self.executable]
        command = ([*prefix, "env", f"CODEX_HOME={self.codex_home}",
                    self.codex_command, "login", "status"] if self._windows
                   else [*prefix, "login", "status"])
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=30, check=False)
        return ((result.stdout or "") + "\n" + (result.stderr or "")).strip()

    def complete(self, prompt: str) -> CodexResult:
        run_dir = self.workspace / "one_time" / "research" / "bootstrap" / "codex_runs"
        run_dir.mkdir(parents=True, exist_ok=True)
        output = run_dir / f"last_message_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.txt"
        command = self.build_command(output)
        result = subprocess.run(
            command, input=prompt, text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=self.timeout, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if self._windows else 0),
        )
        if result.returncode != 0:
            detail = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
            raise CodexCLIError(f"Codex CLI 执行失败({result.returncode}): {detail[-3000:]}")
        if not output.exists():
            raise CodexCLIError("Codex CLI 已退出，但没有生成最终响应文件")
        text = output.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            raise CodexCLIError("Codex CLI 最终响应为空")
        return CodexResult(text=text, model=self.model or "subscription_default")
