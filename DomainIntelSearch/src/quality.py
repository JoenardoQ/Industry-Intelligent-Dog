"""Read-only data quality and freshness checks for one industry."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit


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
    for item in items:
        for field in ("title", "url", "source", "date", "category"):
            if not item.get(field):
                missing[field] += 1
        url = item.get("url", "")
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            invalid_urls += 1
        else:
            publishers[parts.netloc.lower().removeprefix("www.")] += 1
            canonical_urls[store._canonical_url(url)] += 1
        if (item.get("category") in {"funding", "hiring", "ceo"}
                and not item.get("classification_reason")):
            weak_classification += 1
    duplicates = sum(count - 1 for count in canonical_urls.values() if count > 1)
    knowledge = store.knowledge
    entities = store._read_json(knowledge / "entities.json", [])
    chains = store._read_json(knowledge / "chains.json", [])
    entity_refs = sum(bool(entity.get("references")) for entity in entities)
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
    if len(publishers) < 3 and items:
        warnings.append("来源多样性不足（少于 3 个发布者）")
    return {
        "industry": store.name, "folder": store.folder,
        "latest_date": latest, "stale_days": stale_days,
        "fresh": stale_days is not None and stale_days <= freshness_days,
        "items": len(items), "publishers": len(publishers),
        "top_publishers": publishers.most_common(10),
        "missing_required_fields": dict(missing),
        "invalid_urls": invalid_urls, "duplicate_urls": duplicates,
        "weak_classification": weak_classification,
        "knowledge": {"chains": len(chains), "entities": len(entities),
                      "entities_with_references": entity_refs},
        "warnings": warnings,
    }
