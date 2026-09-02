from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from ..schemas import (CoverageAttemptCreate, CoverageCellCreate,
                       CoverageAttemptState, CoverageCellState, CoverageState,
                       CoverageCandidateState,
                       CoverageExpansionExecutionRequest, CoverageExpansionRequest,
                       CoverageFrontierState, CoverageReviewQueueState,
                       CoverageRoundState, JobAccepted,
                       EntityCandidateReview, EntityCandidateReviewState,
                       EntityCoverageMatrixState,
                       HistoryCoverageState,
                       KnowledgeEntityDetail, KnowledgeEntityPage,
                       QualityDriftState, StoryMomentumBatchState, StoryMomentumState,
                       StoryDetailState, StoryListState, StoryMergeRequest,
                       StoryIgnoreRequest, StorySplitRequest, StoryUnlockRequest)
from ..commands import search_command, search_cwd


def _child_environment(data_root: Path, project_root: Path) -> dict[str, str]:
    from src.background_worker import _safe_environment

    return _safe_environment(data_root, project_root)


def _entity_coverage_view(repo, folder: str) -> dict:
    from src.entity_coverage import materialize_coverage_matrix

    return materialize_coverage_matrix(repo, folder)


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
                              resolve_folder: Callable[[str], str], dataio,
                              jobs=None, search_root: Path | None = None,
                              project_root: Path | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/industries/{folder}", tags=["intelligence"])

    @router.get("/coverage-matrix", response_model=EntityCoverageMatrixState)
    def entity_coverage_matrix(folder: str) -> dict:
        return _entity_coverage_view(service.repo, resolve_folder(folder))

    @router.post("/coverage-expansions", response_model=CoverageFrontierState)
    def expand_entity_coverage(folder: str,
                               request: CoverageExpansionRequest) -> dict:
        from dataclasses import asdict
        from src.entity_coverage import plan_entity_frontier

        folder = resolve_folder(folder)
        matrix = _entity_coverage_view(service.repo, folder)
        history = service.repo.list_coverage_rounds(folder)
        matrix["round_history"] = [item["outcome"] for item in reversed(history)]
        frontier = plan_entity_frontier(matrix, round_no=len(history) + 1)
        persisted = service.repo.create_coverage_round(folder, frontier)
        return {**asdict(frontier), "round_id": persisted["id"],
                "round_no": persisted["round_no"], "status": persisted["status"]}

    @router.get("/coverage-expansions", response_model=list[CoverageRoundState])
    def coverage_expansion_history(folder: str) -> list[dict]:
        return service.repo.list_coverage_rounds(resolve_folder(folder))

    @router.post("/coverage-expansions/{round_id}/execute", status_code=202,
                 response_model=JobAccepted)
    def execute_coverage_expansion(folder: str, round_id: str,
                                   request: CoverageExpansionExecutionRequest) -> dict:
        folder = resolve_folder(folder)
        rounds = service.repo.list_coverage_rounds(folder)
        if not any(item["id"] == round_id for item in rounds):
            raise HTTPException(404, "coverage round not found")
        if jobs is None or search_root is None or project_root is None:
            raise HTTPException(503, "本地任务运行时未配置")
        provider = request.provider or service.repo.effective_workflow_settings(
            folder, "coverage_expansion")["provider"]
        if provider == "taskpack":
            raise HTTPException(409, "覆盖扩展需要可直接运行的智能体；请在智能体设置中选择本机 Agent 或 API")
        from src.services.provider_readiness import provider_readiness
        readiness = provider_readiness(provider, data_root / folder)
        if not readiness.get("ready"):
            raise HTTPException(
                409, f"Provider {provider} 未就绪：{readiness.get('detail', '请检查连接设置')}")
        args = ["execute-coverage", "--folder", folder,
                "--coverage-round-id", round_id, "--provider", provider]
        job = jobs.start(
            search_command(args), cwd=search_cwd(search_root),
            title=f"实体与关系覆盖扩展 · {folder}", timeout=3600,
            env=_child_environment(data_root, project_root),
            metadata={"operation": "coverage_expansion",
                      "operation_payload": {"folder": folder,
                                            "round_id": round_id,
                                            "provider": provider}})
        return {"run_id": job.run_id, "status": "queued", "title": job.title,
                "action": "coverage_expansion"}

    @router.get("/coverage-review-queue", response_model=CoverageReviewQueueState)
    def coverage_review_queue(folder: str) -> dict:
        return service.repo.list_coverage_review_queue(resolve_folder(folder))

    @router.post("/entity-candidates/{candidate_id}/review",
                 response_model=EntityCandidateReviewState)
    def review_entity_candidate(folder: str, candidate_id: str,
                                request: EntityCandidateReview) -> dict:
        from src.entity_coverage import resolve_entity_candidate

        folder = resolve_folder(folder)
        persistent = None
        try:
            persistent = service.repo.get_coverage_candidate(
                folder, candidate_id, kind="entity")
        except FileNotFoundError:
            pass
        try:
            source_candidate = (None if persistent else
                                service.repo.get_source_candidate(folder, candidate_id))
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        candidate = (persistent["payload"] if persistent
                     else source_candidate.get("entity"))
        if not isinstance(candidate, dict):
            raise HTTPException(409, "source candidate has no entity identity payload")
        if request.decision == "approve":
            try:
                result = resolve_entity_candidate(service.repo, folder, candidate)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        elif request.decision == "manual_review":
            result = {"decision": "manual_review", "reason": request.reason,
                      "entity_id": None}
        else:
            result = {"decision": "rejected", "reason": request.reason,
                      "entity_id": None}
        review = request.model_dump()
        if persistent:
            target = request.decision
            if target == "approve":
                with service.repo.connection() as con:
                    materialized = con.execute("""SELECT 1 FROM industry_entities
                        WHERE industry_id=? AND entity_id=? AND status='accepted'""",
                        (service.repo.industry_id(folder), result.get("entity_id"))).fetchone()
                if not materialized:
                    target = "manual_review"
                    result = {"decision": "manual_review",
                              "reason": "current_industry_evidence_required",
                              "entity_id": result.get("entity_id")}
            service.repo.review_coverage_candidate(
                folder, candidate_id, kind="entity", decision=target,
                actor=request.actor, reason=result["reason"],
                entity_id=result.get("entity_id") if target == "approve" else None)
        else:
            service.repo.audit("entity_candidate_review", "source_candidate",
                               object_id=candidate_id, actor=request.actor,
                               details={**review, "result": result})
        return {"candidate_id": candidate_id, **result, "review": review}

    @router.post("/relation-candidates/{candidate_id}/review",
                 response_model=CoverageCandidateState)
    def review_relation_candidate(folder: str, candidate_id: str,
                                  request: EntityCandidateReview) -> dict:
        folder = resolve_folder(folder)
        try:
            return service.repo.review_coverage_candidate(
                folder, candidate_id, kind="relation", decision=request.decision,
                actor=request.actor, reason=request.reason)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

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

    @router.get("/stories-momentum", response_model=StoryMomentumBatchState)
    def stories_momentum(folder: str,
                         story_ids: str = Query(default="", max_length=20_000)) -> dict:
        from src.signal_momentum import compute_story_momentum

        folder = resolve_folder(folder)
        ids = list(dict.fromkeys(value.strip() for value in story_ids.split(",")
                                 if value.strip()))[:500]
        observations = service.repo.list_story_observations_batch(folder, ids)
        items = []
        for story_id in ids:
            result = compute_story_momentum(observations.get(story_id, []))
            timeline = result.get("timeline", [])
            items.append({"story_id": story_id,
                          "first_appearance": (timeline[0]["intelligence_date"] if timeline else None),
                          "last_observation": (timeline[-1]["intelligence_date"] if timeline else None),
                          **result})
        return {"items": items, "total": len(items)}

    @router.get("/stories/{story_id}", response_model=StoryDetailState)
    def story(folder: str, story_id: str) -> dict:
        try:
            return service.repo.story_detail(resolve_folder(folder), story_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/stories/{story_id}/momentum", response_model=StoryMomentumState)
    def story_momentum(folder: str, story_id: str) -> dict:
        from src.signal_momentum import compute_story_momentum

        folder = resolve_folder(folder)
        try:
            service.repo.story_detail(folder, story_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        result = compute_story_momentum(
            service.repo.list_story_observations(folder, story_id))
        return {"story_id": story_id, "first_appearance": None,
                "last_observation": None, **result}

    @router.get("/quality-drift", response_model=QualityDriftState)
    def quality_drift(folder: str,
                      as_of: str = Query(default="", max_length=10)) -> dict:
        from datetime import datetime
        from math import ceil
        from zoneinfo import ZoneInfo
        from src.quality_drift import analyze_quality_drift, evaluate_columnar_triggers

        folder = resolve_folder(folder)
        observations = service.repo.list_quality_observations(folder)
        if not as_of:
            as_of = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        try:
            result = analyze_quality_drift(observations, as_of=as_of)
        except ValueError as exc:
            raise HTTPException(422, "as_of must be an ISO calendar date") from exc
        with service.repo.connection() as con:
            document_count = int(con.execute("""SELECT COUNT(*) FROM industry_documents
                WHERE industry_id=? AND deleted_at IS NULL""",
                (service.repo.industry_id(folder),)).fetchone()[0])
        latency = sorted(float(item["numerator"]) / float(item["denominator"])
                         for item in observations
                         if item["metric"] == "long_query_latency_seconds" and
                         float(item["denominator"]) > 0)
        p95 = latency[max(0, ceil(len(latency) * .95) - 1)] if latency else 0.0
        write_blocked = any(item["metric"] == "sqlite_write_blocked" and
                            float(item["numerator"]) > 0 for item in observations)
        backup_rows = [item for item in observations
                       if item["metric"] == "backup_size_bytes"]
        backup_size = int(backup_rows[-1]["numerator"]) if backup_rows else 0
        backup_limit = int(backup_rows[-1]["dimensions"].get(
            "max_backup_size_bytes", 4 * 1024**3)) if backup_rows else 4 * 1024**3
        result["columnar_prototype"] = evaluate_columnar_triggers(
            document_count=document_count, long_query_p95_seconds=p95,
            sqlite_write_blocked=write_blocked, backup_size_bytes=backup_size,
            max_backup_size_bytes=backup_limit)
        return result

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

    @router.post("/stories/{story_id}/ignore", response_model=StoryDetailState)
    def ignore_story(folder: str, story_id: str, request: StoryIgnoreRequest) -> dict:
        folder = resolve_folder(folder)
        try:
            service.repo.ignore_story(
                folder, story_id, actor="web", reason=request.reason)
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
