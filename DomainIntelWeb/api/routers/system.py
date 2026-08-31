from __future__ import annotations

import threading
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..schemas import CustomAgentProfile, HealthState, SetupState, ShutdownState
from ..lifecycle import request_shutdown


def build_system_router(*, data_root: Path, jobs, automation,
                        session_required: bool = False) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["system"])

    @router.get("/health", response_model=HealthState)
    def health() -> dict:
        return {"status": "ready", "data_root": str(data_root),
                "database": (data_root / "intdog.sqlite3").exists(),
                "active_jobs": len(jobs.active()),
                "automation_running": bool(automation._thread and automation._thread.is_alive()),
                "session_required": session_required}

    @router.get("/setup", response_model=SetupState)
    def setup() -> dict:
        from src.services.agent_registry import discover_agents
        from src.services.capability_manifest import API_SPECS
        from src.services.provider_readiness import provider_readiness
        from concurrent.futures import ThreadPoolExecutor
        import os

        generic_key = os.environ.get("INTDOG_LLM_API_KEY", "").strip()
        selected = os.environ.get("INTDOG_LLM_PROVIDER", "").strip().lower()
        model = os.environ.get("INTDOG_LLM_MODEL", "").strip()
        custom_base = os.environ.get("INTDOG_LLM_API_BASE", "").strip()
        providers = []
        for spec in API_SPECS:
            configured = bool(os.environ.get(spec.key_env, "").strip()
                              or (generic_key and selected == spec.id))
            selected_model = model if selected == spec.id else ""
            providers.append({"id": spec.id, "name": spec.name, "region": spec.region,
                              "configured": configured,
                              "ready": configured and bool(selected_model),
                              "model": selected_model,
                              "default_model": spec.default_model,
                              "api_base": custom_base or spec.default_api_base,
                              "key_env": spec.key_env,
                              "docs_url": spec.docs_url,
                              "web_search": spec.web_search,
                              "schedulable": spec.schedulable})
        executable = os.environ.get("INTDOG_SEARCH_EXECUTABLE", "").strip()
        mcp = ([executable, "cli", "mcp-serve"] if executable else
               ["python3", "-m", "src.main", "mcp-serve"])
        agents = discover_agents(check_auth=False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            checks = {name: result for name, result in zip(
                ("codex", "claude"),
                pool.map(lambda name: provider_readiness(name, data_root),
                         ("codex", "claude")))}
        for agent in agents:
            if agent["id"] in {"codex", "claude"}:
                checked = checks[agent["id"]]
                for key in ("installed", "authenticated", "ready", "executable", "detail", "mode"):
                    if key in checked:
                        agent[key] = checked[key]
        mcp_configs = [
            {"id": "codex", "name": "Codex", "format": "toml",
             "value": f'[mcp_servers.intdog]\ncommand = {json.dumps(mcp[0])}\nargs = {json.dumps(mcp[1:])}'},
            {"id": "claude", "name": "Claude Code", "format": "json",
             "value": {"mcpServers": {"intdog": {"command": mcp[0], "args": mcp[1:]}}}},
            {"id": "workbuddy", "name": "Work Buddy", "format": "json",
             "value": {"mcpServers": {"intdog": {"command": mcp[0], "args": mcp[1:]}}}},
            {"id": "generic", "name": "Generic MCP", "format": "json",
             "value": {"mcpServers": {"intdog": {"command": mcp[0], "args": mcp[1:]}}}},
        ]
        profiles_path = data_root / "_settings" / "agent_profiles.json"
        try:
            raw_profiles = json.loads(profiles_path.read_text(encoding="utf-8")) if profiles_path.is_file() else []
            agent_profiles = [CustomAgentProfile.model_validate(item).model_dump()
                              for item in raw_profiles if isinstance(item, dict)]
        except (OSError, ValueError, TypeError):
            agent_profiles = []
        return {"runtime_ready": True, "data_root": str(data_root),
                "taskpack_ready": True, "agents": agents,
                "api_providers": providers, "mcp_command": mcp,
                "mcp_configs": mcp_configs,
                "agent_profiles": agent_profiles,
                "privacy_note": "仅检测 PATH 与公开状态命令；不读取 GUI 私有登录数据"}

    @router.post("/shutdown", status_code=202, response_model=ShutdownState)
    def shutdown() -> dict:
        timer = threading.Timer(0.35, request_shutdown)
        timer.daemon = True
        timer.start()
        return {"status": "stopping"}

    @router.get("/artifact")
    def artifact(path: str = Query(max_length=4000)):
        candidate = Path(path).resolve()
        try:
            candidate.relative_to(data_root)
        except ValueError as exc:
            raise HTTPException(403, "只能读取行业数据目录中的产物") from exc
        if not candidate.is_file():
            raise HTTPException(404, "产物不存在")
        return FileResponse(candidate)

    return router
