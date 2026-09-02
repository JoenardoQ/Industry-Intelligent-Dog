"""Source-first industry research bootstrap with explicit quality gates.

The workflow never treats an LLM answer as verified truth.  It discovers a
source universe first, records a structural audit, then permits value-chain
and entity discovery only when the preceding artifact passes its gate.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from intdog_core import tracked_function
from intdog_core.models import json_text, utc_now
from .services.provider_factory import create_provider

from .knowledge_model import KnowledgeModel
from .source_discovery import (SOURCE_CATEGORIES, balance_source_origins,
                               build_discovery_task, merge_sources, seed_sources,
                               source_origin)


PRIMARY_CATEGORIES = {"official", "associations", "financials", "journals"}
ENTITY_TYPES = {"company", "research_group", "regulator", "association",
                "person", "technology", "product", "facility"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _extract_json(text: str):
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I | re.S)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", clean):
        try:
            value, _ = decoder.raw_decode(clean[match.start():])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("Agent 返回中没有可解析的 JSON")


def audit_sources(sources: dict) -> dict:
    counts, domains, invalid, primary, access_checks = {}, set(), [], 0, []
    origin_counts = {"china": 0, "foreign": 0, "unknown": 0}
    total = 0
    for category, _ in SOURCE_CATEGORIES:
        valid = 0
        for item in sources.get(category, []) or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                invalid.append(url or str(item.get("name") or "(missing url)"))
                continue
            valid += 1
            origin_counts[source_origin(item)] += 1
            domains.add(parts.netloc.lower().removeprefix("www."))
            if isinstance(item.get("access_check"), dict):
                access_checks.append(bool(item["access_check"].get("reachable")))
            if category in PRIMARY_CATEGORIES or item.get("tier") == "primary":
                primary += 1
        counts[category] = valid
        total += valid
    covered = sum(1 for key, _ in SOURCE_CATEGORIES if counts.get(key, 0) > 0)
    coverage = covered / max(1, len(SOURCE_CATEGORIES))
    checks = {
        "minimum_sources": total >= 15,
        "domain_diversity": len(domains) >= 10,
        "primary_sources": primary >= 5,
        "category_coverage": coverage >= 0.6,
        "valid_urls": not invalid,
    }
    china = origin_counts["china"]
    foreign = origin_counts["foreign"]
    foreign_per_china = foreign / china if china else 999.0
    balance_advisory = china < 8 or (foreign_per_china > 2.0 if china else True)
    if access_checks:
        required_live = min(10, max(3, (len(access_checks) + 2) // 3))
        checks["live_reachability"] = sum(access_checks) >= required_live
    return {"passed": all(checks.values()), "checks": checks, "total": total,
            "unique_domains": len(domains), "primary_count": primary,
            "category_coverage": round(coverage, 3), "counts": counts,
            "live_checked": len(access_checks),
            "live_reachable": sum(access_checks),
            "origin_counts": origin_counts,
            "foreign_per_china": round(foreign_per_china, 3),
            "balance_policy": "advisory_domestic_recall_preferred",
            "advisories": (["国内来源偏少；继续扩充官方媒体、垂直媒体和优质自媒体"]
                           if balance_advisory else []),
            "invalid_urls": invalid, "verification_scope": "structure_and_provenance",
            "note": "通过表示来源结构合格，不表示每条内容事实已经复核。"}


def _apply_access_classification(item: dict, access_check: dict) -> None:
    result = dict(access_check)
    code = result.get("status_code")
    declared_access = str(item.get("access") or "").lower()
    result["reachable"] = (
        isinstance(code, int) and 200 <= code < 400 and
        "paywall" not in declared_access)
    item["access_check"] = result
    if result["reachable"]:
        item["monitoring_status"] = "active"
        item.pop("access_note", None)
    else:
        item["monitoring_status"] = "recommended_manual"
        item["access_note"] = (
            "优质候选源当前无法稳定自动抓取；保留用于人工关注或后续接入。")


def reconcile_source_audit(store) -> dict:
    """Reclassify persisted checks and refresh the bootstrap source audit offline."""
    sources = store.get_sources()
    for category, _ in SOURCE_CATEGORIES:
        for item in sources.get(category, []) or []:
            if isinstance(item, dict) and isinstance(item.get("access_check"), dict):
                _apply_access_classification(item, item["access_check"])
    store.save_sources(sources)
    audit = audit_sources(store.get_sources())
    status = store._read_json(store.root / "bootstrap_status.json", {})
    status.setdefault("stages", {})
    stage = dict(status["stages"].get("sources") or {})
    stage.update({"state": "passed" if audit["passed"] else "failed", "audit": audit})
    status["stages"]["sources"] = stage
    if not audit["passed"]:
        status["state"] = "blocked_by_source_gate"
    status["updated_at"] = _now()
    _write(store.root / "bootstrap_status.json", status)
    return status


def check_source_accessibility(sources: dict, timeout: int = 8,
                               workers: int = 8) -> dict:
    """Live-check candidate URLs and distinguish access from mere existence."""
    import requests

    entries = []
    for category, _ in SOURCE_CATEGORIES:
        for item in sources.get(category, []) or []:
            if isinstance(item, dict) and item.get("url"):
                entries.append(item)

    def probe(item):
        url = str(item["url"])
        try:
            response = requests.head(url, allow_redirects=True, timeout=timeout,
                                     headers={"User-Agent": "IntDog/2.1 source-audit"})
            if response.status_code in {405, 501}:
                response = requests.get(url, allow_redirects=True, timeout=timeout,
                                        stream=True,
                                        headers={"User-Agent": "IntDog/2.1 source-audit"})
            code = response.status_code
            final_url = response.url
            response.close()
            return {"checked_at": _now(), "status_code": code,
                    "final_url": final_url}
        except requests.RequestException as exc:
            return {"checked_at": _now(), "reachable": False,
                    "error": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as pool:
        futures = {pool.submit(probe, item): item for item in entries}
        for future in as_completed(futures):
            item = futures[future]
            _apply_access_classification(item, future.result())
    return sources


class _FeedLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        blob = f"{values.get('rel', '')} {values.get('type', '')} {values.get('href', '')}".lower()
        if values.get("href") and "alternate" in blob and any(
                token in blob for token in ("rss", "atom", "feed")):
            self.links.append(values["href"])


def discover_rss_endpoints(sources: dict, timeout: int = 8,
                           workers: int = 8) -> dict:
    """Discover declared RSS/Atom links from monitorable source homepages."""
    import requests
    monitorable = {"blogs", "platforms", "self_media", "news", "finance"}
    targets = []
    for category, _ in SOURCE_CATEGORIES:
        if category not in monitorable:
            continue
        for item in sources.get(category, []) or []:
            if isinstance(item, dict) and item.get("url") and not (
                    item.get("rss_url") or item.get("feed_url")):
                targets.append(item)

    def inspect(item):
        try:
            response = requests.get(str(item["url"]), timeout=timeout,
                                    headers={"User-Agent": "IntDog/2.2 feed-discovery"})
            if response.status_code >= 400 or "html" not in response.headers.get(
                    "content-type", "").lower():
                return item, ""
            parser = _FeedLinkParser(); parser.feed(response.text[:1_000_000])
            if parser.links:
                return item, urljoin(response.url, parser.links[0])
            # Some Chinese publishers expose feeds without declaring <link rel=alternate>.
            # Probe common endpoints, but persist only a response that is actually XML/RSS/Atom.
            if source_origin(item) == "china":
                parts = urlsplit(response.url)
                base = f"{parts.scheme}://{parts.netloc}/"
                for suffix in ("feed/", "rss.xml", "index.rss"):
                    candidate = urljoin(base, suffix)
                    try:
                        feed = requests.get(candidate, timeout=min(timeout, 6),
                                            headers={"User-Agent": "IntDog/2.2 feed-discovery"})
                        head = feed.text[:1000].lower()
                        content_type = feed.headers.get("content-type", "").lower()
                        if feed.status_code < 400 and (
                                "rss" in content_type or "atom" in content_type or
                                "xml" in content_type and ("<rss" in head or "<feed" in head)):
                            return item, feed.url
                    except requests.RequestException:
                        continue
            return item, ""
        except (requests.RequestException, ValueError):
            return item, ""

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(inspect, item) for item in targets]
        for future in as_completed(futures):
            item, feed_url = future.result()
            if feed_url:
                item["rss_url"] = feed_url
                item["access"] = "rss"
                item["rss_discovered_at"] = _now()
    return sources


def audit_chains(chains: list[dict]) -> dict:
    valid = [c for c in chains if isinstance(c, dict) and c.get("name")]
    cited = [c for c in valid if c.get("references")]
    checks = {"minimum_stages": len(valid) >= 5,
              "all_stages_cited": len(cited) == len(valid),
              "inputs_outputs_defined": all(c.get("inputs") is not None and
                                            c.get("outputs") is not None for c in valid)}
    return {"passed": all(checks.values()), "checks": checks,
            "stage_count": len(valid), "cited_stage_count": len(cited)}


def audit_entities(entities: list[dict], chains: list[dict]) -> dict:
    chain_names = {c.get("name") for c in chains}
    valid = [e for e in entities if isinstance(e, dict) and e.get("name") and
             e.get("chain") in chain_names and e.get("references")]
    coverage = {name: sum(1 for e in valid if e.get("chain") == name) for name in chain_names}
    company_regions = {}
    for name in chain_names:
        rows = [e for e in valid if e.get("chain") == name and e.get("type") == "company"]
        company_regions[name] = {
            "china": sum(1 for e in rows if e.get("is_china") is True),
            "global": sum(1 for e in rows if e.get("is_china") is False),
        }
    checks = {"every_stage_has_entities": all(v >= 3 for v in coverage.values()),
              "every_entity_cited": len(valid) == len(entities),
              "china_global_company_coverage": all(
                  v["china"] >= 1 and v["global"] >= 1 for v in company_regions.values())}
    return {"passed": all(checks.values()), "checks": checks,
            "entity_count": len(valid), "coverage_by_stage": coverage,
            "company_regions_by_stage": company_regions}


def normalize_entities(entities: list[dict], valid_chains: set[str] | None = None) -> list[dict]:
    """Expand an entity linked to multiple stages into one row per stage."""
    normalized = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        raw = entity.get("chain")
        stages = raw if isinstance(raw, list) else [raw]
        expanded = []
        for stage in stages:
            if (isinstance(stage, str) and valid_chains and stage not in valid_chains
                    and ("；" in stage or ";" in stage)):
                expanded.extend(re.split(r"[；;]", stage))
            else:
                expanded.append(stage)
        for stage in expanded:
            if not isinstance(stage, str) or not stage.strip():
                continue
            if valid_chains and stage.strip() not in valid_chains:
                continue
            row = dict(entity)
            row["chain"] = stage.strip()
            normalized.append(row)
    return normalized


def _persist_knowledge(store, industry_en: str, chains: list[dict],
                       entities: list[dict], chain_result: dict,
                       entity_result: dict, status: dict) -> dict:
    entity_audit = audit_entities(entities, chains)
    status["stages"]["entities"] = {"state": "passed" if entity_audit["passed"] else "review",
                                           "audit": entity_audit}
    km = KnowledgeModel(store.knowledge)
    km.set_industry(store.name, industry_en, references=[])
    # A completed bootstrap replaces the previous generated graph.  Otherwise
    # stale or malformed model relationships can survive a corrected rerun.
    km.reset_generated()
    for index, chain in enumerate(chains, 1):
        km.add_chain(chain["name"], chain.get("description", ""),
                     int(chain.get("order") or index), chain.get("references", []),
                     inputs=chain.get("inputs", []), outputs=chain.get("outputs", []),
                     upstream=chain.get("upstream", []), downstream=chain.get("downstream", []),
                     technology_barriers=chain.get("technology_barriers", []),
                     geographies=chain.get("geographies", []),
                     confidence=chain.get("confidence"))
    chain_names = {chain["name"] for chain in chains}
    explicit_edges = chain_result.get("edges", []) if isinstance(chain_result, dict) else []
    explicit_pairs = set()
    for edge in explicit_edges:
        source, target = edge.get("source"), edge.get("target")
        if source not in chain_names or target not in chain_names or source == target:
            continue
        explicit_pairs.add((source, target))
        references = edge.get("references", []) or []
        km.add_chain_edge(source, target, edge.get("relation", "supplies"),
                          confidence=edge.get("confidence"),
                          status="collected" if references else "candidate",
                          effect=edge.get("effect", "uncertain"),
                          lag_days=edge.get("lag_days"), references=references)
    for chain in chains:
        for downstream in chain.get("downstream", []) or []:
            pair = (chain["name"], downstream)
            if downstream in chain_names and downstream != chain["name"] and pair not in explicit_pairs:
                km.add_chain_edge(*pair, "supplies", status="candidate")
        for upstream in chain.get("upstream", []) or []:
            pair = (upstream, chain["name"])
            if upstream in chain_names and upstream != chain["name"] and pair not in explicit_pairs:
                km.add_chain_edge(*pair, "supplies", status="candidate")
    for entity in entities:
        if not entity.get("name") or not entity.get("chain"):
            continue
        etype = entity.get("type") if entity.get("type") in ENTITY_TYPES else "company"
        km.add_entity(entity["name"], etype, entity["chain"], entity.get("name_en", ""),
                      entity.get("country", ""), entity.get("description", ""),
                      entity.get("url", ""), entity.get("references", []),
                      is_china=entity.get("is_china"), roles=entity.get("roles", []),
                      confidence=entity.get("confidence"))
    raw_dir = store.one_time / "research" / "bootstrap"
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    _write(raw_dir / f"{run_id}_chains.json", chain_result)
    persisted_entities = dict(entity_result)
    persisted_entities["entities"] = entities
    _write(raw_dir / f"{run_id}_entities.json", persisted_entities)
    status.update({"state": "ready_for_review", "updated_at": _now(),
                   "review_required": True, "artifact_status": "draft"})
    _write(store.root / "bootstrap_status.json", status)
    return status


def resume_codex_bootstrap(store, industry_en: str = "") -> dict:
    """Recover completed Codex stages after a local normalization/persistence failure."""
    run_dir = store.one_time / "research" / "bootstrap" / "codex_runs"
    chain_result = entity_result = None
    for path in sorted(run_dir.glob("last_message_*.txt"), key=lambda p: p.stat().st_mtime):
        try:
            payload = _extract_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("chains"), list):
            chain_result = payload
        if isinstance(payload, dict) and isinstance(payload.get("entities"), list):
            entity_result = payload
    if not chain_result or not entity_result:
        raise ValueError("没有找到可恢复的 Codex 产业链与实体结果")
    chains = chain_result["chains"]
    chain_audit = audit_chains(chains)
    if not chain_audit["passed"]:
        raise ValueError(f"可恢复产业链未通过质量门槛: {chain_audit['checks']}")
    entities = normalize_entities(entity_result["entities"],
                                  {chain.get("name") for chain in chains})
    source_audit = audit_sources(store.get_sources())
    status = {"industry": store.name, "mode": "codex", "updated_at": _now(),
              "stages": {"sources": {"state": "passed", "audit": source_audit},
                         "value_chain": {"state": "passed", "audit": chain_audit},
                         "entities": {"state": "running"}},
              "review_required": True}
    return _persist_knowledge(store, industry_en, chains, entities,
                              chain_result, entity_result, status)


def build_tasks(industry: str, industry_en: str = "") -> list[dict]:
    source_task = {
        "stage": "sources", "title": "01 信息源发现与核验",
        "output_file": "sources.candidate.json",
        "admission": "candidate_only",
        "allowed_statuses": ["candidate"],
        "depends_on": [],
        "prompt": build_discovery_task(industry, industry_en)["prompt"],
    }
    chain_task = {
        "stage": "value_chain", "title": "02 基于合格来源重建产业链",
        "output_file": "chains.candidate.json", "depends_on": ["sources:passed"],
        "prompt": f"""仅使用阶段 01 通过门槛的来源研究“{industry}”产业链。搜索各来源并只输出 JSON：
{{"chains":[{{"name","order","description","inputs":[],"outputs":[],"upstream":[],
"downstream":[],"technology_barriers":[],"geographies":[],"references":[{{"title","url"}}],
"confidence":0.0}}],"edges":[{{"source","target","relation","effect","lag_days",
"references":[{{"title","url"}}],"confidence":0.0}}]}}。relation 仅可为 supplies、depends_on、
enables、substitutes、competes_capacity。覆盖研发、原材料/设备、生产、集成、渠道、应用、
服务/回收等适用环节；节点引用不能当作边引用，缺少边专属来源时保留上下游候选字段但不要
伪造 edges.references。""",
    }
    entity_task = {
        "stage": "entities", "title": "03 按产业链发现实体",
        "output_file": "entities.candidate.json", "depends_on": ["value_chain:passed"],
        "prompt": f"""仅使用通过门槛的信息源和产业链，发现“{industry}”实体并只输出 JSON：
{{"entities":[{{"name","name_en","type","chain","country","is_china","description",
"url","roles":[],"references":[{{"title","url"}}],"confidence":0.0}}]}}。
type 可为 company,research_group,regulator,association,person,technology,product,facility。
每个产业链环节至少覆盖中国与非中国企业，同时纳入关键监管者、研究机构、协会与技术；
数量不足要明确 coverage_gap，禁止为了凑数虚构实体。""",
    }
    return [source_task, chain_task, entity_task]


def _persist_source_coverage(store, candidate: dict) -> dict:
    """Persist model discovery claims as plans, never as verified yield."""
    repo = store.service.repo
    cells: dict[str, str] = {}
    for item in candidate.get("coverage_ledger", []) or []:
        if not isinstance(item, dict) or not isinstance(item.get("dimensions"), dict):
            continue
        cell_id = repo.upsert_coverage_cell(
            store.folder, item["dimensions"], priority=int(item.get("priority", 60)),
            status=(item.get("status") if item.get("status") in
                    {"gap", "thin", "covered", "paused"} else "gap"),
            rationale=str(item.get("rationale") or "模型提出；尚待 URL 与发布者验证"))
        cells[json.dumps(item["dimensions"], ensure_ascii=False, sort_keys=True)] = cell_id
    recorded = 0
    for item in candidate.get("query_ledger", []) or []:
        if not isinstance(item, dict) or not str(item.get("query") or "").strip():
            continue
        dimensions = item.get("dimensions") if isinstance(item.get("dimensions"), dict) else {}
        key = json.dumps(dimensions, ensure_ascii=False, sort_keys=True)
        cell_id = cells.get(key) or repo.upsert_coverage_cell(
            store.folder, dimensions, status="gap",
            rationale="查询计划提出的覆盖单元；尚待验证")
        evidence = [{"url": url, "validation_status": "unverified_model_lead"}
                    for url in item.get("discovered_urls", []) if isinstance(url, str)]
        repo.record_coverage_attempt(
            store.folder, cell_id, query=str(item["query"]),
            rationale=str(item.get("rationale") or "模型提出；尚待验证"),
            status="planned", source_yield=0, entity_yield=0,
            evidence=evidence,
            stopping_reason=str(item.get("stopping_reason") or ""))
        recorded += 1
    return {"cells": len(cells), "planned_queries": recorded,
            "model_yield_credited": 0}


def _stage_source_payload(store, payload: dict, *, query_text: str,
                          family: str) -> dict:
    """Persist one actual provider/seed batch as candidates, never active sources."""
    repo = store.service.repo
    targets = [category for category, _ in SOURCE_CATEGORIES]
    campaign = repo.create_source_campaign(store.folder, targets, 1)
    repo.transition_source_campaign(campaign["id"], "running")
    returned = sum(len(payload.get(category, []) or []) for category in targets
                   if isinstance(payload.get(category, []) or [], list))
    query = repo.record_source_query(
        campaign["id"], round_no=1, language="multilingual", family=family,
        dimensions={"region": "china+global", "source_type": "all",
                    "subdomain": "all", "chain_stage": "all",
                    "entity_type": "publisher", "time_horizon": "current"},
        query=query_text,
        outcome={"status": "completed", "returned_count": returned,
                 "admission": "candidate_only"})
    saved: dict[str, dict] = {}
    invalid = 0
    for category in targets:
        for item in payload.get(category, []) or []:
            if not isinstance(item, dict):
                invalid += 1
                continue
            try:
                candidate = repo.upsert_source_candidate(campaign["id"], {
                    **item,
                    "category": category,
                    "status": "candidate",
                    "monitoring_status": "candidate",
                    "query_id": query["id"],
                })
            except ValueError:
                invalid += 1
                continue
            saved[candidate["id"]] = candidate
    qualified_by_category = {category: len({
        item["publisher_owner_cluster"] for item in saved.values()
        if item["category"] == category
    }) for category in targets}
    now = utc_now()
    with repo.transaction() as con:
        con.execute("""UPDATE source_campaigns SET rounds=1,updated_at=?
            WHERE id=? AND status='running'""", (now, campaign["id"]))
        con.execute("""INSERT INTO audit_log
            (occurred_at,actor,action,object_type,object_id,details_json)
            VALUES(?,'source-payload-stager','source_campaign_round',
                   'source_campaign',?,?)""",
                    (now, campaign["id"], json_text({
                        "round_no": 1,
                        "new_qualified": sum(qualified_by_category.values()),
                        "candidate_total": len(saved),
                        "qualified_by_category": qualified_by_category,
                        "query_count": 1,
                        "invalid_count": invalid,
                    })))
    return {
        "campaign_id": campaign["id"],
        "status": "running",
        "candidate_total": len(saved),
        "invalid_count": invalid,
        "qualified_by_category": qualified_by_category,
    }


def prepare_bootstrap(store, industry_en: str = "", profile: dict | None = None) -> dict:
    seed = seed_sources(store.name, industry_en, profile)
    existing = store.get_sources()
    seed_campaign = _stage_source_payload(
        store, seed, query_text="bundled reviewed seed catalog",
        family="bundled_seed_baseline")
    tasks = build_tasks(store.name, industry_en)
    task_path = store.save_task("industry_bootstrap", {
        "type": "industry_bootstrap", "execution": "strictly_sequential",
        "tasks": tasks, "quality_policy": "failed stage blocks downstream stages",
    })
    status = {"industry": store.name, "state": "waiting_for_agent",
              "mode": "task_package", "updated_at": _now(),
              "stages": {"sources": {"state": "candidate",
                                      "active_catalog_audit": audit_sources(existing),
                                      "candidate_campaign": seed_campaign},
                         "value_chain": {"state": "blocked", "requires": "sources:passed"},
                         "entities": {"state": "blocked", "requires": "value_chain:passed"}},
              "task_file": str(task_path), "review_required": True}
    _write(store.root / "bootstrap_status.json", status)
    return status


@tracked_function("refresh-sources", store_position=1)
def refresh_sources_with_agent(config: dict, store, industry_en: str = "",
                               profile: dict | None = None,
                               provider: str = "codex", progress=print) -> dict:
    """Refresh only the source universe while preserving reviewed chain/entity artifacts."""
    existing = store.get_sources()
    client = create_provider(config, provider, store.root)
    task = build_tasks(store.name, industry_en)[0]
    progress("[来源] 搜索可信信息源，并优先扩充国内官方媒体与优质自媒体…")
    candidate = _extract_json(client.complete(task["prompt"]).text)
    if not isinstance(candidate, dict):
        raise ValueError("信息源阶段必须返回 JSON 对象")
    coverage_metrics = _persist_source_coverage(store, candidate)
    candidate["industry"] = store.name
    candidate_campaign = _stage_source_payload(
        store, candidate, query_text=task["prompt"], family="provider_batch_candidate")
    candidate_dir = store.one_time / "research" / "bootstrap"
    _write(candidate_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_sources_candidate.json",
           candidate)
    status = store._read_json(store.root / "bootstrap_status.json", {})
    status.setdefault("industry", store.name)
    status.setdefault("stages", {})
    status["mode"] = provider
    status["updated_at"] = _now()
    status["review_required"] = True
    status["stages"]["sources"] = {
        "state": "candidate",
        "active_catalog_audit": audit_sources(existing),
        "candidate_campaign": candidate_campaign,
        "coverage_planning": coverage_metrics}
    status["state"] = "awaiting_source_review"
    _write(store.root / "bootstrap_status.json", status)
    progress(f"[完成] 已保存 {candidate_campaign['candidate_total']} 个待审查来源；"
             "未自动激活。")
    return status


@tracked_function("bootstrap-industry", store_position=1)
def run_bootstrap(config: dict, store, industry_en: str = "", profile: dict | None = None,
                  provider: str | None = None, progress=print) -> dict:
    status = prepare_bootstrap(store, industry_en, profile)
    status["mode"] = "codex" if provider == "codex" else "api"
    client = create_provider(config, provider, store.root)
    tasks = build_tasks(store.name, industry_en)
    progress("[1/3] 搜索并审计信息源…")
    candidate = _extract_json(client.complete(tasks[0]["prompt"]).text)
    if not isinstance(candidate, dict):
        raise ValueError("信息源阶段必须返回 JSON 对象")
    coverage_metrics = _persist_source_coverage(store, candidate)
    candidate["industry"] = store.name
    candidate_campaign = _stage_source_payload(
        store, candidate, query_text=tasks[0]["prompt"],
        family="provider_batch_candidate")
    candidate_dir = store.one_time / "research" / "bootstrap"
    _write(candidate_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_sources_candidate.json",
           candidate)
    status["stages"]["sources"] = {
        "state": "candidate", "candidate_campaign": candidate_campaign,
        "coverage_planning": coverage_metrics}
    status["state"] = "awaiting_source_review"
    status["stages"]["value_chain"] = {
        "state": "blocked", "requires": "sources:passed"}
    status["stages"]["entities"] = {
        "state": "blocked", "requires": "value_chain:passed"}
    status["updated_at"] = _now()
    _write(store.root / "bootstrap_status.json", status)
    progress(f"[暂停] 已保存 {candidate_campaign['candidate_total']} 个候选来源；"
             "完成来源审查后才能研究产业链。")
    return status
