"""Local source-health and longitudinal coverage metrics."""

from __future__ import annotations

from collections import Counter
from datetime import date

from .contracts import SOURCE_CATEGORIES


def build_source_observatory(observations: list[dict], overlap: dict, inventory: dict,
                             stale_days: int, previous: dict | None = None) -> dict:
    today = date.today()
    statuses, categories, clusters, origins = Counter(), Counter(), Counter(), Counter()
    for item in observations:
        categories[item["category"]] += 1
        clusters[item["publisher_cluster"]] += 1
        raw_origin = str(item.get("origin") or "unknown").lower()
        origin = ("china" if raw_origin in {"china", "domestic", "cn", "中国"} else
                  "international" if raw_origin in {"foreign", "international", "global"}
                  else "unknown")
        item["normalized_origin"] = origin
        origins[origin] += 1
        if item.get("monitoring_status") == "recommended_manual":
            status = "manual_watch"
        elif item["document_count"] == 0:
            status = "unused"
        elif item["last_observed"]:
            try:
                age = (today - date.fromisoformat(item["last_observed"][:10])).days
            except ValueError:
                age = stale_days + 1
            status = "stale" if age > stale_days else "active"
            item["age_days"] = age
        else:
            status = "unused"
        if status == "active" and item["publisher_verification"] != "verified":
            status = "unverified"
        item["health_status"] = status
        statuses[status] += 1
    missing = [category for category in SOURCE_CATEGORIES if not categories[category]]
    source_links = len(observations)
    total_cluster_links = sum(clusters.values()) or 1
    hhi = round(sum((count / total_cluster_links) ** 2 for count in clusters.values()), 4)
    document_counts = inventory.get("documents_by_cluster", {})
    unique_documents = int(inventory.get("unique_documents", 0))
    document_hhi = round(sum((count / unique_documents) ** 2
                             for count in document_counts.values()), 4) if unique_documents else 0.0
    metrics = {"source_links": source_links,
               "unique_sources": int(inventory.get("unique_sources", 0)),
               "publisher_clusters": len(clusters),
               "missing_categories": len(missing), "source_link_hhi": hhi,
               "publisher_hhi": hhi, "document_hhi": document_hhi,
               "documents": unique_documents,
               **{key: statuses[key] for key in
                  ("active", "unverified", "stale", "unused", "manual_watch")},
               **overlap}
    previous_metrics = (previous or {}).get("metrics", {})
    delta = {key: metrics[key] - previous_metrics[key]
             for key in ("source_links", "publisher_clusters", "documents", "active")
             if isinstance(previous_metrics.get(key), (int, float))}
    return {"kind": "source_observatory", "stale_days": stale_days,
            "metrics": metrics, "metric_delta": delta, "metric_definitions": {
                "source_links": "行业—来源—类别链接数；同一来源可出现多次",
                "unique_sources": "去重后的规范来源数", "documents": "去重后的行业文档数",
                "source_link_hhi": "按来源链接计算的发布者集中度",
                "document_hhi": "按唯一文档产出计算的发布者集中度"},
            "missing_categories": missing, "origin_counts": dict(origins),
            "duplicate_publisher_clusters": [
                {"cluster": key, "source_links": count}
                for key, count in clusters.items() if count > 1],
            "sources": observations}
