"""Read-only data quality and freshness checks for one industry."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit

from .source_discovery import SOURCE_CATEGORIES, source_origin
from .deduplication import content_fingerprint, normalize_text
from intdog_core.source_trust import publisher_key


def audit_store(store, freshness_days: int = 3) -> dict:
    daily_root = store.periodic / "daily"
    dates = sorted((d.name for d in daily_root.iterdir() if d.is_dir()), reverse=True) \
        if daily_root.exists() else []
    items = store.list_daily_range(days=3650)
    latest = dates[0] if dates else ""
    stale_days = None
    if latest:
        try:
            stale_days = (datetime.now().date() -
                          datetime.strptime(latest, "%Y-%m-%d").date()).days
        except ValueError:
            pass
    missing = Counter()
    invalid_urls = 0
    weak_classification = 0
    publishers = Counter()
    canonical_urls = Counter()
    content_fingerprints = Counter()
    publisher_title_dates: dict[tuple[str, str], list[datetime]] = {}
    daily_categories = Counter()
    daily_origins = Counter()
    for item in items:
        for field in ("title", "url", "source", "date", "category"):
            if not item.get(field):
                missing[field] += 1
        url = item.get("url", "")
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            invalid_urls += 1
        else:
            publishers[publisher_key(item)] += 1
            canonical_urls[store._canonical_url(url)] += 1
            normalized_abstract = normalize_text(item.get("abstract") or item.get("summary"))
            if len(normalized_abstract) >= 80:
                content_fingerprints[content_fingerprint(item)] += 1
            title_key = (publisher_key(item), normalize_text(item.get("title")))
            try:
                observed = datetime.strptime(str(item.get("date") or "")[:10], "%Y-%m-%d")
            except ValueError:
                observed = None
            if title_key[1] and observed:
                publisher_title_dates.setdefault(title_key, []).append(observed)
        if (item.get("category") in {"funding", "hiring", "ceo"}
                and not item.get("classification_reason")):
            weak_classification += 1
        daily_categories[item.get("category") or item.get("_cat") or "unknown"] += 1
        daily_origins[source_origin(item)] += 1
    duplicates = sum(count - 1 for count in canonical_urls.values() if count > 1)
    duplicate_content = sum(count - 1 for count in content_fingerprints.values() if count > 1)
    duplicate_publisher_titles = 0
    for observed_dates in publisher_title_dates.values():
        ordered_dates = sorted(observed_dates)
        duplicate_publisher_titles += sum(
            (current - previous).days <= 3
            for previous, current in zip(ordered_dates, ordered_dates[1:]))
    knowledge = store.knowledge
    entities = store._read_json(knowledge / "entities.json", [])
    chains = store._read_json(knowledge / "chains.json", [])
    entity_refs = sum(bool(entity.get("references")) for entity in entities)
    chain_coverage = {}
    for chain in chains:
        name = chain.get("name", "")
        members = [entity for entity in entities if entity.get("chain") == name]
        chain_coverage[name] = {
            "entities": len(members),
            "entity_types": dict(Counter(entity.get("type", "unknown") for entity in members)),
            "countries": len({entity.get("country") for entity in members if entity.get("country")}),
            "with_references": sum(bool(entity.get("references")) for entity in members),
        }
    assigned_names = set(chain_coverage)
    unassigned = sum(not entity.get("chain") or entity.get("chain") not in assigned_names
                     for entity in entities)
    entity_types = Counter(entity.get("type", "unknown") for entity in entities)
    empty_chains = [name for name, coverage in chain_coverage.items()
                    if coverage["entities"] == 0]
    warnings = []
    if stale_days is None:
        warnings.append("没有每日数据")
    elif stale_days > freshness_days:
        warnings.append(f"数据已 {stale_days} 天未更新")
    if weak_classification:
        warnings.append(f"{weak_classification} 条分类记录缺少命中依据（可能是 v1 数据）")
    if entities and entity_refs < len(entities):
        warnings.append(f"{len(entities)-entity_refs} 个知识实体没有引用")
    if not chains:
        warnings.append("产业链知识结构为空")
    if not entities:
        warnings.append("公司/研究机构实体库为空")
    if empty_chains:
        warnings.append(f"{len(empty_chains)} 个产业链节点尚无实体")
    if entities and not entity_types.get("research_group"):
        warnings.append("尚未覆盖研究组实体")
    if unassigned:
        warnings.append(f"{unassigned} 个实体未映射到有效产业链节点")
    if len(publishers) < 3 and items:
        warnings.append("来源多样性不足（少于 3 个发布者）")
    sources = store.get_sources()
    source_items = [entry for category, _ in SOURCE_CATEGORIES
                    for entry in sources.get(category, []) or [] if isinstance(entry, dict)]
    source_statuses = Counter(str(entry.get("monitoring_status") or "active")
                              for entry in source_items)
    origin_counts = Counter(source_origin(entry) for entry in source_items)
    origin_ratio = (origin_counts["foreign"] / origin_counts["china"]
                    if origin_counts["china"] else None)
    if source_items and origin_counts["china"] < 8:
        warnings.append("国内信息源偏少；建议扩充官方媒体、垂直媒体和优质自媒体（不阻断运行）")
    reports = list(store.reports.rglob("*.md")) if store.reports.exists() else []
    period_reports = sum(1 for kind in ("weekly", "monthly", "quarterly")
                         for path in (store.periodic / kind).glob("*.md"))
    if items and daily_origins["china"] == 0:
        warnings.append("当前每日情报没有中文网站条目（来源池合格不等于抓取结果平衡）")
    elif items and daily_origins["china"]:
        daily_ratio = daily_origins["foreign"] / daily_origins["china"]
        if daily_ratio > 2:
            warnings.append(f"每日情报国内召回偏低（中文:外文=1:{daily_ratio:.2f}，不阻断运行）")
    if items and daily_categories:
        dominant, dominant_count = daily_categories.most_common(1)[0]
        if dominant_count / len(items) > 0.7:
            warnings.append(f"每日情报被 {dominant} 类别主导（{dominant_count}/{len(items)}）")
    if not reports:
        warnings.append("尚无行业报告 Markdown 成品")
    if not period_reports:
        warnings.append("尚无周/月/季 Markdown 成品")
    return {
        "industry": store.name, "folder": store.folder,
        "latest_date": latest, "stale_days": stale_days,
        "fresh": stale_days is not None and stale_days <= freshness_days,
        "items": len(items), "publishers": len(publishers),
        "top_publishers": publishers.most_common(10),
        "missing_required_fields": dict(missing),
        "invalid_urls": invalid_urls, "duplicate_urls": duplicates,
        "duplicate_content": duplicate_content,
        "duplicate_publisher_titles": duplicate_publisher_titles,
        "weak_classification": weak_classification,
        "knowledge": {"chains": len(chains), "entities": len(entities),
                      "entities_with_references": entity_refs,
                      "entity_types": dict(entity_types),
                      "unassigned_entities": unassigned},
        "coverage_matrix": {"by_chain": chain_coverage,
                            "empty_chains": empty_chains,
                            "source_categories": {
                                category: len(sources.get(category, []) or [])
                                for category, _ in SOURCE_CATEGORIES}},
        "structured_core": store.service.repo.knowledge_stats(store.folder),
        "sources": {"total": len(source_items), "origin_counts": dict(origin_counts),
                    "monitoring_statuses": dict(source_statuses),
                    "foreign_per_china": round(origin_ratio, 3) if origin_ratio else None},
        "reports": {"industry_markdown": len(reports),
                    "periodic_markdown": period_reports},
        "daily_distribution": {"categories": dict(daily_categories),
                               "origins": dict(daily_origins)},
        "warnings": warnings,
    }
