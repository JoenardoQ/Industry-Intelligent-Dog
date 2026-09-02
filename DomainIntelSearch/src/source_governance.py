"""Bounded source portfolio governance without destructive catalog pruning."""

from __future__ import annotations

from collections import Counter

from intdog_core.models import canonical_url
from intdog_core.source_trust import source_verification

from .source_discovery import SOURCE_CATEGORIES, source_origin
from .source_review import assess_source_candidate


ALGORITHM_VERSION = "source-governance-v2"
POLICIES = {category: (8, 10, 10) for category, _ in SOURCE_CATEGORIES}


def category_target(category: str, chain_count: int = 0) -> dict:
    minimum, target, maximum = POLICIES[category]
    return {"minimum": minimum, "target": target,
            "maximum": maximum, "chain_count": max(0, int(chain_count))}


def _coverage(item: dict) -> set[str]:
    value = item.get("coverage") or []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    return {str(part).strip().casefold() for part in value if str(part).strip()}


def _canonical_catalog(category: str, entries: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    invalid: list[dict] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        url = canonical_url(item.get("url", ""))
        if not url:
            assessment = assess_source_candidate(item, category=category)
            item.update({
                "monitoring_status": "rejected",
                "governance_role": "rejected",
                "governance_score": assessment["score"],
                **assessment,
            })
            item["governance_reason"] = assessment["reason"]
            invalid.append(item)
            continue
        item["url"] = url
        previous = by_url.get(url)
        score = assess_source_candidate(item, category=category)["score"]
        previous_score = (assess_source_candidate(previous, category=category)["score"]
                          if previous is not None else -1)
        if previous is None or score > previous_score:
            by_url[url] = item
    return list(by_url.values()) + invalid


def govern_category(category: str, entries: list[dict], chain_count: int = 0) -> tuple[list[dict], dict]:
    boundary = category_target(category, chain_count)
    catalog = _canonical_catalog(category, entries)
    candidates, rejected = [], []
    for item in catalog:
        if item.get("monitoring_status") == "rejected":
            rejected.append(item)
            continue
        context = {"china_gap": bool(item.get("fills_china_gap"))}
        assessment = assess_source_candidate(item, category=category, context=context)
        item.update(assessment)
        item["governance_score"] = assessment["score"]
        item["governance_reason"] = assessment["reason"]
        candidates.append(item)

    topic_frequency: Counter[str] = Counter(
        topic for item in candidates for topic in _coverage(item))
    candidates.sort(key=lambda item: (
        -sum(1 / topic_frequency[topic] for topic in _coverage(item)),
        -int(item["governance_score"]),
        -int(item["score_components"].get("china_gap", 0)),
        0 if source_origin(item) == "china" else 1,
        str(item.get("name") or "").casefold(), item.get("url", "")))
    active, manual, reserve = [], [], []
    publishers: Counter[str] = Counter()
    origins: Counter[str] = Counter()
    covered_topics: set[str] = set()
    authority_present = False
    for item in candidates:
        publisher = source_verification(item)["owner_cluster"]
        topics = _coverage(item)
        origin = source_origin(item)
        new_topics = topics - covered_topics
        new_origin = origin not in origins
        tier = str(item.get("tier") or "").casefold()
        adds_authority = tier in {"primary", "authoritative"} and not authority_present
        context = {
            "duplicate_owner": publishers[publisher] > 0 and not new_topics and not new_origin,
            "china_gap": bool(item.get("fills_china_gap")),
        }
        assessment = assess_source_candidate(item, category=category, context=context)
        item.update(assessment)
        item["governance_score"] = assessment["score"]
        item["governance_reason"] = assessment["reason"]
        gains = []
        if adds_authority:
            gains.append("authority")
        if new_origin:
            gains.append("region")
        if new_topics:
            gains.append("topic")
        if publishers[publisher] == 0:
            gains.append("publisher")
        item["coverage_gain"] = gains
        if assessment["decision"] == "active" and len(active) < boundary["maximum"]:
            item["monitoring_status"] = "active"
            item["governance_role"] = "core" if len(active) < boundary["minimum"] else "coverage"
            active.append(item)
            publishers[publisher] += 1
            origins[origin] += 1
            covered_topics.update(topics)
            authority_present = authority_present or tier in {"primary", "authoritative"}
        elif assessment["decision"] == "manual_review":
            item["monitoring_status"] = "recommended_manual"
            item["governance_role"] = "manual"
            manual.append(item)
        elif assessment["decision"] == "rejected":
            item["monitoring_status"] = "rejected"
            item["governance_role"] = "rejected"
            rejected.append(item)
        else:
            item["monitoring_status"] = "reserve"
            item["governance_role"] = "reserve"
            if assessment["decision"] == "active":
                item["decision"] = "reserve"
                item["reason"] = "portfolio_boundary_reached"
                item["governance_reason"] = "portfolio_boundary_reached"
            reserve.append(item)

    all_items = active + manual + reserve + rejected
    all_items.sort(key=lambda item: (
        {"active": 0, "recommended_manual": 1, "reserve": 2,
         "rejected": 3}.get(item.get("monitoring_status"), 4),
        -int(item.get("governance_score") or 0), str(item.get("name") or "").casefold()))
    shortage = max(0, boundary["minimum"] - len(active))
    audit = {**boundary, "registered": len(all_items), "active": len(active),
             "manual": len(manual), "reserve": len(reserve),
             "quarantined": len(rejected), "rejected": len(rejected),
             "shortage": shortage,
             "origins": dict(origins), "publisher_count": len(publishers),
             "stopping_reason": ("insufficient_qualified_sources" if shortage else
                                 "dynamic_target_reached" if len(active) >= boundary["target"] else
                                 "no_additional_coverage_gain")}
    return all_items, audit


def govern_sources(sources: dict, chain_count: int = 0) -> dict:
    governed = {key: value for key, value in dict(sources).items()
                if key not in {category for category, _ in SOURCE_CATEGORIES}}
    audits = {}
    for category, _ in SOURCE_CATEGORIES:
        governed[category], audits[category] = govern_category(
            category, sources.get(category, []) or [], chain_count)
    totals = Counter()
    for audit in audits.values():
        for key in ("registered", "active", "manual", "reserve", "quarantined", "shortage"):
            totals[key] += int(audit[key])
    governed["source_governance"] = {
        "algorithm": ALGORITHM_VERSION, "chain_count": chain_count,
        "categories": audits, "totals": dict(totals),
        "policy": "dynamic_active_portfolio_non_destructive_catalog",
    }
    return governed
