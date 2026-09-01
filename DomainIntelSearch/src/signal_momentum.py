"""Deterministic cross-day Story momentum derived from immutable observations."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
BOUNDARY_HOUR = 4
UNRESOLVED_DAYS = 7


def intelligence_day(timestamp: str, *, boundary_hour: int = BOUNDARY_HOUR) -> str:
    raw = str(timestamp)
    if len(raw) == 10:
        return datetime.fromisoformat(raw).date().isoformat()
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=LOCAL_ZONE)
    local = value.astimezone(LOCAL_ZONE) - timedelta(hours=boundary_hour)
    return local.date().isoformat()


def rank_signals(signals: list[dict]) -> list[dict]:
    ordered = sorted((dict(item) for item in signals), key=lambda item: (
        -float(item.get("score") or 0), str(item.get("story_id") or "")))
    previous_score = None
    previous_rank = 0
    for position, item in enumerate(ordered, start=1):
        score = float(item.get("score") or 0)
        if previous_score is None or score != previous_score:
            previous_rank = position
        item["rank"] = previous_rank
        previous_score = score
    return ordered


def _delta(current: dict, previous: dict) -> dict:
    return {
        "rank": int(previous["rank"]) - int(current["rank"]),
        "score": round(float(current["score"]) - float(previous["score"]), 8),
        "independent_publishers": (int(current["independent_publishers"]) -
                                   int(previous["independent_publishers"])),
        "evidence_strength": round(float(current["evidence_strength"]) -
                                   float(previous["evidence_strength"]), 8),
    }


def _trend(segment: list[dict], current: dict) -> dict:
    current_date = datetime.fromisoformat(current["intelligence_date"]).date()
    eligible = [row for row in segment
                if 0 <= (current_date - datetime.fromisoformat(
                    row["intelligence_date"]).date()).days <= 7]
    oldest = eligible[0] if eligible else current
    return _delta(current, oldest)


def _status(delta: dict | None) -> str:
    if delta is None:
        return "tracking"
    positives = sum(value > 0 for value in delta.values())
    negatives = sum(value < 0 for value in delta.values())
    if delta["independent_publishers"] > 0 or positives >= 2:
        return "heating"
    if negatives >= 2 and positives == 0:
        return "cooling"
    return "tracking"


def compute_story_momentum(observations: list[dict]) -> dict:
    canonical: dict[tuple[str, str], dict] = {}
    for row in observations:
        item = dict(row)
        key = (str(item["intelligence_date"]), str(item["algorithm_version"]))
        current = canonical.get(key)
        if current is None or (str(item.get("id") or ""), str(item.get("observed_at") or "")) < (
                str(current.get("id") or ""), str(current.get("observed_at") or "")):
            canonical[key] = item
    ordered = sorted(canonical.values(), key=lambda row: (
        row["intelligence_date"], row.get("observed_at", ""), row["id"]))
    if not ordered:
        return {"status": "new", "timeline": [], "raw_observation_links": []}
    first_date = datetime.fromisoformat(ordered[0]["intelligence_date"]).date()
    timeline: list[dict] = []
    by_version: dict[str, list[dict]] = {}
    for index, current in enumerate(ordered):
        version = str(current["algorithm_version"])
        segment = by_version.setdefault(version, [])
        previous = segment[-1] if segment else None
        delta = _delta(current, previous) if previous else None
        current_date = datetime.fromisoformat(current["intelligence_date"]).date()
        missing_days = max(0, (current_date - datetime.fromisoformat(
            previous["intelligence_date"]).date()).days - 1) if previous else 0
        status = "new" if index == 0 else _status(delta)
        if (str(current.get("classification") or "").casefold() in {
                "open", "unresolved", "candidate"} and
                (current_date - first_date).days >= UNRESOLVED_DAYS and
                previous is not None):
            status = "unresolved"
        segment.append(current)
        timeline.append({
            **current, "status": status, "deltas": delta,
            "missing_days": missing_days,
            "algorithm_segment_started": previous is None and index > 0,
            "seven_day_trend": _trend(segment, current),
            "raw_observation_link": f"observation://story/{current['id']}",
        })
    return {
        "status": timeline[-1]["status"], "timeline": timeline,
        "first_appearance": ordered[0]["intelligence_date"],
        "last_observation": ordered[-1]["intelligence_date"],
        "raw_observation_links": [row["raw_observation_link"] for row in timeline],
    }
