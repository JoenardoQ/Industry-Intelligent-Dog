"""Fast, redaction-safe checks used before queuing model work."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .agent_registry import diagnose_agent
from .capability_manifest import capability_or_unknown
from .runtime_credentials import credential_for


def _saved_agent_profile(provider: str, workspace: str | Path) -> dict | None:
    explicit_root = os.environ.get("DOMAIN_INTEL_DATA_ROOT", "").strip()
    base = Path(explicit_root) if explicit_root else Path(workspace)
    candidates = [base / "_settings" / "agent_profiles.json"]
    if not explicit_root:
        candidates.append(base.parent / "_settings" / "agent_profiles.json")
    for path in candidates:
        try:
            if not path.is_file() or path.stat().st_size > 256 * 1024:
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if not isinstance(value, list):
            continue
        matches = [item for item in value if (
            isinstance(item, dict)
            and str(item.get("capability_id") or "").casefold() == provider)]
        preferred = next((item for item in matches
                          if item.get("id") == f"binding-{provider}"), None)
        if preferred is not None:
            return preferred
        if matches:
            return matches[-1]
    return None


def provider_readiness(provider: str, workspace: str | Path) -> dict:
    name = str(provider or "").strip().lower()
    if not name or name == "taskpack":
        return {"provider": "taskpack", "ready": True, "installed": True,
                "failure_code": None, "detail": "任务包模式"}
    spec = capability_or_unknown(name)
    if spec.connection == "native_cli":
        profile = _saved_agent_profile(name, workspace) or {"id": name}
        result = diagnose_agent(profile)
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
