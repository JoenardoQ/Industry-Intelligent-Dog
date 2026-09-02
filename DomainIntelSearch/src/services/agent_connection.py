"""User-triggered, bounded end-to-end probes for verified local Agents."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from .agent_registry import diagnose_agent

PROBE_MARKER = "INTDOG_CONNECTION_OK"


def probe_agent_connection(profile: dict, workspace_root: str | Path,
                           *, timeout_seconds: int = 90) -> dict:
    started = time.monotonic()
    diagnosis = diagnose_agent(profile, timeout_seconds=min(15, timeout_seconds))
    provider = str(diagnosis.get("id") or profile.get("capability_id") or "unknown")
    if not diagnosis.get("ready"):
        return {
            "provider": provider, "ready": False, "status": "not_ready",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "detail": str(diagnosis.get("detail") or "Agent 尚未就绪")[:1000],
        }
    try:
        with tempfile.TemporaryDirectory(prefix="intdog-agent-probe-",
                                         dir=Path(workspace_root)) as temporary:
            if provider == "codex":
                from .codex_cli_service import CodexCLIService
                client = CodexCLIService(
                    {"codex": {"timeout_seconds": timeout_seconds}}, temporary,
                    executable_binding=diagnosis)
            elif provider == "claude":
                from .claude_cli_service import ClaudeCLIService
                client = ClaudeCLIService(
                    {"claude": {"timeout_seconds": timeout_seconds}}, temporary,
                    executable_binding=diagnosis)
            else:
                return {
                    "provider": provider, "ready": False, "status": "unsupported",
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "detail": "该 Agent 尚无经过验证的直接调用适配器",
                }
            result = client.complete(
                f"Connection check only. Reply with exactly {PROBE_MARKER} and nothing else.")
        passed = str(result.text).strip() == PROBE_MARKER
        return {
            "provider": provider, "ready": passed,
            "status": "ready" if passed else "unexpected_response",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "detail": "真实最小调用成功" if passed else "Agent 已响应，但未返回连接标记",
        }
    except Exception as exc:
        return {
            "provider": provider, "ready": False, "status": "failed",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "detail": f"真实最小调用失败：{type(exc).__name__}；请检查登录状态和网络后重试",
        }
