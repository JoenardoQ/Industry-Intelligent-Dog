from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from intdog_core.models import json_value

from ..schemas import (
    CountState, SourceCampaignCreate, SourceCampaignDetail, SourceCampaignPage,
    SourceCampaignExecutionRequest, SourceCampaignState, SourceCandidateReview,
    SourceCandidateState, SourceCreate, JobAccepted,
    SourceMutationState, SourceReassessmentRequest, SourceReassessmentState,
    SourcesState,
)
from ..commands import search_command, search_cwd


SOURCE_TARGET = 8


def _child_environment(data_root: Path, project_root: Path) -> dict[str, str]:
    from src.background_worker import _safe_environment

    return _safe_environment(data_root, project_root)


def _page(items: list[dict], *, offset: int, limit: int) -> dict:
    rows = items[offset:offset + limit]
    next_offset = offset + limit if offset + limit < len(items) else None
    return {"items": rows, "total": len(items), "offset": offset,
            "limit": limit, "next_offset": next_offset}


def _query_ledger(repo, campaign_id: str) -> list[dict]:
    with repo.connection() as con:
        rows = con.execute("""SELECT * FROM source_queries WHERE campaign_id=?
            ORDER BY round_no,created_at,id""", (campaign_id,)).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        item["dimensions"] = json_value(item.pop("dimensions_json"), {})
        item["outcome"] = json_value(item.pop("outcome_json"), {})
        output.append(item)
    return output


def _campaign_in_folder(repo, folder: str, campaign_id: str) -> dict:
    campaign = repo.get_source_campaign(campaign_id)
    if campaign["industry_id"] != repo.industry_id(folder):
        raise FileNotFoundError(f"source campaign not found: {campaign_id}")
    return campaign


def _source_gaps(campaign: dict, candidates: list[dict],
                 queries: list[dict]) -> list[dict]:
    output = []
    for category in campaign["targets"]:
        matches = [item for item in candidates if item["category"] == category]
        usable = [item for item in matches if item["status"] == "active"]
        category_queries = [item for item in queries
                            if item["dimensions"].get("source_type") == category]
        reasons = Counter(item.get("status_reason") or "unspecified"
                          for item in matches if item["status"] == "rejected")
        current = len(usable)
        gap = max(0, SOURCE_TARGET - current)
        output.append({
            "category": category, "current": current, "target": SOURCE_TARGET,
            "gap": gap, "query_count": len(category_queries),
            "candidate_count": len(matches), "rejection_reasons": dict(reasons),
            "explanation": (
                f"{category} 当前 {current} / {SOURCE_TARGET}；缺口 {gap}；"
                f"已执行 {len(category_queries)} 条查询，发现 {len(matches)} 个候选。"
                "少于 8 个表示权威来源池仍未达到深化目标，并不等同于检索完整。"),
        })
    return output


def build_sources_router(*, data_root: Path, dataio, service,
                         resolve_folder: Callable[[str], str], jobs=None,
                         search_root: Path | None = None,
                         project_root: Path | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/industries/{folder}", tags=["sources"])

    @router.get("/sources", response_model=SourcesState)
    def sources(folder: str) -> dict:
        folder = resolve_folder(folder)
        payload = dataio.read_sources(data_root, folder)
        return {"industry": payload.pop("industry", folder), "categories": payload}

    @router.post("/sources", status_code=201, response_model=SourceMutationState)
    def add_source(folder: str, request: SourceCreate) -> dict:
        folder = resolve_folder(folder)
        if request.category not in dataio.SOURCE_CATEGORIES:
            raise HTTPException(400, "未知信息源类别")
        service.repo.upsert_source(folder, request.category, {
            **request.model_dump(),
            "added_manually": True,
            "monitoring_status": "recommended_manual",
        })
        return {"added": True}

    @router.delete("/sources", response_model=CountState)
    def remove_source(folder: str, category: str, url: str) -> dict:
        folder = resolve_folder(folder)
        if category not in dataio.SOURCE_CATEGORIES:
            raise HTTPException(400, "未知信息源类别")
        return {"deleted": dataio.delete_source(data_root, folder, category, url)}

    @router.get("/source-campaigns", response_model=SourceCampaignPage)
    def source_campaigns(folder: str,
                         offset: int = Query(default=0, ge=0),
                         limit: int = Query(default=20, ge=1, le=100)) -> dict:
        rows = service.repo.list_source_campaigns(resolve_folder(folder))
        return _page(rows, offset=offset, limit=limit)

    @router.post("/source-campaigns", status_code=201,
                 response_model=SourceCampaignState)
    def create_source_campaign(folder: str, request: SourceCampaignCreate) -> dict:
        try:
            return service.repo.create_source_campaign(
                resolve_folder(folder), request.targets, request.budget)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/source-campaigns/{campaign_id}",
                response_model=SourceCampaignDetail)
    def source_campaign(folder: str, campaign_id: str,
                        offset: int = Query(default=0, ge=0),
                        limit: int = Query(default=20, ge=1, le=100)) -> dict:
        folder = resolve_folder(folder)
        try:
            campaign = _campaign_in_folder(service.repo, folder, campaign_id)
            candidates = service.repo.list_source_candidates(campaign_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        queries = _query_ledger(service.repo, campaign_id)
        return {**campaign,
                "candidate_page": _page(candidates, offset=offset, limit=limit),
                "query_ledger": queries,
                "source_gaps": _source_gaps(campaign, candidates, queries),
                "round_history": service.repo.list_source_campaign_rounds(campaign_id)}

    @router.post("/source-campaigns/{campaign_id}/execute", status_code=202,
                 response_model=JobAccepted)
    def execute_source_campaign(folder: str, campaign_id: str,
                                request: SourceCampaignExecutionRequest) -> dict:
        folder = resolve_folder(folder)
        try:
            campaign = _campaign_in_folder(service.repo, folder, campaign_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        if campaign["status"] in {"converged", "failed"}:
            raise HTTPException(409, "终态来源活动不能再次执行")
        if jobs is None or search_root is None or project_root is None:
            raise HTTPException(503, "本地任务运行时未配置")
        from src.services.provider_readiness import provider_readiness
        readiness = provider_readiness(request.provider, data_root / folder)
        if not readiness.get("ready"):
            raise HTTPException(
                409, f"Provider {request.provider} 未就绪：{readiness.get('detail', '请检查连接设置')}")
        args = ["run-source-campaign", "--folder", folder,
                "--campaign-id", campaign_id, "--provider", request.provider]
        job = jobs.start(
            search_command(args), cwd=search_cwd(search_root),
            title=f"来源检索活动 · {folder}", timeout=3600,
            env=_child_environment(data_root, project_root),
            metadata={"operation": "source_campaign",
                      "operation_payload": {"folder": folder,
                                            "campaign_id": campaign_id,
                                            "provider": request.provider}})
        return {"run_id": job.run_id, "status": "queued", "title": job.title,
                "action": "source_campaign"}

    @router.post("/source-candidates/{candidate_id}/review",
                 response_model=SourceCandidateState)
    def review_source_candidate(folder: str, candidate_id: str,
                                request: SourceCandidateReview) -> dict:
        folder = resolve_folder(folder)
        try:
            item = service.repo.review_source_candidate(
                folder, candidate_id, decision=request.decision,
                actor=request.actor, reason=request.reason)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {**item, "review": request.model_dump()}

    @router.post("/sources/{source_id}/reassess",
                 response_model=SourceReassessmentState)
    def reassess_source(folder: str, source_id: str,
                        request: SourceReassessmentRequest) -> dict:
        folder = resolve_folder(folder)
        try:
            return service.repo.reassess_source(
                folder, source_id, decision=request.decision,
                actor=request.actor, reason=request.reason)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
