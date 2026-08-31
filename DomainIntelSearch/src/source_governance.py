"""Bounded source portfolio governance without destructive catalog pruning."""

from __future__ import annotations

from collections import Counter

from intdog_core.models import canonical_url
from intdog_core.source_trust import publisher_profile

from .source_discovery import SOURCE_CATEGORIES, source_origin


ALGORITHM_VERSION = "source-governance-v1"
POLICIES = {
    "official": (4, 6, 12), "associations": (3, 5, 9),
    "blogs": (3, 5, 9), "platforms": (3, 5, 9),
    "self_media": (2, 4, 6), "news": (5, 8, 14),
    "journals": (4, 6, 12), "financials": (4, 6, 12),
    "finance": (3, 5, 9),
}
_TIER_SCORE = {"primary": 28, "authoritative": 22, "secondary": 10, "signal": 2}
_MANUAL = {"recommended_manual", "manual"}


def category_target(category: str, chain_count: int = 0) -> dict:
    minimum, baseline, maximum = POLICIES[category]
    increment = 3 if chain_count >= 24 else 2 if chain_count >= 12 else 1 if chain_count >= 6 else 0
    return {"minimum": minimum, "target": min(maximum, baseline + increment),
            "maximum": maximum, "chain_count": max(0, int(chain_count))}


def _coverage(item: dict) -> set[str]:
    value = item.get("coverage") or []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    return {str(part).strip().casefold() for part in value if str(part).strip()}


def _score(item: dict) -> int:
    profile = publisher_profile(item)
    score = round(float(profile["quality"]) * 40)
    score += _TIER_SCORE.get(str(item.get("tier") or "secondary").casefold(), 8)
    access = str(item.get("access") or "").casefold()
    score += 18 if access == "api" else 15 if access in {"rss", "atom", "feed"} else 5
    if item.get("rss_url") or item.get("feed_url"):
        score += 8
    score += min(8, len(_coverage(item)) * 2)
    if source_origin(item) == "china":
        score += 5
    if item.get("added_manually"):
        score += 2
    if (item.get("access_check") or {}).get("reachable") is False:
        score -= 15
    return max(0, min(100, score))


def _canonical_catalog(entries: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    invalid: list[dict] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        url = canonical_url(item.get("url", ""))
        if not url:
            item["monitoring_status"] = "quarantined"
            item["governance_reason"] = "invalid_url"
            invalid.append(item)
            continue
        item["url"] = url
        previous = by_url.get(url)
        if previous is None or _score(item) > _score(previous):
            by_url[url] = item
    return list(by_url.values()) + invalid


def govern_category(category: str, entries: list[dict], chain_count: int = 0) -> tuple[list[dict], dict]:
    boundary = category_target(category, chain_count)
    catalog = _canonical_catalog(entries)
    manual, candidates, quarantined = [], [], []
    for item in catalog:
        status = str(item.get("monitoring_status") or "active").casefold()
        if status == "quarantined":
            quarantined.append(item)
        elif status in _MANUAL:
            item["monitoring_status"] = "recommended_manual"
            item["governance_role"] = "manual"
            item["governance_score"] = _score(item)
            manual.append(item)
        else:
            item["governance_score"] = _score(item)
            candidates.append(item)

    candidates.sort(key=lambda item: (
        -int(item["governance_score"]),
        0 if source_origin(item) == "china" else 1,
        str(item.get("name") or "").casefold(), item.get("url", "")))
    active, reserve = [], []
    publishers: Counter[str] = Counter()
    covered: set[str] = set()
    origins: Counter[str] = Counter()
    access_modes: set[str] = set()
    for item in candidates:
        profile = publisher_profile(item)
        publisher = profile["owner_cluster"]
        coverage = _coverage(item)
        origin = source_origin(item)
        access = str(item.get("access") or "web").casefold()
        adds_dimension = bool(coverage - covered) or origin not in origins or access not in access_modes
        critical_gain = (bool(item.get("fills_critical_gap")) or
                         origin not in origins or access not in access_modes)
        distinct_publisher = publishers[publisher] == 0
        below_target = len(active) < boundary["target"]
        eligible = item["governance_score"] >= 25
        select = eligible and len(active) < boundary["maximum"] and (
            (below_target and (distinct_publisher or adds_dimension)) or
            (not below_target and distinct_publisher and critical_gain))
        if select:
            item["monitoring_status"] = "active"
            item["governance_role"] = "core" if len(active) < boundary["minimum"] else "coverage"
            item["governance_reason"] = "quality_and_coverage"
            active.append(item)
            publishers[publisher] += 1
            covered.update(coverage)
            origins[origin] += 1
            access_modes.add(access)
        else:
            item["monitoring_status"] = "reserve"
            item["governance_role"] = "reserve"
            item["governance_reason"] = (
                "below_quality_floor" if not eligible else
                "publisher_redundancy" if not distinct_publisher and not adds_dimension else
                "portfolio_boundary_reached")
            reserve.append(item)

    all_items = active + manual + reserve + quarantined
    all_items.sort(key=lambda item: (
        {"active": 0, "recommended_manual": 1, "reserve": 2,
         "quarantined": 3}.get(item.get("monitoring_status"), 4),
        -int(item.get("governance_score") or 0), str(item.get("name") or "").casefold()))
    shortage = max(0, boundary["minimum"] - len(active))
    audit = {**boundary, "registered": len(all_items), "active": len(active),
             "manual": len(manual), "reserve": len(reserve),
             "quarantined": len(quarantined), "shortage": shortage,
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
