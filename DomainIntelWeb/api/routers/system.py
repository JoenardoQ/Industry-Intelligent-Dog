from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..schemas import HealthState, ShutdownState
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
