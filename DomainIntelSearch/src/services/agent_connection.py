"""User-triggered, bounded end-to-end probes for verified local Agents."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from .agent_registry import diagnose_agent
from .agent_sessions import AgentSessionError, CodexAppServerSession

PROBE_MARKER = "INTDOG_CONNECTION_OK"


def _codex_app_server_probe(executable: str, workspace: str | Path,
                            timeout_seconds: int) -> str:
    session = CodexAppServerSession(
        executable, workspace, timeout=timeout_seconds)
    try:
        session.start()
        thread_id = session.start_thread()
        result = session.start_turn(
            thread_id,
            f"Connection check only. Reply with exactly {PROBE_MARKER} and nothing else.")
        parts = []
        for row in result.get("events", []):
            method = str(row.get("method") or "")
            if "delta" not in method.casefold():
                continue
            params = row.get("params") if isinstance(row.get("params"), dict) else {}
            value = params.get("delta") or params.get("text")
            if isinstance(value, str):
                parts.append(value)
        return "".join(parts).strip()
    finally:
        session.close()


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
    native_error: Exception | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="intdog-agent-probe-",
                                         dir=Path(workspace_root)) as temporary:
            if provider == "codex":
                executable = str(diagnosis.get("resolved_executable") or
                                 diagnosis.get("executable") or "")
                try:
                    text = _codex_app_server_probe(
                        executable, temporary, timeout_seconds)
                    passed = text == PROBE_MARKER
                    return {
                        "provider": provider, "ready": passed,
                        "status": "ready" if passed else "unexpected_response",
                        "connection": "codex_app_server",
                        "latency_ms": round((time.monotonic() - started) * 1000),
                        "detail": ("Codex App Server 真实最小调用成功" if passed
                                   else "Codex App Server 已响应，但未返回连接标记"),
                    }
                except (AgentSessionError, OSError) as exc:
                    native_error = exc
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
        fallback = provider == "codex" and native_error is not None
        return {
            "provider": provider, "ready": passed,
            "status": "ready" if passed else "unexpected_response",
            "connection": "cli_fallback" if fallback else "cli",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "detail": (("Codex App Server 不可用，已通过同一 Codex CLI 完成真实调用"
                        if fallback else "真实最小调用成功") if passed
                       else "Agent 已响应，但未返回连接标记"),
        }
    except Exception as exc:
        return {
            "provider": provider, "ready": False, "status": "failed",
            "connection": "cli_fallback" if native_error is not None else "cli",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "detail": f"真实最小调用失败：{type(exc).__name__}；请检查登录状态和网络后重试",
        }
