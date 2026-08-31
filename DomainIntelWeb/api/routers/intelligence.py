from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from ..schemas import (CoverageAttemptCreate, CoverageCellCreate,
                       CoverageAttemptState, CoverageCellState, CoverageState,
                       HistoryCoverageState,
                       KnowledgeEntityDetail, KnowledgeEntityPage,
                       StoryDetailState, StoryListState, StoryMergeRequest,
                       StorySplitRequest, StoryUnlockRequest)


def _query_for(cell: dict) -> str:
    d = cell["dimensions"]
    parts = [d.get("subdomain"), d.get("chain_stage"), d.get("entity_type"),
             d.get("event_type"), d.get("time_horizon")]
    subject = " ".join(value for value in parts if value and value != "unknown")
    if d.get("region") in {"china", "中国", "cn"}:
        authority = "中国 官方 政策 标准 白皮书 企业公告"
    else:
        authority = "official regulator standards filing peer reviewed"
    source = d.get("source_type")
    return " ".join(value for value in (subject, source, authority) if value)


def build_intelligence_router(*, data_root: Path, service,
                              resolve_folder: Callable[[str], str], dataio) -> APIRouter:
    router = APIRouter(prefix="/api/industries/{folder}", tags=["intelligence"])

    @router.get("/history", response_model=HistoryCoverageState)
    def history(folder: str) -> dict:
        """Read live long-horizon coverage without mutating compatibility files."""
        from src.history_backfill import POLICIES, evaluate_history
        from src.industry_store import IndustryStore

        folder = resolve_folder(folder)

        class HistoryView:
            _key = staticmethod(IndustryStore._key)

            def list_daily_range(self, days: int, end_date: str | None = None):
                rows = service.repo.list_documents(folder, limit=100_000)
                if not end_date:
                    return rows
                from datetime import date, timedelta
                finish = date.fromisoformat(end_date)
                start = finish - timedelta(days=max(1, days) - 1)
                return [row for row in rows if start.isoformat() <= str(
                    row.get("published_at") or row.get("date") or "")[:10]
                        <= finish.isoformat()]

        rows = []
        for horizon in POLICIES:
            state = evaluate_history(HistoryView(), horizon)
            manifest_path = (data_root / folder / "one_time" / "research" /
                             "history" / f"{horizon}.json")
            manifest = service.read_json(manifest_path, {})
            state.update({
                "status": manifest.get("status") or ("ready" if state["ready"] else "not_started"),
                "updated_at": manifest.get("updated_at"),
                "attempts": len(manifest.get("attempts") or []),
            })
            state.pop("buckets", None)
            rows.append(state)
        return {"items": rows}

    @router.get("/knowledge/entities", response_model=KnowledgeEntityPage)
    def knowledge_entities(folder: str, query: str = Query(default="", max_length=200),
                           kind: str = Query(default="", max_length=80),
                           country: str = Query(default="", max_length=100),
                           status: str = Query(default="", max_length=80),
                           chain: str = Query(default="", max_length=200),
                           offset: int = Query(default=0, ge=0),
                           limit: int = Query(default=50, ge=1, le=100)) -> dict:
        return service.repo.page_knowledge_entities(
            resolve_folder(folder), query=query, kind=kind, country=country,
            status=status, chain=chain, offset=offset, limit=limit)

    @router.get("/knowledge/entities/{entity_id}", response_model=KnowledgeEntityDetail)
    def knowledge_entity(folder: str, entity_id: str) -> dict:
        try:
            return service.repo.knowledge_entity_detail(resolve_folder(folder), entity_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/stories", response_model=StoryListState)
    def stories(folder: str, limit: int = Query(default=100, ge=1, le=500)) -> dict:
        folder = resolve_folder(folder)
        rows = service.repo.list_stories(folder, limit=limit)
        return {"items": rows, "total": len(rows)}

    @router.get("/stories/{story_id}", response_model=StoryDetailState)
    def story(folder: str, story_id: str) -> dict:
        try:
            return service.repo.story_detail(resolve_folder(folder), story_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/stories/{story_id}/merge", response_model=StoryDetailState)
    def merge_story(folder: str, story_id: str, request: StoryMergeRequest) -> dict:
        folder = resolve_folder(folder)
        try:
            service.repo.merge_stories(
                folder, story_id, request.source_story_id, actor="web")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return service.repo.story_detail(folder, story_id)

    @router.post("/stories/{story_id}/split", status_code=201,
                 response_model=StoryDetailState)
    def split_story(folder: str, story_id: str, request: StorySplitRequest) -> dict:
        folder = resolve_folder(folder)
        try:
            created = service.repo.split_story(
                folder, story_id, request.document_ids, request.title, actor="web")
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return service.repo.story_detail(folder, created)

    @router.post("/stories/{story_id}/unlock", response_model=StoryDetailState)
    def unlock_story(folder: str, story_id: str, request: StoryUnlockRequest) -> dict:
        folder = resolve_folder(folder)
        try:
            service.repo.unlock_story_documents(
                folder, story_id, request.document_ids, actor="web")
            return service.repo.story_detail(folder, story_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/coverage", response_model=CoverageState)
    def coverage(folder: str) -> dict:
        folder = resolve_folder(folder)
        cells = service.repo.list_coverage(folder)
        return {"cells": [{**cell, "attempt_history":
                            service.repo.coverage_attempts(cell["id"])} for cell in cells],
                "summary": {
                    "total": len(cells),
                    "gaps": sum(cell["status"] == "gap" for cell in cells),
                    "source_yield": sum(cell["source_yield"] for cell in cells),
                    "entity_yield": sum(cell["entity_yield"] for cell in cells),
                }}

    @router.post("/coverage/cells", status_code=201,
                 response_model=CoverageCellState)
    def create_coverage_cell(folder: str, request: CoverageCellCreate) -> dict:
        folder = resolve_folder(folder)
        cell_id = service.repo.upsert_coverage_cell(
            folder, request.dimensions, priority=request.priority,
            status=request.status, rationale=request.rationale)
        return next(cell for cell in service.repo.list_coverage(folder)
                    if cell["id"] == cell_id)

    @router.post("/coverage/initialize", status_code=201)
    def initialize_coverage(folder: str) -> dict:
        folder = resolve_folder(folder)
        knowledge = dataio.read_knowledge(data_root, folder)
        chain = knowledge.get("chains") or []
        stages = [str(node.get("name") or node.get("label") or "unknown")
                  for node in chain] or ["industry-wide"]
        created = []
        for stage in stages:
            for region in ("china", "global"):
                dimensions = {
                    "region": region, "subdomain": "unknown", "chain_stage": stage,
                    "entity_type": "company/research_group",
                    "source_type": "primary/authoritative",
                    "event_type": "technology/market/policy", "time_horizon": "12m",
                }
                created.append(service.repo.upsert_coverage_cell(
                    folder, dimensions, priority=80 if region == "china" else 70,
                    rationale="产业链端点与地区的一手证据覆盖"))
        return {"created_or_updated": len(created), "cell_ids": created}

    @router.post("/coverage/plan")
    def plan_coverage(folder: str, limit: int = Query(default=10, ge=1, le=50)) -> dict:
        folder = resolve_folder(folder)
        cells = [cell for cell in service.repo.list_coverage(folder)
                 if cell["status"] in {"gap", "thin"}][:limit]
        planned = []
        for cell in cells:
            query = _query_for(cell)
            attempt_id = service.repo.record_coverage_attempt(
                folder, cell["id"], query=query,
                rationale="按未覆盖单元的优先级生成；结果仍需 URL 与发布者验证")
            planned.append({"attempt_id": attempt_id, "cell_id": cell["id"],
                            "query": query, "dimensions": cell["dimensions"],
                            "validation_required": True})
        return {"items": planned, "stopping_reason": (
            "当前没有 gap/thin 单元" if not planned else "达到本次计划上限")}

    @router.post("/coverage/cells/{cell_id}/attempts", status_code=201,
                 response_model=CoverageAttemptState)
    def record_attempt(folder: str, cell_id: str,
                       request: CoverageAttemptCreate) -> dict:
        folder = resolve_folder(folder)
        try:
            attempt_id = service.repo.record_coverage_attempt(
                folder, cell_id, query=request.query, rationale=request.rationale,
                status=request.status, source_yield=request.source_yield,
                entity_yield=request.entity_yield, evidence=request.evidence,
                stopping_reason=request.stopping_reason)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        service.repo.audit(
            "coverage.manual_attempt", "coverage_cell", object_id=cell_id,
            actor=request.actor,
            details={"folder": folder, "attempt_id": attempt_id,
                     "source_yield": request.source_yield,
                     "entity_yield": request.entity_yield,
                     "evidence_kind": "manual_assertion"},
        )
        return next(item for item in service.repo.coverage_attempts(cell_id)
                    if item["id"] == attempt_id)

    return router
