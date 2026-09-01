"""Fast, redaction-safe checks used before queuing model work."""

from __future__ import annotations

import os
from pathlib import Path

from .agent_registry import diagnose_agent
from .capability_manifest import capability_or_unknown
from .runtime_credentials import credential_for


def provider_readiness(provider: str, workspace: str | Path) -> dict:
    del workspace  # the diagnostic contract never scans a workspace
    name = str(provider or "").strip().lower()
    if not name or name == "taskpack":
        return {"provider": "taskpack", "ready": True, "installed": True,
                "failure_code": None, "detail": "任务包模式"}
    spec = capability_or_unknown(name)
    if spec.connection == "native_cli":
        result = diagnose_agent({"id": name})
        return {"provider": name, **result}
    if spec.connection != "api":
        return {"provider": name, "ready": False, "installed": False,
                "failure_code": "direct_adapter_unavailable",
                "detail": "该 Agent 通过 MCP/任务包交接，不是直接生成 Provider"}

    runtime = credential_for(name)
    selected = (runtime.get("provider") or
                os.environ.get("INTDOG_LLM_PROVIDER", "")).strip().lower()
    selected_here = selected == name
    generic_key = (runtime.get("apiKey") or
                   os.environ.get("INTDOG_LLM_API_KEY", "")).strip() if selected_here else ""
    provider_key = (os.environ.get(spec.key_env, "").strip()
                    if spec.key_env and
                    (spec.key_env != "INTDOG_LLM_API_KEY" or selected_here)
                    else "")
    model = ((runtime.get("model") or os.environ.get("INTDOG_LLM_MODEL", "")).strip()
             if selected_here else "") \
        or spec.default_model
    base = ((runtime.get("apiBase") or os.environ.get("INTDOG_LLM_API_BASE", "")).strip()
            if selected_here else "") \
        or spec.default_api_base
    auth_type = ((runtime.get("authType") or os.environ.get("INTDOG_LLM_AUTH_TYPE", "")).strip()
                 if selected_here else "") \
        or ("" if spec.auth == "explicit" else spec.auth)
    result = diagnose_agent({
        "id": name, "api_base": base, "model": model, "auth_type": auth_type,
        "credential_configured": bool(generic_key or provider_key),
    })
    return {"provider": name, **result}
