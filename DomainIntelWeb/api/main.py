"""FastAPI boundary over IntDog's canonical local repository.

The browser never reads compatibility files directly. The canonical domain
service and the Web workbench share only the neutral application runtime.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers.content import build_content_router
from .routers.daily import build_daily_router
from .routers.industries import build_industries_router
from .routers.operations import build_operations_router
from .routers.sources import build_sources_router
from .routers.system import build_system_router
from .routers.automation import build_automation_router
from .routers.intelligence import build_intelligence_router
from .routers.recovery import build_recovery_router
from .routers.agent_bridge import build_agent_bridge_router
from .routers.conversation import build_conversation_router
from .security import install_security

PROJECT_ROOT = Path(os.environ.get("INTDOG_PROJECT_ROOT") or Path(__file__).resolve().parents[2])
APP_ROOT = PROJECT_ROOT / "DomainIntelApp"
SEARCH_ROOT = PROJECT_ROOT / "DomainIntelSearch"
for import_root in (APP_ROOT, SEARCH_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from runtime import dataio  # noqa: E402
from runtime.jobs import JobManager, sanitize_text  # noqa: E402
from intdog_core.models import validate_folder  # noqa: E402
from intdog_core import IntDogService  # noqa: E402
from src.services.semantic_verifier import build_production_assertion_verifier  # noqa: E402
from src.services.runtime_credentials import credential_bundle  # noqa: E402
from src.services.conversation_broker import ConversationBroker  # noqa: E402
from .automation import AutomationScheduler  # noqa: E402


DATA_ROOT = Path(
    os.environ.get("DOMAIN_INTEL_DATA_ROOT")
    or os.environ.get("INTDOG_DATA_ROOT")
    or PROJECT_ROOT / "DomainIntelData"
).resolve()
WEB_DIST = PROJECT_ROOT / "DomainIntelWeb" / "dist"

service = IntDogService(DATA_ROOT)
conversation_broker = ConversationBroker(service.repo, DATA_ROOT)
jobs = JobManager(
    DATA_ROOT, ledger=service.repo, credential_supplier=credential_bundle)
automation = AutomationScheduler(
    DATA_ROOT, jobs, search_root=SEARCH_ROOT, project_root=PROJECT_ROOT)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    automation.start()
    yield
    automation.stop(timeout=3)
    jobs.shutdown(timeout=3)
    conversation_broker.close()


app = FastAPI(title="IntDog Local API", version="4.1.0", lifespan=lifespan)
install_security(app, os.environ.get("INTDOG_SESSION_TOKEN", ""))


def _folder(value: str) -> str:
    try:
        folder = validate_folder(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if not any(row["folder"] == folder for row in dataio.list_industries(DATA_ROOT)):
        raise HTTPException(404, "行业不存在")
    return folder


def _display_source(item: dict) -> str:
    category = str(item.get("category") or item.get("_cat") or "")
    if category == "github":
        owner = item.get("owner") or item.get("developer") or item.get("author")
        if not owner:
            parts = urlsplit(str(item.get("url") or "")).path.strip("/").split("/")
            owner = parts[0] if len(parts) > 1 else ""
        return str(owner or "N/A")
    if category == "papers":
        authors = item.get("authors") or item.get("author")
        if isinstance(authors, list):
            authors = ", ".join(str(value) for value in authors[:4])
        return str(authors or "N/A")
    if category == "ceo":
        return str(item.get("account") or item.get("publisher") or item.get("author") or "N/A")
    return str(
        item.get("source_name") or item.get("publication") or item.get("source")
        or item.get("publisher") or item.get("account") or item.get("author") or "N/A"
    )


def _daily_item(item: dict) -> dict:
    result = dict(item)
    result["display_source"] = _display_source(result)
    result["origin"] = dataio.source_origin(result)
    result["identity"] = {
        "date": str(result.get("_date") or result.get("date") or ""),
        "category": str(result.get("_cat") or result.get("category") or ""),
        "key": str(result.get("url") or result.get("title") or "")[:200],
    }
    return result


daily_router = build_daily_router(
    data_root=DATA_ROOT, dataio=dataio, resolve_folder=_folder,
    present_item=_daily_item)
sources_router = build_sources_router(
    data_root=DATA_ROOT, dataio=dataio, service=service, resolve_folder=_folder,
    jobs=jobs, search_root=SEARCH_ROOT, project_root=PROJECT_ROOT)
industries_router = build_industries_router(
    data_root=DATA_ROOT, dataio=dataio, resolve_folder=_folder)
content_router = build_content_router(
    data_root=DATA_ROOT, dataio=dataio, resolve_folder=_folder)
system_router = build_system_router(
    data_root=DATA_ROOT, jobs=jobs, automation=automation,
    repo=service.repo,
    session_required=bool(os.environ.get("INTDOG_SESSION_TOKEN")))
app.include_router(daily_router)
app.include_router(sources_router)
app.include_router(industries_router)
app.include_router(content_router)
app.include_router(system_router)
app.include_router(build_automation_router(
    automation=automation, resolve_folder=_folder))
intelligence_router = build_intelligence_router(
    data_root=DATA_ROOT, service=service, resolve_folder=_folder, dataio=dataio,
    jobs=jobs, search_root=SEARCH_ROOT, project_root=PROJECT_ROOT)
app.include_router(intelligence_router)
app.include_router(build_recovery_router(data_root=DATA_ROOT, dataio=dataio))
agent_bridge_verifier = build_production_assertion_verifier(PROJECT_ROOT)
agent_bridge_router = build_agent_bridge_router(
    data_root=DATA_ROOT, dataio=dataio, resolve_folder=_folder, service=service,
    verifier=agent_bridge_verifier)
app.include_router(agent_bridge_router)
# Preserve direct-call compatibility for the existing Python contract tests.
daily = next(route.endpoint for route in daily_router.routes
             if route.path.endswith("/daily") and "GET" in route.methods)
delete_daily = next(route.endpoint for route in daily_router.routes
                    if route.path.endswith("/daily") and "DELETE" in route.methods)
industries = next(route.endpoint for route in industries_router.routes
                  if route.path == "/api/industries" and "GET" in route.methods)
overview = next(route.endpoint for route in industries_router.routes
                if route.path.endswith("/overview"))
health = next(route.endpoint for route in system_router.routes
              if route.path == "/api/health")
artifact = next(route.endpoint for route in system_router.routes
                if route.path == "/api/artifact")
setup = next(route.endpoint for route in system_router.routes
             if route.path == "/api/setup")
history = next(route.endpoint for route in intelligence_router.routes
               if route.path.endswith("/history"))


def _job_rows() -> list[dict]:
    active_ids = {job.run_id for job in jobs.active()}
    manifests = {str(row.get("run_id")): row for row in jobs.store.list()
                 if row.get("run_id")}
    rows = []

    def heartbeat_age(value) -> float | None:
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(
                str(value).replace("Z", "+00:00"))).total_seconds()
        except (TypeError, ValueError):
            return None

    def elapsed_seconds(started, finished=None) -> int:
        try:
            start = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            end = (datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
                   if finished else datetime.now(timezone.utc))
            return max(0, int((end - start).total_seconds()))
        except (TypeError, ValueError):
            return 0

    for task in service.repo.list_tasks(limit=500):
        run_id = task["id"]
        manifest = manifests.pop(run_id, {})
        error = task.get("error") if isinstance(task.get("error"), dict) else {}
        heartbeat = task.get("heartbeat_at") or task.get("updated_at")
        age = heartbeat_age(heartbeat)
        status = str(task["status"])
        progress = max(0, min(100, int(task.get("progress") or 0)))
        task_input = task.get("input") if isinstance(task.get("input"), dict) else {}
        execution_mode = str(task_input.get("execution_mode") or "")
        operation = str(task.get("operation") or "")
        recovery = []
        if status in {"queued", "running", "cancelling", "paused"}:
            recovery.append("cancel")
        if status in {"paused", "failed", "partial", "cancelled", "interrupted"}:
            recovery.append("retry")
        rows.append({
            "run_id": run_id,
            "folder": str(task_input.get("folder") or ""),
            "title": sanitize_text(manifest.get("title") or task["operation"]),
            "status": status, "updated_at": str(task.get("updated_at") or ""),
            "stalled": bool(status in {"queued", "running", "cancelling"}
                            and age is not None and age > 45),
            "active": run_id in active_ids,
            "stage": str(task.get("stage") or "queued"),
            "progress": 100 if status == "completed" else progress,
            "progress_mode": ("determinate" if progress > 0 or status == "completed"
                              else "indeterminate"),
            "elapsed_seconds": elapsed_seconds(task.get("started_at"), task.get("finished_at")),
            "result_kind": ("task_package" if execution_mode == "taskpack" else
                            "local_data" if operation in {
                                "daily", "history", "coverage", "bootstrap"} else
                            "artifact" if operation else "unknown"),
            "artifact_path": task.get("output_path") or
                             manifest.get("artifact_path") or None,
            "parent_run_id": task.get("parent_run_id"),
            "operation": task.get("operation"),
            "error": sanitize_text(error.get("message") or manifest.get("error") or ""),
            "error_category": str(error.get("category") or ""),
            "origin": task.get("origin") or "app",
            "provider": task.get("provider") or "local",
            "model": task.get("model") or "",
            "time_window": task.get("time_window") or {
                "start": None, "end": None, "timezone": None},
            "heartbeat_at": task.get("heartbeat_at"),
            "checkpoint": task.get("checkpoint") or {},
            "request_dispatched_at": task.get("request_dispatched_at"),
            "recovery_actions": recovery,
        })
    for manifest in manifests.values():
        raw_progress = float(manifest.get("progress") or 0)
        progress = round(raw_progress * 100) if raw_progress <= 1 else round(raw_progress)
        status = str(manifest.get("status") or "interrupted")
        heartbeat = manifest.get("last_heartbeat_at") or manifest.get("updated_at")
        age = heartbeat_age(heartbeat)
        rows.append({
            "run_id": str(manifest.get("run_id")),
            "folder": str(manifest.get("folder") or ""),
            "title": sanitize_text(manifest.get("title") or "Legacy task"),
            "status": status, "updated_at": str(manifest.get("updated_at") or ""),
            "stalled": bool(status in {"queued", "running", "cancelling"}
                            and age is not None and age > 45),
            "active": manifest.get("run_id") in active_ids,
            "stage": manifest.get("stage"),
            "progress": max(0, min(100, progress)),
            "progress_mode": ("determinate" if progress > 0 or status == "completed"
                              else "indeterminate"),
            "elapsed_seconds": elapsed_seconds(
                manifest.get("started_at"), manifest.get("finished_at")),
            "result_kind": str(manifest.get("result_kind") or "unknown"),
            "artifact_path": manifest.get("artifact_path"),
            "parent_run_id": manifest.get("parent_run_id"),
            "operation": manifest.get("operation"),
            "error": sanitize_text(manifest.get("error") or ""),
            "error_category": "legacy_process" if manifest.get("error") else "",
            "origin": "app", "provider": "local", "model": "",
            "time_window": {"start": None, "end": None, "timezone": None},
            "heartbeat_at": manifest.get("last_heartbeat_at"), "checkpoint": {},
            "request_dispatched_at": None,
            "recovery_actions": (["retry"] if status in {
                "failed", "partial", "cancelled", "interrupted"} else
                ["cancel"] if status in {"queued", "running", "cancelling"} else []),
        })
    return sorted(rows, key=lambda row: (row["updated_at"], row["run_id"]), reverse=True)


operations_router = build_operations_router(
    jobs=jobs, repo=service.repo, job_rows=_job_rows, resolve_folder=_folder, data_root=DATA_ROOT,
    search_root=SEARCH_ROOT, project_root=PROJECT_ROOT, dataio=dataio,
    sanitize_text=sanitize_text)
app.include_router(operations_router)
generate_operation = next(
    route.endpoint for route in operations_router.routes
    if route.path.endswith("/generate") and "POST" in route.methods)
app.include_router(build_conversation_router(
    broker=conversation_broker, repo=service.repo, resolve_folder=_folder,
    generate=generate_operation))


if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def web_app(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        candidate = (WEB_DIST / full_path).resolve()
        if candidate.is_file() and WEB_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")

else:
    @app.get("/{full_path:path}", include_in_schema=False)
    def web_app(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        raise HTTPException(404, "Web assets are not built")
