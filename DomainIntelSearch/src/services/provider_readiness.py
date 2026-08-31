"""Fast, redaction-safe checks used before queuing model work."""
from __future__ import annotations
import os
from pathlib import Path

from .capability_manifest import capability

def provider_readiness(provider: str, workspace: str | Path) -> dict:
    name = str(provider or "").strip().lower()
    if not name or name == "taskpack":
        return {"provider": "taskpack", "ready": True, "detail": "任务包模式"}
    if name == "codex":
        try:
            from .codex_cli_service import CodexCLIService
            return {"provider": name, **CodexCLIService({}, workspace).diagnostics()}
        except Exception as exc:
            return {"provider": name, "ready": False, "detail": str(exc), "installed": False}
    if name == "claude":
        try:
            from .claude_cli_service import ClaudeCLIService
            return {"provider": name, **ClaudeCLIService({}, workspace).diagnostics()}
        except Exception as exc:
            return {"provider": name, "ready": False, "detail": str(exc), "installed": False}
    spec = capability(name)
    if not spec or spec.kind != "api" or not spec.key_env:
        return {"provider": name, "ready": False, "detail": "该 Agent 通过 MCP/任务包交接，不是直接生成 Provider"}
    generic = os.environ.get("INTDOG_LLM_API_KEY", "").strip()
    selected = os.environ.get("INTDOG_LLM_PROVIDER", "").strip().lower()
    configured = bool(os.environ.get(spec.key_env, "").strip() or
                      (generic and selected == name))
    return {"provider": name, "ready": configured, "installed": True,
            "authenticated": configured,
            "detail": "API 凭据已配置" if configured else f"缺少 {spec.key_env} 或桌面安全存储配置"}
