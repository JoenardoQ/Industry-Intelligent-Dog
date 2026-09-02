"""Budgeted, evidence-admitting execution for open-world coverage plans."""

from __future__ import annotations

import json
from time import monotonic
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests

from intdog_core.models import canonical_url, json_text, utc_now
from .agent_evidence import _peer_address, _public_addresses
from .research_bootstrap import _extract_json
from .services.provider_factory import create_provider
from .source_discovery import SOURCE_CATEGORIES


CATEGORIES = {key for key, _ in SOURCE_CATEGORIES}
ENTITY_TYPES = {
    "company", "research_group", "government_institution", "association",
    "investment_institution", "person", "product", "technology", "standard",
    "policy",
}


@dataclass(frozen=True)
class Probe:
    reachable: bool
    final_url: str
    status_code: int | None
    reason: str = ""


def probe_url(url: str, timeout: int = 10) -> Probe:
    """Probe a URL with fail-closed DNS, peer-IP and per-hop redirect checks."""
    current = canonical_url(url)
    if not current:
        return Probe(False, "", None, "blocked_invalid_http_url")
    deadline = monotonic() + max(1, int(timeout))
    session = requests.Session()
    session.trust_env = False
    try:
        for redirect_no in range(6):
            remaining = deadline - monotonic()
            if remaining <= 0:
                return Probe(False, current, None, "deadline_exceeded")
            try:
                resolved = _public_addresses(current)
            except ValueError as exc:
                return Probe(False, current, None, str(exc))
            response = session.request(
                "HEAD", current, allow_redirects=False, timeout=min(remaining, 5),
                stream=True, headers={"User-Agent": "IntDog/4.0 coverage-validator"})
            if response.status_code in {405, 501}:
                response.close()
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return Probe(False, current, None, "deadline_exceeded")
                response = session.request(
                    "GET", current, allow_redirects=False,
                    timeout=min(remaining, 5), stream=True,
                    headers={"User-Agent": "IntDog/4.0 coverage-validator"})
            peer = _peer_address(response)
            if not peer or peer not in resolved:
                status = response.status_code
                response.close()
                return Probe(False, current, status, "blocked_peer_address_mismatch")
            status = response.status_code
            response_url = canonical_url(response.url) or current
            location = response.headers.get("location", "")
            response.close()
            if status in {301, 302, 303, 307, 308} and location:
                if redirect_no >= 5:
                    return Probe(False, response_url, status, "too_many_redirects")
                current = canonical_url(urljoin(response_url, location))
                if not current:
                    return Probe(False, response_url, status,
                                 "blocked_invalid_redirect_url")
                continue
            reachable = 200 <= status < 400
            return Probe(reachable, response_url, status,
                         "" if reachable else f"HTTP {status}")
        return Probe(False, current, None, "too_many_redirects")
    except requests.RequestException as exc:
        return Probe(False, current, None, type(exc).__name__)
    finally:
        session.close()


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
"type":"company|research_group|government_institution|association|investment_institution|person|product|technology|standard|policy",
"country":"...","chain":"..."}}}}],"stopping_reason":"本轮停止原因"}}
"""


def execute_coverage(config: dict, store, *, provider: str | None = None, budget: int = 12,
                     provider_client=None, probe=probe_url) -> dict:
    """Search and persist reviewable candidates without activating sources/entities."""
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
    grouped = {cell_id: [] for cell_id in by_cell}
    for candidate in candidates[:budget * 3]:
        if isinstance(candidate, dict) and candidate.get("cell_id") in grouped:
            grouped[candidate["cell_id"]].append(candidate)

    target_categories = sorted({
        str(candidate.get("category") or "").strip()
        for candidate in candidates if isinstance(candidate, dict)
        and str(candidate.get("category") or "").strip() in CATEGORIES
    } | {
        str(cell["dimensions"].get("source_type") or "").strip()
        for cell in cells
        if str(cell["dimensions"].get("source_type") or "").strip() in CATEGORIES
    })
    campaign = repo.create_source_campaign(
        store.folder, target_categories or ["official"], max(budget, len(cells)))
    repo.transition_source_campaign(campaign["id"], "running")

    total_rejected = 0
    candidate_ids: set[str] = set()
    for cell_id, cell in by_cell.items():
        query = _query(cell)
        evidence = []
        repo.record_coverage_attempt(
            store.folder, cell_id, query=query, rationale="服务器正在验证搜索候选",
            status="running")
        language = "zh" if cell["dimensions"].get("region") == "china" else "en"
        query_record = repo.record_source_query(
            campaign["id"], round_no=1, language=language,
            family="gap_expansion", dimensions=cell["dimensions"], query=query,
            outcome={"status": "completed", "returned_count": len(grouped[cell_id])})
        for candidate in grouped[cell_id]:
            raw_url = canonical_url(candidate.get("url", ""))
            category = str(candidate.get("category") or "").strip()
            if not raw_url or urlsplit(raw_url).scheme not in {"http", "https"}:
                evidence.append({"url": raw_url, "status": "rejected",
                                 "reason": "invalid_url"}); total_rejected += 1
                continue
            checked = probe(raw_url)
            if category not in CATEGORIES:
                evidence.append({"url": checked.final_url, "status": "rejected",
                                 "reason": "invalid_category"})
                total_rejected += 1; continue
            final_url = canonical_url(checked.final_url) or raw_url
            saved = repo.upsert_source_candidate(campaign["id"], {
                **candidate,
                "name": str(candidate.get("name") or urlsplit(final_url).netloc),
                "url": final_url,
                "category": category,
                "status": "candidate",
                "monitoring_status": "candidate",
                "score": 0.5 if checked.reachable else 0.25,
                "selection_reason": str(candidate.get("note") or
                                        "coverage search candidate; review required"),
                "query_id": query_record["id"],
                "access_check": {
                    "reachable": checked.reachable,
                    "status_code": checked.status_code,
                    "reason": checked.reason,
                },
                "discovery_provenance": {"cell_id": cell_id, "query": query,
                                         "provider": provider},
            })
            candidate_ids.add(saved["id"])
            evidence.append({"url": final_url,
                             "status": ("candidate_reachable" if checked.reachable
                                        else "candidate_unreachable"),
                             "status_code": checked.status_code,
                             "reason": checked.reason,
                             "publisher": candidate.get("name", "")})
        reason = str(payload.get("stopping_reason") or "候选已验证")
        repo.record_coverage_attempt(
            store.folder, cell_id, query=query, rationale="搜索候选已经服务器验证",
            status="completed", source_yield=0, entity_yield=0,
            evidence=evidence, stopping_reason=reason)
    now = utc_now()
    with repo.transaction() as con:
        con.execute("""UPDATE source_campaigns SET rounds=1,updated_at=?
            WHERE id=? AND status='running'""", (now, campaign["id"]))
        con.execute("""INSERT INTO audit_log
            (occurred_at,actor,action,object_type,object_id,details_json)
            VALUES(?,'coverage-executor','source_campaign_round','source_campaign',?,?)""",
                    (now, campaign["id"], json_text({
                        "round_no": 1,
                        "new_qualified": len(candidate_ids),
                        "candidate_total": len(candidate_ids),
                        "query_count": len(cells),
                    })))
    return {"status": "completed", "cells": len(cells),
            "campaign_id": campaign["id"], "candidate_yield": len(candidate_ids),
            "source_yield": 0, "entity_yield": 0,
            "rejected": total_rejected,
            "stopping_reason": str(payload.get("stopping_reason") or "候选已验证")}


def execute_persisted_coverage_round(config: dict, store, round_id: str, *,
                                     provider: str | None = None,
                                     provider_client=None) -> dict:
    """Execute and resume a server-persisted entity/relation frontier."""
    repo = store.service.repo
    round_state = repo.start_coverage_round(store.folder, round_id)
    token = round_state["lease_token"]
    rounds = repo.list_coverage_rounds(store.folder)
    current = next(item for item in rounds if item["id"] == round_id)
    repo.append_coverage_round_log(
        round_id, token,
        f"round {current['round_no']}: {len(current['queries'])} persisted queries")
    entity_ids: set[str] = set()
    relation_ids: set[str] = set()
    try:
        client = provider_client or create_provider(config, provider, store.root)
        for query in current["queries"]:
            if query["status"] == "completed":
                continue
            kind = query["kind"]
            schema = ({"name": "entity name", "type": "company",
                       "country": "...", "chain": "...", "aliases": []}
                      if kind == "entity" else
                      {"source": "upstream node", "target": "downstream node",
                       "relation": "supplies", "document_id": None,
                       "assertion_id": None, "evidence_url": "https://..."})
            prompt = f"""Execute this persisted industry coverage query. Return JSON only.
Query: {query['query']}
Dimensions: {json.dumps(query['dimensions'], ensure_ascii=False, sort_keys=True)}
Candidate kind: {kind}
Return only identities/relationships actually found. All output remains candidate-only.
Schema: {{"candidates":[{json.dumps(schema, ensure_ascii=False)}]}}
Never claim accepted status and never invent a URL, document id, or assertion id."""
            repo.record_coverage_round_query(
                round_id, token, query["id"], status="running", outcome={})
            payload = _extract_json(client.complete(prompt).text)
            candidates = (payload.get("candidates", [])
                          if isinstance(payload, dict) else [])
            saved = 0
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                try:
                    row = repo.upsert_coverage_candidate(
                        store.folder, round_id, query["id"], query["cell_id"],
                        kind=kind, payload=candidate)
                except ValueError:
                    continue
                (entity_ids if kind == "entity" else relation_ids).add(row["id"])
                saved += 1
            repo.record_coverage_round_query(
                round_id, token, query["id"], status="completed",
                outcome={"returned_count": len(candidates), "candidate_count": saved})
            repo.append_coverage_round_log(
                round_id, token, f"{kind} {query['cell_id']}: {saved} candidates")
    except Exception as exc:
        reason = f"provider_unavailable:{type(exc).__name__}"
        repo.append_coverage_round_log(round_id, token, reason, level="warning")
        return repo.finish_coverage_round(
            round_id, token, {"entities": len(entity_ids),
                              "relationships": len(relation_ids),
                              "qualified_gain": 0},
            status="paused", stopping_reason=reason)

    pending = len(entity_ids) + len(relation_ids)
    prior = [item for item in rounds if item["id"] != round_id]
    previous_zero = bool(prior and
                         int(prior[0]["outcome"].get("qualified_gain", -1)) == 0)
    converged = pending == 0 and previous_zero
    outcome = {
        "entities": len(entity_ids), "relationships": len(relation_ids),
        "coverage_units": len({query["cell_id"] for query in current["queries"]}),
        "qualified_gain": 0, "pending_review": pending,
    }
    status = "converged" if converged else "completed"
    reason = ("two_consecutive_zero_qualified_gain_rounds" if converged
              else "candidate_review_required" if pending
              else "one_zero_qualified_gain_round")
    return repo.finish_coverage_round(
        round_id, token, outcome, status=status, stopping_reason=reason)
