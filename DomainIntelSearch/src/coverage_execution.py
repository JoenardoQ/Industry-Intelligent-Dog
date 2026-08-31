"""Budgeted, evidence-admitting execution for open-world coverage plans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

import requests

from intdog_core.models import canonical_url
from .research_bootstrap import _extract_json
from .services.provider_factory import create_provider
from .source_discovery import SOURCE_CATEGORIES


CATEGORIES = {key for key, _ in SOURCE_CATEGORIES}
ENTITY_TYPES = {"company", "research_group", "regulator", "association",
                "person", "technology", "product", "facility"}


@dataclass(frozen=True)
class Probe:
    reachable: bool
    final_url: str
    status_code: int | None
    reason: str = ""


def probe_url(url: str, timeout: int = 10) -> Probe:
    """Validate a candidate URL without interpreting an error page as evidence."""
    try:
        response = requests.head(
            url, allow_redirects=True, timeout=timeout,
            headers={"User-Agent": "IntDog/4.0 coverage-validator"})
        if response.status_code in {405, 501}:
            response.close()
            response = requests.get(
                url, allow_redirects=True, timeout=timeout, stream=True,
                headers={"User-Agent": "IntDog/4.0 coverage-validator"})
        status, final_url = response.status_code, canonical_url(response.url)
        response.close()
        reachable = 200 <= status < 400
        return Probe(reachable, final_url or canonical_url(url), status,
                     "" if reachable else f"HTTP {status}")
    except requests.RequestException as exc:
        return Probe(False, canonical_url(url), None, type(exc).__name__)


def _query(cell: dict) -> str:
    dimensions = cell["dimensions"]
    subject = " ".join(str(dimensions.get(key) or "") for key in (
        "subdomain", "chain_stage", "entity_type", "event_type", "time_horizon"))
    authority = ("中国 原生站点 官方 监管 标准 企业公告" if
                 dimensions.get("region") == "china" else
                 "official regulator standards filing peer reviewed")
    return " ".join(f"{subject} {dimensions.get('source_type', '')} {authority}".split())


def _prompt(cells: list[dict], max_candidates: int) -> str:
    compact = [{"cell_id": item["id"], "dimensions": item["dimensions"],
                "query": _query(item)} for item in cells]
    return f"""为以下行业覆盖缺口执行联网搜索。只返回 JSON 对象，不要 Markdown。
每个候选必须是你实际搜索到的原始 URL；不要猜 URL。优先一手、官方、监管、标准、公司披露、
同行评审和中国发布者原生站点。转载或社交内容只能作为线索。

覆盖单元：{json.dumps(compact, ensure_ascii=False)}

最多返回 {max_candidates} 个候选：
{{"candidates":[{{"cell_id":"...","name":"发布者/实体名称","url":"https://...",
"category":"official|associations|blogs|platforms|self_media|news|journals|financials|finance",
"publisher_country":"...","note":"为何补足该单元","entity":{{"name":"可选实体",
"type":"company|research_group|regulator|association|person|technology|product|facility",
"country":"...","chain":"..."}}}}],"stopping_reason":"本轮停止原因"}}
"""


def execute_coverage(config: dict, store, *, provider: str = "codex", budget: int = 12,
                     provider_client=None, probe=probe_url) -> dict:
    """Search, validate and admit canonical sources/entities; return measured yield."""
    budget = max(1, min(50, int(budget)))
    repo = store.service.repo
    cells = [cell for cell in repo.list_coverage(store.folder)
             if cell["status"] in {"gap", "thin"}][:budget]
    if not cells:
        return {"status": "stopped", "cells": 0, "source_yield": 0,
                "entity_yield": 0, "rejected": 0,
                "stopping_reason": "当前没有 gap/thin 覆盖单元"}
    client = provider_client or create_provider(config, provider, store.root)
    payload = _extract_json(client.complete(_prompt(cells, budget * 3)).text)
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    by_cell = {cell["id"]: cell for cell in cells}
    existing_sources = {canonical_url(item.get("url", ""))
                        for item in repo.list_sources(store.folder)}
    existing_entities = {(str(item.get("type") or "company"),
                          str(item.get("name") or "").casefold(),
                          str(item.get("country") or "").casefold())
                         for item in repo.list_compat_entities(store.folder)}
    grouped = {cell_id: [] for cell_id in by_cell}
    for candidate in candidates[:budget * 3]:
        if isinstance(candidate, dict) and candidate.get("cell_id") in grouped:
            grouped[candidate["cell_id"]].append(candidate)

    total_sources = total_entities = total_rejected = 0
    for cell_id, cell in by_cell.items():
        query = _query(cell)
        evidence, source_yield, entity_yield = [], 0, 0
        repo.record_coverage_attempt(
            store.folder, cell_id, query=query, rationale="服务器正在验证搜索候选",
            status="running")
        for candidate in grouped[cell_id]:
            raw_url = canonical_url(candidate.get("url", ""))
            category = str(candidate.get("category") or "").strip()
            if not raw_url or urlsplit(raw_url).scheme not in {"http", "https"}:
                evidence.append({"url": raw_url, "status": "rejected",
                                 "reason": "invalid_url"}); total_rejected += 1
                continue
            checked = probe(raw_url)
            if not checked.reachable:
                evidence.append({"url": raw_url, "status": "rejected",
                                 "reason": checked.reason,
                                 "status_code": checked.status_code})
                total_rejected += 1; continue
            if category not in CATEGORIES:
                evidence.append({"url": checked.final_url, "status": "rejected",
                                 "reason": "invalid_category"})
                total_rejected += 1; continue
            final_url = canonical_url(checked.final_url)
            if final_url not in existing_sources:
                created = store.service.add_source(store.folder, category, {
                    "name": str(candidate.get("name") or urlsplit(final_url).netloc),
                    "url": final_url, "note": str(candidate.get("note") or ""),
                    "publisher_country": str(candidate.get("publisher_country") or ""),
                    "tier": "candidate_validated_url", "monitoring_status": "active",
                    "discovery_provenance": {"cell_id": cell_id, "query": query,
                                             "provider": provider,
                                             "validated_at": datetime.now().isoformat()},
                })
                if created:
                    source_yield += 1; total_sources += 1; existing_sources.add(final_url)
            entity = candidate.get("entity") or {}
            if isinstance(entity, dict) and entity.get("name") and entity.get("type") in ENTITY_TYPES:
                key = (str(entity["type"]), str(entity["name"]).casefold(),
                       str(entity.get("country") or "").casefold())
                if key not in existing_entities:
                    store.service.repo.upsert_entity(store.folder, {
                        **entity, "status": "candidate", "confidence": 0.55,
                        "references": [{"url": final_url, "title": candidate.get("name", "")}],
                        "discovery_provenance": {"cell_id": cell_id, "query": query}},
                        chain_name=str(entity.get("chain") or
                                       cell["dimensions"].get("chain_stage") or ""))
                    entity_yield += 1; total_entities += 1; existing_entities.add(key)
            evidence.append({"url": final_url, "status": "validated",
                             "status_code": checked.status_code,
                             "publisher": candidate.get("name", "")})
        reason = str(payload.get("stopping_reason") or "候选已验证")
        repo.record_coverage_attempt(
            store.folder, cell_id, query=query, rationale="搜索候选已经服务器验证",
            status="completed", source_yield=source_yield, entity_yield=entity_yield,
            evidence=evidence, stopping_reason=reason)
    store.service.reconcile_compat([store.folder])
    return {"status": "completed", "cells": len(cells),
            "source_yield": total_sources, "entity_yield": total_entities,
            "rejected": total_rejected,
            "stopping_reason": str(payload.get("stopping_reason") or "候选已验证")}
