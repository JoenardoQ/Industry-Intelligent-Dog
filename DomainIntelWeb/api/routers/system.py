from __future__ import annotations

import threading
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..schemas import (BackgroundPermissionMutation, BackgroundPermissionUpdate,
                       BackgroundState, CustomAgentProfile, HealthState,
                       SetupState, ShutdownState, WorkflowSettingsState,
                       WorkflowSettingsUpdate)
from ..lifecycle import request_shutdown


def _bounded_json_object(path: Path) -> dict:
    try:
        if path.is_file() and path.stat().st_size <= 65_536:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        pass
    return {}


def _interval_minutes(value: object) -> int:
    try:
        parsed = int(value or 15)
    except (TypeError, ValueError):
        parsed = 15
    return max(5, min(1440, parsed))


def build_system_router(*, data_root: Path, jobs, automation, repo,
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
        from src.services.capability_manifest import CAPABILITY_MANIFEST
        from src.services.provider_readiness import provider_readiness
        from concurrent.futures import ThreadPoolExecutor
        import os

        selected = os.environ.get("INTDOG_LLM_PROVIDER", "").strip().lower()
        model = os.environ.get("INTDOG_LLM_MODEL", "").strip()
        custom_base = os.environ.get("INTDOG_LLM_API_BASE", "").strip()
        selected_auth = os.environ.get("INTDOG_LLM_AUTH_TYPE", "").strip().lower()
        direct_specs = tuple(
            spec for spec in CAPABILITY_MANIFEST
            if spec.execution_level == "direct"
            and spec.connection in {"native_cli", "api"}
        )
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(direct_specs)))) as pool:
            checks = {spec.id: result for spec, result in zip(
                direct_specs,
                pool.map(lambda item: provider_readiness(item.id, data_root), direct_specs),
            )}
        providers = []
        for spec in CAPABILITY_MANIFEST:
            if spec.connection != "api" or spec.execution_level != "direct":
                continue
            checked = checks[spec.id]
            selected_model = model if selected == spec.id else ""
            auth_type = ((selected_auth if selected == spec.id and selected_auth
                          else "bearer") if spec.auth == "explicit" else spec.auth)
            providers.append({"id": spec.id, "name": spec.name, "region": spec.region,
                              "configured": bool(checked.get("authenticated",
                                                             checked.get("ready", False))),
                              "ready": bool(checked.get("ready", False)),
                              "model": selected_model,
                              "default_model": spec.default_model,
                              "api_base": (custom_base if selected == spec.id and custom_base
                                           else spec.default_api_base),
                              "key_env": spec.key_env,
                              "docs_url": spec.docs_url,
                              "auth_type": auth_type,
                              "auth_configurable": spec.auth == "explicit",
                              "web_search": spec.web_search,
                              "schedulable": spec.schedulable})
        executable = os.environ.get("INTDOG_SEARCH_EXECUTABLE", "").strip()
        mcp = ([executable, "cli", "mcp-serve"] if executable else
               ["python3", "-m", "src.main", "mcp-serve"])
        agents = discover_agents(check_auth=False)
        for agent in agents:
            if agent["id"] in checks:
                checked = checks[agent["id"]]
                for key in ("installed", "authenticated", "ready", "executable",
                            "detail", "status", "failure_code", "version_verified",
                            "version"):
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

    @router.get("/settings/effective", response_model=WorkflowSettingsState)
    def effective_settings(folder: str = Query(min_length=1, max_length=80),
                           operation: str = Query(default="*", max_length=64)) -> dict:
        try:
            return repo.effective_workflow_settings(folder, operation)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.put("/settings/global/{operation}", response_model=dict)
    def put_global_settings(operation: str, request: WorkflowSettingsUpdate) -> dict:
        try:
            return repo.put_workflow_settings(
                None, operation, request.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.delete("/settings/global/{operation}", response_model=dict)
    def delete_global_settings(operation: str) -> dict:
        try:
            return {"deleted": repo.delete_workflow_settings(None, operation)}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.put("/industries/{folder}/settings/{operation}", response_model=dict)
    def put_industry_settings(folder: str, operation: str,
                              request: WorkflowSettingsUpdate) -> dict:
        try:
            return repo.put_workflow_settings(
                folder, operation, request.model_dump(exclude_unset=True))
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.delete("/industries/{folder}/settings/{operation}", response_model=dict)
    def delete_industry_settings(folder: str, operation: str) -> dict:
        try:
            return {"deleted": repo.delete_workflow_settings(folder, operation)}
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/background", response_model=BackgroundState)
    def background() -> dict:
        state_path = Path(os.environ.get("INTDOG_BACKGROUND_STATE_PATH") or
                          data_root.parent / "background-service.json")
        saved = _bounded_json_object(state_path)
        worker_state_path = Path(
            os.environ.get("INTDOG_BACKGROUND_WORKER_STATE_PATH") or
            state_path.with_name("background-worker-state.json"))
        worker_saved = _bounded_json_object(worker_state_path)
        schedules = repo.list_schedules()
        next_values = sorted(str(row["next_run_at"]) for row in schedules
                             if row.get("enabled") and row.get("next_run_at")
                             and row.get("runtime_status") != "paused")
        errors = [{
            "folder": row["folder"], "action": row["action"],
            "runtime_status": str(row.get("runtime_status") or "idle"),
            "error": str(row.get("last_error") or ""),
            "pause_reason": str(row.get("pause_reason") or ""),
            "retry_after": row.get("retry_after"),
        } for row in schedules if row.get("last_error") or row.get("pause_reason")]
        permissions = repo.list_background_authorizations()
        permission_keys = {
            (row["folder"], row["provider"], row["operation"])
            for row in permissions
        }
        for schedule in schedules:
            provider = str(schedule.get("provider") or "public_sources")
            key = (str(schedule["folder"]), provider, str(schedule["action"]))
            if provider in {"", "local", "public_sources"} or key in permission_keys:
                continue
            permissions.append({
                "folder": key[0], "provider": key[1], "operation": key[2],
                "allowed": False, "granted_by": "", "granted_at": "",
                "revoked_by": None, "revoked_at": None,
                "updated_at": str(schedule.get("updated_at") or ""),
            })
            permission_keys.add(key)
        return {
            "service": {
                "installed": bool(saved.get("installed")),
                "enabled": bool(saved.get("enabled")),
                "platform": str(saved.get("platform") or "unavailable"),
                "interval_minutes": _interval_minutes(saved.get("intervalMinutes")),
                "error_category": str(saved.get("errorCategory") or
                                      worker_saved.get("errorCategory") or ""),
            },
            "last_wakeup": repo.latest_worker_wakeup(),
            "next_run_at": next_values[0] if next_values else None,
            "permissions": sorted(
                permissions,
                key=lambda row: (row["folder"], row["provider"], row["operation"])),
            "schedule_errors": errors,
            "email_delivery": False,
        }

    @router.put("/background/permissions", response_model=BackgroundPermissionMutation)
    def update_background_permission(request: BackgroundPermissionUpdate) -> dict:
        try:
            if request.allowed:
                return repo.grant_background_authorization(
                    request.folder, provider=request.provider,
                    operation=request.operation, actor="local-user")
            return repo.revoke_background_authorization(
                request.folder, provider=request.provider,
                operation=request.operation, actor="local-user",
                reason=request.reason)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

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
