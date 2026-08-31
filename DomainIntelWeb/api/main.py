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
from .automation import AutomationScheduler
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


DATA_ROOT = Path(
    os.environ.get("DOMAIN_INTEL_DATA_ROOT")
    or os.environ.get("INTDOG_DATA_ROOT")
    or PROJECT_ROOT / "DomainIntelData"
).resolve()
WEB_DIST = PROJECT_ROOT / "DomainIntelWeb" / "dist"

jobs = JobManager(DATA_ROOT)
service = IntDogService(DATA_ROOT)
automation = AutomationScheduler(
    DATA_ROOT, jobs, search_root=SEARCH_ROOT, project_root=PROJECT_ROOT)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    automation.start()
    yield
    automation.stop(timeout=3)
    jobs.shutdown(timeout=3)


app = FastAPI(title="IntDog Local API", version="4.0.0", lifespan=lifespan)
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
        or item.get("publisher") or "N/A"
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
    data_root=DATA_ROOT, dataio=dataio, resolve_folder=_folder)
industries_router = build_industries_router(
    data_root=DATA_ROOT, dataio=dataio, resolve_folder=_folder)
content_router = build_content_router(
    data_root=DATA_ROOT, dataio=dataio, resolve_folder=_folder)
system_router = build_system_router(
    data_root=DATA_ROOT, jobs=jobs, automation=automation,
    session_required=bool(os.environ.get("INTDOG_SESSION_TOKEN")))
app.include_router(daily_router)
app.include_router(sources_router)
app.include_router(industries_router)
app.include_router(content_router)
app.include_router(system_router)
app.include_router(build_automation_router(
    automation=automation, resolve_folder=_folder))
intelligence_router = build_intelligence_router(
    data_root=DATA_ROOT, service=service, resolve_folder=_folder, dataio=dataio)
app.include_router(intelligence_router)
app.include_router(build_recovery_router(data_root=DATA_ROOT, dataio=dataio))
agent_bridge_router = build_agent_bridge_router(
    data_root=DATA_ROOT, dataio=dataio, resolve_folder=_folder, service=service)
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
    rows = []
    active_ids = {job.run_id for job in jobs.active()}
    for row in jobs.store.list():
        clean = dict(row)
        clean["active"] = clean.get("run_id") in active_ids
        heartbeat = clean.get("last_heartbeat_at") or clean.get("updated_at")
        try:
            heartbeat_age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                str(heartbeat).replace("Z", "+00:00"))).total_seconds()
        except (TypeError, ValueError):
            heartbeat_age = None
        clean["heartbeat_age_seconds"] = heartbeat_age
        clean["stalled"] = bool(
            clean.get("status") in {"queued", "running", "cancelling"}
            and heartbeat_age is not None and heartbeat_age > 45
        )
        clean["title"] = sanitize_text(clean.get("title") or "")
        clean["error"] = sanitize_text(clean.get("error") or "")
        rows.append(clean)
    return rows


operations_router = build_operations_router(
    jobs=jobs, job_rows=_job_rows, resolve_folder=_folder, data_root=DATA_ROOT,
    search_root=SEARCH_ROOT, project_root=PROJECT_ROOT, dataio=dataio,
    sanitize_text=sanitize_text)
app.include_router(operations_router)


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
