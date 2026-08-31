"""Claude Code non-interactive provider using the user's local sign-in."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ClaudeCLIError(RuntimeError):
    pass


@dataclass
class ClaudeResult:
    text: str
    provider: str = "claude_subscription"
    model: str = "subscription_default"
    response_id: str = ""
    usage: dict | None = None


class ClaudeCLIService:
    def __init__(self, config: dict, workspace: str | Path):
        cfg = config.get("claude", {}) or {}
        self.workspace = Path(workspace).resolve()
        self.timeout = int(cfg.get("timeout_seconds", 1800))
        self.model = str(cfg.get("model") or "").strip()
        self.executable = shutil.which("claude") or ""
        if not self.executable:
            raise ClaudeCLIError("未找到 Claude Code；请安装后运行 claude auth login")

    def diagnostics(self) -> dict:
        try:
            result = subprocess.run(
                [self.executable, "auth", "status"], capture_output=True, text=True,
                timeout=8, check=False,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"installed": True, "authenticated": False, "ready": False,
                    "mode": "native", "executable": self.executable,
                    "detail": f"Claude 登录状态检测失败：{type(exc).__name__}"}
        detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        return {"installed": True, "authenticated": result.returncode == 0,
                "ready": result.returncode == 0, "mode": "native",
                "executable": self.executable, "detail": detail[-800:]}

    def complete(self, prompt: str) -> ClaudeResult:
        command = [self.executable, "-p", "--permission-mode", "plan"]
        if self.model:
            command.extend(["--model", self.model])
        result = subprocess.run(
            command, input=prompt, cwd=self.workspace, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=self.timeout,
            check=False, creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        if result.returncode != 0:
            detail = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
            raise ClaudeCLIError(f"Claude Code 执行失败({result.returncode}): {detail[-3000:]}")
        text = (result.stdout or "").strip()
        if not text:
            raise ClaudeCLIError("Claude Code 已退出，但没有返回可读文本")
        return ClaudeResult(text=text, model=self.model or "subscription_default")
