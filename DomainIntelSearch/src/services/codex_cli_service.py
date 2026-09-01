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

    def __init__(self, config: dict, workspace: str | Path,
                 *, executable_binding: dict | None = None):
        cfg = config.get("codex", {}) or {}
        self.workspace = Path(workspace).resolve()
        self.timeout = int(cfg.get("timeout_seconds", 1800))
        self.model = str(cfg.get("model") or "").strip()
        self._windows = os.name == "nt"
        self._executable_binding = executable_binding
        self.mode = "native"
        if executable_binding is not None:
            from .agent_registry import (ExecutableBindingError,
                                         validate_executable_binding)
            try:
                self.executable = validate_executable_binding(executable_binding)
            except ExecutableBindingError as exc:
                raise CodexCLIError(str(exc)) from exc
        else:
            self.executable = shutil.which("codex") or ""
        self.codex_command = "codex"
        self.codex_home = ""
        if executable_binding is None and self._windows and not self.executable:
            windows_codex_home = Path.home() / ".codex"
            candidates = list((windows_codex_home / "bin" / "wsl").glob("*/codex"))
            wsl = shutil.which("wsl.exe") or shutil.which("wsl") or ""
            if wsl and candidates:
                newest = max(candidates, key=lambda path: path.stat().st_mtime)
                self.mode = "wsl-shared-home"
                self.executable = wsl
                self.codex_command = windows_to_wsl(newest)
                self.codex_home = windows_to_wsl(windows_codex_home)
            elif wsl:
                probe = subprocess.run(
                    [wsl, "sh", "-lc", "command -v codex"],
                    capture_output=True, text=True, timeout=8, check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                discovered = (probe.stdout or "").strip().splitlines()
                if probe.returncode == 0 and discovered:
                    self.mode = "wsl"
                    self.executable = wsl
                    self.codex_command = discovered[-1].strip()
        if not self.executable:
            raise CodexCLIError(
                "未找到 Codex CLI。安装 IntDog 不会自动安装模型工具；"
                "请先安装 Codex CLI 并用 ChatGPT 登录，然后重新检测"
            )

    def _paths(self, output: Path) -> tuple[str, str]:
        if getattr(self, "mode", "wsl-shared-home" if self._windows else "native").startswith("wsl"):
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
        mode = getattr(self, "mode", "wsl-shared-home" if self._windows else "native")
        if mode == "wsl-shared-home":
            return [self.executable, "--cd", workspace, "env",
                    f"CODEX_HOME={self.codex_home}", *codex_args]
        if mode == "wsl":
            return [self.executable, "--cd", workspace, *codex_args]
        return [self.executable, *codex_args[1:]]

    def login_status_result(self) -> subprocess.CompletedProcess[str]:
        if self.mode == "wsl-shared-home":
            command = [self.executable, "env", f"CODEX_HOME={self.codex_home}",
                       self.codex_command, "login", "status"]
        elif self.mode == "wsl":
            command = [self.executable, self.codex_command, "login", "status"]
        else:
            command = [self.executable, "login", "status"]
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=8, check=False,
                                creationflags=(subprocess.CREATE_NO_WINDOW
                                               if self._windows else 0))
        return result

    def login_status(self) -> str:
        result = self.login_status_result()
        return ((result.stdout or "") + "\n" + (result.stderr or "")).strip()

    def diagnostics(self) -> dict:
        try:
            result = self.login_status_result()
        except (OSError, subprocess.SubprocessError) as exc:
            return {"installed": True, "authenticated": False, "ready": False,
                    "mode": self.mode, "executable": self.executable,
                    "detail": f"Codex 登录状态检测失败：{type(exc).__name__}"}
        detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        authenticated = result.returncode == 0
        return {"installed": True, "authenticated": authenticated,
                "ready": authenticated, "mode": self.mode,
                "executable": self.executable,
                "detail": detail[-800:] or ("已登录" if authenticated else "未登录")}

    def complete(self, prompt: str) -> CodexResult:
        binding = getattr(self, "_executable_binding", None)
        if binding is not None:
            from .agent_registry import (ExecutableBindingError,
                                         validate_executable_binding)
            try:
                self.executable = validate_executable_binding(binding)
            except ExecutableBindingError as exc:
                raise CodexCLIError(str(exc)) from exc
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
