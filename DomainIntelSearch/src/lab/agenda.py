"""Knowledge-boundary agenda construction."""

from __future__ import annotations


def build_agenda_items(folder: str, evidence: dict, sources: dict) -> list[dict]:
    items = []
    for gap in evidence.get("chain_gaps", []):
        priority = {"empty": 95, "thin": 85, "partial": 72}.get(gap["coverage_status"], 60)
        items.append({"dimension": "value_chain", "target_key": gap["id"],
            "title": f"补全产业链节点：{gap['name']}", "priority": priority,
            "rationale": f"当前覆盖为 {gap['coverage_status']}；实体 {gap['entity_count']}，"
                         f"有证据实体 {gap['evidenced_entities']}。",
            "queries": [f"{gap['name']} 主要企业 官方", f"{gap['name']} 研究组 论文",
                        f"{gap['name']} market suppliers"],
            "acceptance": {"minimum_entities": 3, "minimum_evidenced_entities": 2,
                           "minimum_publisher_clusters": 2}})
    claim_priority = {"contested": 92, "unsupported": 88, "single_source": 76}
    for claim in evidence.get("claims", []):
        state = claim["evidence_state"]
        if state not in claim_priority:
            continue
        items.append({"dimension": "claim", "target_key": claim["id"],
            "title": f"核验主张：{claim['predicate']}", "priority": claim_priority[state],
            "rationale": f"证据状态为 {state}；独立支持簇 "
                         f"{claim['independent_supporting_publishers']}；"
                         f"支持权重 {claim.get('support_weight', 0)}。",
            "queries": [f"{claim['subject']} {claim['predicate']} 官方",
                        f"{claim['subject']} {claim['predicate']} independent source"],
            "acceptance": {"minimum_independent_supporting_publishers": 2,
                           "resolve_contradictions": state == "contested"}})
    for category in sources.get("missing_categories", []):
        items.append({"dimension": "source_category", "target_key": category,
            "title": f"补充来源类别：{category}", "priority": 70,
            "rationale": "当前行业没有该类别的有效来源链接。",
            "queries": [f"{folder} {category} official source",
                        f"{folder} {category} 中文 权威来源"],
            "acceptance": {"minimum_sources": 3, "minimum_verified_publishers": 1}})
    for source in sources.get("sources", []):
        if source.get("health_status") not in {"stale", "unused"}:
            continue
        items.append({"dimension": "source_health",
            "target_key": f"{source['id']}:{source['category']}",
            "title": f"检查来源：{source['name']}",
            "priority": 66 if source["health_status"] == "stale" else 58,
            "rationale": f"本地观测状态为 {source['health_status']}；这不等于网站失效。",
            "queries": [source["url"]],
            "acceptance": {"manual_reachability_review": True,
                           "observed_document_or_manual_status": True}})
    if sources.get("metrics", {}).get("publisher_hhi", 0) > 0.35:
        items.append({"dimension": "source_diversity", "target_key": "publisher_hhi",
            "title": "降低发布者集中度", "priority": 74,
            "rationale": f"当前发布者 HHI 为 {sources['metrics']['publisher_hhi']}。",
            "queries": [f"{folder} independent industry sources",
                        f"{folder} 国内 官方 行业协会"],
            "acceptance": {"publisher_hhi_below": 0.35,
                           "minimum_publisher_clusters": 4}})
    items.sort(key=lambda item: (-item["priority"], item["dimension"], item["target_key"]))
    return items
