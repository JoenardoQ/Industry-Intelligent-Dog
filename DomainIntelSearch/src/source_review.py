"""Deterministic source admission and periodic-review decisions."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from intdog_core.models import canonical_url
from intdog_core.source_trust import publisher_profile, source_verification

from .source_discovery import source_origin


HUMAN_REVIEW_CATEGORIES = {"blogs", "platforms", "self_media", "news", "finance"}
PRIMARY_CATEGORIES = {"official", "associations", "journals", "financials"}


def _as_date(value) -> date:
    if value is None:
        return datetime.now().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("now must be a date or datetime")


def _human_approved(item: dict) -> bool:
    review = item.get("human_review")
    if not isinstance(review, dict):
        return False
    return (
        str(review.get("decision") or "").casefold() in {"active", "approved"}
        and bool(str(review.get("actor") or "").strip())
        and bool(str(review.get("reason") or "").strip()))


def _score_components(item: dict, verification: dict, context: dict) -> dict[str, int]:
    profile = publisher_profile(item)
    tier = str(item.get("tier") or "secondary").casefold()
    access = str(item.get("access") or "web").casefold()
    coverage = item.get("coverage") or []
    if isinstance(coverage, str):
        coverage = [part.strip() for part in coverage.split(",") if part.strip()]
    success_rate = item.get("historical_success_rate")
    citation_rate = item.get("citation_quality")
    try:
        stability = round(max(0.0, min(1.0, float(success_rate))) * 8)
    except (TypeError, ValueError):
        stability = 0
    try:
        citation_quality = round(max(0.0, min(1.0, float(citation_rate))) * 8)
    except (TypeError, ValueError):
        citation_quality = 0
    components = {
        "identity": 20 if verification["identity_passed"] else (
            4 if verification["identity_hint"] else 0),
        "ownership": 20 if verification["ownership_passed"] else 0,
        "url": 15 if verification["url_passed"] else 0,
        "publisher_quality": round(float(profile["quality"]) * 10),
        "primary_status": 8 if tier in {"primary", "authoritative"} else 2,
        "access": 6 if access in {"api", "rss", "atom", "feed"} else 2,
        "coverage": min(7, len({str(value).casefold() for value in coverage}) * 2),
        "stability": stability,
        "citation_quality": citation_quality,
        "china_gap": 8 if (source_origin(item) == "china" and
                           (item.get("fills_china_gap") or context.get("china_gap"))) else 0,
        "same_owner_penalty": -30 if context.get("duplicate_owner") else 0,
        "ownership_change_penalty": -35 if verification["ownership_changed"] else 0,
        "zero_value_penalty": -30 if (
            int(item.get("days_observed") or 0) >= 90
            and item.get("useful_output_count") == 0
            and item.get("marginal_value_30d") == 0) else 0,
        "content_farm_penalty": -100 if (
            item.get("content_farm") is True or
            float(item.get("content_farm_score") or 0) >= 0.7) else 0,
    }
    return components


def _decision(item: dict, category: str, verification: dict,
              context: dict) -> tuple[str, str]:
    if not canonical_url(item.get("url", "")):
        return "rejected", "invalid_url"
    if (item.get("content_farm") is True or
            float(item.get("content_farm_score") or 0) >= 0.7):
        return "rejected", "content_farm"
    if verification["ownership_changed"]:
        return "manual_review", "ownership_changed"
    if (int(item.get("days_observed") or 0) >= 90
            and item.get("useful_output_count") == 0
            and item.get("marginal_value_30d") == 0):
        return "reserve", "long_term_zero_value"
    if context.get("duplicate_owner"):
        return "reserve", "same_owner_duplicate"
    human_approved = _human_approved(item)
    if human_approved:
        if verification["all_passed"]:
            return "active", "human_review_approved"
        return "manual_review", "verification_incomplete"
    if item.get("added_manually"):
        return "manual_review", "manual_addition_requires_review"
    if str(item.get("monitoring_status") or "").casefold() in {
            "manual", "recommended_manual"}:
        return "manual_review", "manual_review_required"
    if category in HUMAN_REVIEW_CATEGORIES:
        return "manual_review", "human_review_required"
    if category in PRIMARY_CATEGORIES and verification["all_passed"]:
        return "active", "verified_primary_source"
    return "manual_review", "verification_incomplete"


def _review_due(current: date, decision: str) -> str:
    days = {"active": 90, "manual_review": 0, "reserve": 30,
            "rejected": 180}[decision]
    return (current + timedelta(days=days)).isoformat()


def assess_source_candidate(item: dict, *, category: str,
                            context: dict | None = None, now=None) -> dict:
    if not isinstance(item, dict):
        raise ValueError("source candidate must be an object")
    normalized_category = str(category or "").strip().casefold()
    if normalized_category not in PRIMARY_CATEGORIES | HUMAN_REVIEW_CATEGORIES:
        raise ValueError(f"unknown source category: {category}")
    normalized_context = dict(context or {})
    verification = source_verification(item)
    components = _score_components(item, verification, normalized_context)
    decision, reason = _decision(
        item, normalized_category, verification, normalized_context)
    return {
        "score": max(0, min(100, sum(components.values()))),
        "score_components": components,
        "decision": decision,
        "reason": reason,
        "review_due_at": _review_due(_as_date(now), decision),
        "identity_hint": verification["identity_hint"],
        "verification": verification,
        "algorithm_version": "source-review-v1",
    }
