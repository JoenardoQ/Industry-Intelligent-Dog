from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException

from ..schemas import (CancelState, GenerateRequest, JobAccepted, JobOutputState,
                       JobState)
from ..commands import search_command, search_cwd


def build_operations_router(*, jobs, job_rows: Callable[[], list[dict]],
                            repo,
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
        if job is not None:
            return {"cancelled": bool(job.cancel())}
        try:
            repo.recover_expired_tasks(actor="local-user", run_id=run_id)
            task = repo.get_task(run_id)
            if task["status"] == "running":
                repo.transition(run_id, expected={"running"}, target="cancelling",
                                error={"category": "cancel_requested",
                                       "message": "Cancellation requested from another session"})
            elif task["status"] in {"queued", "paused", "cancelling", "interrupted"}:
                repo.transition(run_id, expected={task["status"]}, target="cancelled",
                                error={"category": "cancel_requested",
                                       "message": "Cancelled by user"})
            else:
                raise HTTPException(409, "任务已处于不可取消的终态")
            return {"cancelled": True}
        except FileNotFoundError as exc:
            raise HTTPException(404, "任务不存在") from exc

    def submit(folder: str, request: GenerateRequest, *, parent_run_id: str = "",
               origin: str = "app"):
        from src.background_worker import _safe_environment
        effective = repo.effective_workflow_settings(folder, request.action)
        provider = request.provider.strip() or str(effective["provider"])
        execution_mode = request.execution_mode or str(effective["execution_mode"])
        pipeline_mode = request.pipeline_mode or str(effective["pipeline_mode"])
        if provider == "taskpack":
            provider, execution_mode = "", "taskpack"
        if execution_mode == "direct" and not provider:
            raise HTTPException(409, "全局设置缺少可直接执行的 Agent 或 API")
        request = request.model_copy(update={
            "provider": provider,
            "execution_mode": execution_mode,
            "pipeline_mode": pipeline_mode,
        })
        taskpack = request.execution_mode == "taskpack"
        public_direct = request.execution_mode == "direct" and request.provider == "public_sources"
        model_free = public_direct and (
            request.action in {"daily", "bootstrap", "history"} or
            (request.action in {"weekly", "monthly", "quarterly"}
             and request.pipeline_mode == "aggregate"))
        if request.execution_mode == "direct" and not model_free:
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
        if public_direct and request.action == "bootstrap":
            command_map["bootstrap"] = (
                "公开免凭据初始化行业研究",
                ["public-bootstrap", "--folder", folder])
        taskpack_commands = {
            "bootstrap": ("创建行业初始化任务包", ["bootstrap-industry", "--folder", folder]),
            "report": ("创建行业报告任务包", ["report-tasks", "--folder", folder]),
            "deep_report": ("创建深度研究任务包", ["deep-reports", "--folder", folder,
                                                     "--rtype", request.kind]),
            "impact": ("创建影响分析任务包", ["impact", "--folder", folder,
                                              "--event", request.event.strip()]),
        }
        if taskpack:
            if request.action not in taskpack_commands:
                raise HTTPException(400, "该操作不支持任务包；请选择 direct 并显式选择 Provider")
            title, args = taskpack_commands[request.action]
        elif request.action in command_map:
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
        if request.execution_mode == "direct":
            args.extend(["--provider", request.provider])
        args.extend(["--execution-mode", request.execution_mode])
        timeout = 14400 if request.action in {"history", "report", "deep_report"} else 3600
        return jobs.start(
            search_command(args), cwd=search_cwd(search_root),
            title=f"{title} · {folder}", timeout=timeout,
            env=_safe_environment(data_root, project_root),
            metadata={"folder": folder, "operation": request.action,
                      "operation_payload": {**request.model_dump(), "folder": folder},
                      "origin": origin,
                      "provider": ("taskpack" if taskpack else request.provider),
                      "execution_mode": request.execution_mode,
                      "requires_artifact": bool(
                          request.execution_mode == "direct" and
                          request.action in {"report", "deep_report", "impact", "lab"}),
                      "result_kind": ("task_package" if taskpack else
                                      "local_data" if request.action in {
                                          "daily", "history", "coverage", "bootstrap"}
                                      else "artifact"),
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
        authoritative = None
        try:
            authoritative = repo.get_task(run_id)
        except FileNotFoundError:
            pass
        state = authoritative.get("status") if authoritative else row.get("status") if row else None
        if state is None:
            raise HTTPException(404, "任务不存在")
        if state not in {"paused", "failed", "partial", "cancelled", "interrupted"}:
            raise HTTPException(409, "只有失败、部分完成、取消或中断任务可以重试")
        payload = (authoritative.get("input") if authoritative else
                   row.get("operation_payload"))
        operation = (authoritative.get("operation") if authoritative else
                     row.get("operation"))
        if not isinstance(payload, dict) or not operation:
            raise HTTPException(409, "历史任务缺少可验证的操作元数据，拒绝重放命令")
        folder = resolve_folder(str(payload.get("folder") or ""))
        try:
            request = GenerateRequest.model_validate({**payload, "action": operation})
        except ValueError as exc:
            raise HTTPException(409, "历史操作元数据无效") from exc
        job = submit(folder, request, parent_run_id=run_id,
                     origin=str(authoritative.get("origin") or "app")
                     if authoritative else "app")
        return {"run_id": job.run_id, "status": "queued", "title": job.title,
                "action": request.action}

    return router
