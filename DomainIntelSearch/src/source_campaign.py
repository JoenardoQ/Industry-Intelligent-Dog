"""Deterministic multi-round source discovery state machine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol

from intdog_core.models import canonical_url, stable_id

from .source_discovery import SOURCE_CATEGORIES


SELECTION_TARGET = 10
CANDIDATE_POOL_TARGET = 11

CATEGORY_QUERY_TERMS = {
    "official": ("政府 监管 统计 官方发布", "government regulator statistics official release"),
    "associations": ("行业协会 标准组织", "industry association standards organization"),
    "blogs": ("权威技术博客 专家机构", "authoritative technical expert blog"),
    "platforms": ("专业平台 开发者社区", "professional platform developer community"),
    "self_media": ("行业专家 自媒体 领导者", "industry expert creator leadership"),
    "news": ("权威垂直媒体 新闻机构", "authoritative trade press news agency"),
    "journals": ("顶级期刊 会议 同行评审", "leading journal conference peer reviewed"),
    "financials": ("公司公告 财报 交易所披露", "company filing financial report exchange disclosure"),
    "finance": ("金融数据 市场研究", "financial data market research"),
}

class SearchAdapter(Protocol):
    def search(self, query: str, *, language: str, family: str,
               dimensions: dict, limit: int): ...


class ProviderSearchAdapter:
    """Translate one logical source query into candidate-only structured output."""

    def __init__(self, client):
        self.client = client

    def search(self, query: str, *, language: str, family: str,
               dimensions: dict, limit: int):
        from .research_bootstrap import _extract_json

        prompt = f"""Search the web for this source-discovery query and return JSON only.
Query: {query}
Language: {language}; family: {family}
Dimensions: {json.dumps(dimensions, ensure_ascii=False, sort_keys=True)}
Return at most {limit} actually found candidates. Never mark a candidate active.
Schema: {{"candidates":[{{"name":"publisher","url":"https://...",
"category":"{dimensions.get('source_type', '')}","publisher_country":"...",
"selection_reason":"why this fills the exact coverage cell"}}]}}
Do not invent URLs. A candidate remains unqualified until repository review gates pass."""
        payload = _extract_json(self.client.complete(prompt).text)
        return payload if isinstance(payload, dict) else {"candidates": []}


@dataclass(frozen=True)
class CampaignOutcome:
    status: Literal["paused", "converged", "running"]
    qualified_by_category: dict[str, int]
    candidate_total: int
    stopping_reason: str


def plan_query_families(industry: dict, gaps: list[dict]) -> list[dict]:
    if not isinstance(industry, dict):
        raise ValueError("industry must be an object")
    if not isinstance(gaps, list):
        raise ValueError("gaps must be a list")
    known_categories = [category for category, _ in SOURCE_CATEGORIES]
    raw_targets = industry.get("targets")
    targets = ([str(value).strip().casefold() for value in raw_targets]
               if isinstance(raw_targets, list) else known_categories)
    targets = [category for category in known_categories if category in set(targets)]
    if not targets:
        raise ValueError("source campaign requires at least one known category")

    gaps_by_category: dict[str, list[dict]] = {category: [] for category in targets}
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        dimensions = gap.get("dimensions") if isinstance(gap.get("dimensions"), dict) else {}
        category = str(gap.get("category") or dimensions.get("source_type") or "").casefold()
        if category in targets:
            gaps_by_category[category].append(gap)

    family = "gap_expansion" if gaps else "authoritative_baseline"
    name_zh = str(industry.get("name") or industry.get("folder") or "目标行业").strip()
    name_en = str(industry.get("name_en") or industry.get("folder") or name_zh).strip()
    plan: list[dict] = []
    for category in targets:
        category_gaps = gaps_by_category[category] or [{}]
        for gap in category_gaps:
            gap_dimensions = (gap.get("dimensions")
                              if isinstance(gap.get("dimensions"), dict) else {})
            zh_terms, en_terms = CATEGORY_QUERY_TERMS[category]
            gap_zh = " 补足覆盖缺口" if family == "gap_expansion" else " 权威一手基线"
            gap_en = " coverage gap expansion" if family == "gap_expansion" else " authoritative primary baseline"
            for language, region, industry_name, terms, suffix in (
                    ("zh", "china", name_zh, zh_terms, gap_zh),
                    ("en", "global", name_en, en_terms, gap_en)):
                dimensions = {
                    "language": language,
                    "region": str(gap_dimensions.get("region") or region),
                    "subdomain": str(gap_dimensions.get("subdomain") or "all"),
                    "chain_stage": str(gap_dimensions.get("chain_stage") or "all"),
                    "entity_type": str(gap_dimensions.get("entity_type") or "publisher"),
                    "source_type": category,
                    "time_horizon": str(gap_dimensions.get("time_horizon") or "current"),
                }
                detail = " ".join(value for key, value in dimensions.items()
                                  if key in {"subdomain", "chain_stage"} and value != "all")
                query = " ".join(
                    f"{industry_name} {detail} {terms}{suffix}".split())
                plan.append({
                    "language": language,
                    "family": family,
                    "dimensions": dimensions,
                    "query": query,
                    "selection_target": SELECTION_TARGET,
                    "candidate_pool_target": CANDIDATE_POOL_TARGET,
                })
    return plan


def _campaign_context(repo, campaign_id: str) -> dict:
    with repo.connection() as con:
        row = con.execute("""SELECT sc.*,i.folder,i.name
            FROM source_campaigns sc JOIN industries i ON i.id=sc.industry_id
            WHERE sc.id=?""", (campaign_id,)).fetchone()
    if not row:
        raise FileNotFoundError(f"source campaign not found: {campaign_id}")
    item = dict(row)
    item["targets"] = json.loads(item.pop("targets_json"))
    return item


def _candidate_counts(candidates: list[dict], targets: list[str]) -> dict[str, int]:
    publishers = {category: set() for category in targets}
    for item in candidates:
        category = str(item.get("category") or "")
        if category in publishers and item.get("status") == "active":
            publishers[category].add(str(item.get("publisher_owner_cluster") or
                                         item.get("canonical_url") or item.get("id")))
    return {category: len(values) for category, values in publishers.items()}


def _pause_reason(value: object) -> str | None:
    if isinstance(value, TimeoutError):
        return "timeout"
    status_code = (value.get("status_code") if isinstance(value, dict)
                   else getattr(value, "status_code", None))
    if status_code in {403, 429}:
        return f"http_{status_code}"
    status = str(value.get("status") if isinstance(value, dict)
                 else getattr(value, "status", "")).strip().casefold()
    aliases = {
        "timeout": "timeout",
        "timed_out": "timeout",
        "forbidden": "http_403",
        "rate_limited": "http_429",
        "rate-limit": "http_429",
        "budget_exhausted": "insufficient_budget",
        "insufficient_budget": "insufficient_budget",
        "login_required": "login_wall",
        "paywalled": "paywall",
        "provider_unavailable": "provider_unavailable",
    }
    return aliases.get(status)


def _result_candidates(value: object) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        items = value.get("candidates", [])
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    return []


def run_campaign_round(repo, campaign_id: str, *, search: SearchAdapter) -> CampaignOutcome:
    campaign = _campaign_context(repo, campaign_id)
    if campaign["status"] in {"converged", "failed"}:
        raise ValueError(f"cannot run terminal source campaign: {campaign['status']}")
    if campaign["status"] in {"planned", "paused"}:
        repo.transition_source_campaign(campaign_id, "running")
        campaign = _campaign_context(repo, campaign_id)

    targets = [category for category, _ in SOURCE_CATEGORIES
               if category in set(campaign["targets"])]
    current_candidates = repo.list_source_candidates(campaign_id)
    current_counts = _candidate_counts(current_candidates, targets)
    round_no = int(campaign["rounds"]) + 1
    coverage_gaps = []
    if round_no > 1:
        coverage_gaps = [cell for cell in repo.list_coverage(campaign["folder"])
                         if cell["status"] in {"gap", "thin"} and
                         cell["dimensions"].get("source_type") in targets]
    gaps = [] if round_no == 1 else (coverage_gaps or [{
        "category": category,
        "missing": max(0, CANDIDATE_POOL_TARGET - current_counts[category]),
        "dimensions": {"source_type": category},
    } for category in targets])
    plan = plan_query_families({
        "name": campaign["name"],
        "name_en": campaign["folder"],
        "folder": campaign["folder"],
        "targets": targets,
    }, gaps)
    logical_ids = {
        stable_id("sqy", campaign_id, round_no, spec["language"].casefold(),
                  spec["family"].casefold(),
                  json.dumps(spec["dimensions"], ensure_ascii=False,
                             separators=(",", ":"), sort_keys=True),
                  spec["query"].casefold())
        for spec in plan
    }
    with repo.connection() as con:
        used_ids = {row[0] for row in con.execute(
            "SELECT id FROM source_queries WHERE campaign_id=?", (campaign_id,))}
    if len(used_ids | logical_ids) > int(campaign["budget"]):
        reason = "insufficient_budget"
        repo.transition_source_campaign(campaign_id, "paused", reason=reason)
        return CampaignOutcome("paused", current_counts, len(current_candidates), reason)

    previous_rounds = repo.list_source_campaign_rounds(campaign_id)
    previous_counts = (previous_rounds[-1]["outcome"].get("qualified_by_category", {})
                       if previous_rounds else {})
    new_qualified = sum(max(0, current_counts[category] - int(
        previous_counts.get(category, 0))) for category in targets)
    round_state = repo.begin_source_campaign_round(
        campaign_id, plan=plan,
        frontier=[dict(spec["dimensions"]) for spec in plan])
    round_id, lease_token = round_state["id"], round_state["lease_token"]
    repo.append_source_campaign_log(
        round_id, lease_token,
        f"round {round_no}: {len(plan)} logical queries; {len(logical_ids-used_ids)} new budget units")
    for spec in plan:
        query_id = stable_id(
            "sqy", campaign_id, round_no, spec["language"].casefold(),
            spec["family"].casefold(),
            json.dumps(spec["dimensions"], ensure_ascii=False,
                       separators=(",", ":"), sort_keys=True),
            spec["query"].casefold())
        if query_id in used_ids:
            with repo.connection() as con:
                prior = con.execute("SELECT outcome_json FROM source_queries WHERE id=?",
                                    (query_id,)).fetchone()
            if prior and json.loads(prior["outcome_json"]).get("status") == "completed":
                continue
        try:
            result = search.search(
                spec["query"], language=spec["language"], family=spec["family"],
                dimensions=dict(spec["dimensions"]),
                limit=int(spec["candidate_pool_target"]))
        except Exception as exc:
            reason = _pause_reason(exc) or f"provider_unavailable:{type(exc).__name__}"
            repo.record_source_query(
                campaign_id, round_no=round_no, language=spec["language"],
                family=spec["family"], dimensions=spec["dimensions"],
                query=spec["query"], outcome={"status": "paused", "reason": reason})
            repo.append_source_campaign_log(
                round_id, lease_token, f"paused: {reason}", level="warning")
            repo.pause_source_campaign_round(round_id, lease_token, reason)
            candidates = repo.list_source_candidates(campaign_id)
            return CampaignOutcome(
                "paused", _candidate_counts(candidates, targets), len(candidates), reason)

        pause_reason = _pause_reason(result)
        if pause_reason:
            repo.record_source_query(
                campaign_id, round_no=round_no, language=spec["language"],
                family=spec["family"], dimensions=spec["dimensions"],
                query=spec["query"], outcome={"status": "paused", "reason": pause_reason})
            repo.append_source_campaign_log(
                round_id, lease_token, f"paused: {pause_reason}", level="warning")
            repo.pause_source_campaign_round(round_id, lease_token, pause_reason)
            candidates = repo.list_source_candidates(campaign_id)
            return CampaignOutcome(
                "paused", _candidate_counts(candidates, targets), len(candidates),
                pause_reason)

        raw_candidates = _result_candidates(result)
        valid: list[dict] = []
        seen_urls: set[str] = set()
        for item in raw_candidates:
            url = canonical_url(item.get("url", ""))
            category = str(item.get("category") or spec["dimensions"]["source_type"]).casefold()
            if (not url or url in seen_urls or
                    category != spec["dimensions"]["source_type"]):
                continue
            seen_urls.add(url)
            valid.append({**item, "url": url, "category": category,
                          "status": "candidate", "monitoring_status": "candidate"})
        query_record = repo.record_source_query(
            campaign_id, round_no=round_no, language=spec["language"],
            family=spec["family"], dimensions=spec["dimensions"],
            query=spec["query"], outcome={
                "status": "completed",
                "returned_count": len(raw_candidates),
                "candidate_count": len(valid),
                "invalid_or_duplicate_count": len(raw_candidates) - len(valid),
            })
        for item in valid:
            saved = repo.upsert_source_candidate(
                campaign_id, {**item, "query_id": query_record["id"]})
        repo.append_source_campaign_log(
            round_id, lease_token,
            f"{spec['language']} {spec['dimensions']['source_type']}: {len(valid)} candidates persisted")

    candidates = repo.list_source_candidates(campaign_id)
    qualified_by_category = _candidate_counts(candidates, targets)
    round_outcome = {
        "round_no": round_no,
        "new_qualified": new_qualified,
        "coverage_gain": new_qualified,
        "candidate_total": len(candidates),
        "qualified_by_category": qualified_by_category,
        "query_count": len(plan),
    }
    repo.finish_source_campaign_round(round_id, lease_token, round_outcome)
    recent_rounds = [item["outcome"] for item in
                     repo.list_source_campaign_rounds(campaign_id)[-2:]]
    if (len(recent_rounds) == 2 and
            all(int(item.get("new_qualified", -1)) == 0 for item in recent_rounds)):
        reason = "two_consecutive_zero_yield_rounds"
        repo.transition_source_campaign(campaign_id, "converged", reason=reason)
        return CampaignOutcome(
            "converged", qualified_by_category, len(candidates), reason)

    shortages = {category: CANDIDATE_POOL_TARGET - count
                 for category, count in qualified_by_category.items()
                 if count < CANDIDATE_POOL_TARGET}
    reason = ("candidate_pool_ready_for_selection" if not shortages
              else "candidate_pool_below_selection_target")
    return CampaignOutcome("running", qualified_by_category, len(candidates), reason)
