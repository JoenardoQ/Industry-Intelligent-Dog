from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException

from ..schemas import (CancelState, GenerateRequest, JobAccepted, JobOutputState,
                       JobState)
from ..commands import search_command, search_cwd


def build_operations_router(*, jobs, job_rows: Callable[[], list[dict]],
                            resolve_folder: Callable[[str], str], data_root: Path,
                            search_root: Path, project_root: Path, dataio,
                            sanitize_text: Callable[[object], str]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["operations"])

    @router.get("/jobs", response_model=list[JobState])
    def list_jobs() -> list[dict]:
        return job_rows()

    @router.get("/jobs/{run_id}/output", response_model=JobOutputState)
    def job_output(run_id: str) -> dict:
        row = next((item for item in jobs.store.list()
                    if item.get("run_id") == run_id), None)
        if row is None:
            raise HTTPException(404, "任务不存在")
        return {"run_id": run_id, "output": sanitize_text(jobs.store.read_output(row))}

    @router.post("/jobs/{run_id}/cancel", response_model=CancelState)
    def cancel_job(run_id: str) -> dict:
        job = next((item for item in jobs.active() if item.run_id == run_id), None)
        if job is None:
            raise HTTPException(409, "任务不在当前服务会话中运行")
        return {"cancelled": bool(job.cancel())}

    def submit(folder: str, request: GenerateRequest, *, parent_run_id: str = ""):
        model_free = (request.action == "daily" or
                      (request.action in {"weekly", "monthly", "quarterly"}
                       and request.pipeline_mode == "aggregate") or
                      (request.action == "bootstrap" and not request.provider))
        if request.provider and not model_free:
            from src.services.provider_readiness import provider_readiness
            readiness = provider_readiness(request.provider, data_root / folder)
            if not readiness.get("ready"):
                raise HTTPException(409, f"Provider {request.provider} 未就绪：{readiness.get('detail', '请检查连接设置')}")
        period_commands = {
            action: ((f"聚合{label}情报", [f"crawl-{action}", "--folder", folder])
                     if request.pipeline_mode == "aggregate"
                     else (f"生成{label}报告", ["generate-period", "--folder", folder,
                                                "--kind", action]))
            for action, label in (("weekly", "每周"), ("monthly", "每月"),
                                  ("quarterly", "季度"))
        }
        command_map = {
            "daily": ("抓取每日情报", ["crawl-daily", "--folder", folder]),
            **period_commands,
            "lab": ("运行 Intelligence Lab", ["run-lab", "--folder", folder]),
            "bootstrap": ("初始化行业研究", ["bootstrap-industry", "--folder", folder]),
            "coverage": ("执行覆盖搜索", ["execute-coverage", "--folder", folder]),
        }
        if request.action in command_map:
            title, args = command_map[request.action]
        elif request.action == "report":
            if request.kind not in dataio.INDUSTRY_REPORT_IDS:
                raise HTTPException(400, "未知行业报告类型")
            title, args = "生成行业报告", ["generate-report", "--folder", folder,
                                             "--kind", request.kind]
        elif request.action == "deep_report":
            if request.kind not in {"quarterly", "chain", "landscape", "market"}:
                raise HTTPException(400, "未知深度研究类型")
            title, args = "生成深度研究", ["generate-deep-report", "--folder", folder,
                                           "--rtype", request.kind]
        elif request.action == "history":
            horizons = {"weekly", "monthly", "quarterly", "semiannual",
                        "biennial", "fiveyear"}
            if request.kind not in horizons:
                raise HTTPException(400, "未知历史采集周期")
            title, args = "回填长周期历史证据", ["backfill-history", "--folder", folder,
                                                 "--kind", request.kind]
        else:
            if not request.event.strip():
                raise HTTPException(400, "影响分析需要事件描述")
            title, args = "生成事件影响分析", ["generate-impact", "--folder", folder,
                                               "--event", request.event.strip()]
        if request.provider and not model_free:
            args.extend(["--provider", request.provider])
        timeout = 14400 if request.action in {"history", "report", "deep_report"} else 3600
        return jobs.start(
            search_command(args), cwd=search_cwd(search_root),
            title=f"{title} · {folder}", timeout=timeout,
            env={**os.environ, "DOMAIN_INTEL_DATA_ROOT": str(data_root),
                 "INTDOG_PROJECT_ROOT": str(project_root), "PYTHONUTF8": "1",
                 "INTDOG_DISABLE_EMAIL": "1"},
            metadata={"operation": request.action,
                      "operation_payload": {**request.model_dump(), "folder": folder},
                      "parent_run_id": parent_run_id or None})

    @router.post("/industries/{folder}/generate", status_code=202,
                 response_model=JobAccepted)
    def generate(folder: str, request: GenerateRequest) -> dict:
        folder = resolve_folder(folder)
        job = submit(folder, request)
        return {"run_id": job.run_id, "status": "queued", "title": job.title,
                "action": request.action}

    @router.post("/jobs/{run_id}/retry", status_code=202, response_model=JobAccepted)
    def retry_job(run_id: str) -> dict:
        row = next((item for item in jobs.store.list()
                    if item.get("run_id") == run_id), None)
        if row is None:
            raise HTTPException(404, "任务不存在")
        if row.get("status") not in {"failed", "partial", "cancelled", "interrupted"}:
            raise HTTPException(409, "只有失败、部分完成、取消或中断任务可以重试")
        payload = row.get("operation_payload")
        if not isinstance(payload, dict) or not row.get("operation"):
            raise HTTPException(409, "历史任务缺少可验证的操作元数据，拒绝重放命令")
        folder = resolve_folder(str(payload.get("folder") or ""))
        try:
            request = GenerateRequest.model_validate({**payload, "action": row["operation"]})
        except ValueError as exc:
            raise HTTPException(409, "历史操作元数据无效") from exc
        job = submit(folder, request, parent_run_id=run_id)
        return {"run_id": job.run_id, "status": "queued", "title": job.title,
                "action": request.action}

    return router
