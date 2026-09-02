from __future__ import annotations

from typing import Callable, Literal

from fastapi import APIRouter, HTTPException

from ..schemas import AutomationState, JobAccepted, ScheduleState, ScheduleUpdate


Action = Literal["daily", "weekly", "monthly", "quarterly"]


def build_automation_router(*, automation,
                            resolve_folder: Callable[[str], str]) -> APIRouter:
    router = APIRouter(prefix="/api/industries/{folder}/automation",
                       tags=["automation"])

    @router.get("", response_model=AutomationState)
    def schedules(folder: str) -> dict:
        folder = resolve_folder(folder)
        return {"email_delivery": False, "schedules": automation.snapshot(folder)}

    @router.put("/{action}", response_model=ScheduleState)
    def configure(folder: str, action: Action, request: ScheduleUpdate) -> dict:
        folder = resolve_folder(folder)
        try:
            from src.services.capability_manifest import SCHEDULABLE_PROVIDER_IDS
            if request.provider and request.provider not in SCHEDULABLE_PROVIDER_IDS:
                raise ValueError("不支持的模型提供方式")
            automation.configure(
                folder, action, enabled=request.enabled,
                local_time=request.local_time, weekday=request.weekday,
                monthday=request.monthday, timezone_name=request.timezone,
                catch_up=request.catch_up, pipeline_mode=request.pipeline_mode,
                provider=request.provider)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return next(row for row in automation.snapshot(folder)
                    if row["action"] == action)

    @router.post("/{action}/run", status_code=202, response_model=JobAccepted)
    def run_now(folder: str, action: Action) -> dict:
        folder = resolve_folder(folder)
        try:
            job = automation.run_now(folder, action)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": job.run_id, "status": "queued", "action": action,
                "email_delivery": False}

    return router
