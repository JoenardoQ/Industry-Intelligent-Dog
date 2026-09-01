"""Quality drift diagnostics and evidence-based columnar prototype triggers."""

from __future__ import annotations

import json
from datetime import date, timedelta


DEFAULT_THRESHOLDS = {
    "source_success_rate": .1, "source_latency_ms": .2, "valid_yield": .15,
    "duplicate_rate": .1, "independent_publisher_rate": .1,
    "citation_failure_rate": .05, "classification_unknown_rate": .05,
    "manual_correction_rate": .05, "top_item_ignore_rate": .1,
    "chain_node_coverage_change": .1, "fixed_eval_quality": .05,
}
LOWER_IS_BETTER = {
    "source_latency_ms", "duplicate_rate", "citation_failure_rate",
    "classification_unknown_rate", "manual_correction_rate", "top_item_ignore_rate",
}


def _aggregate(rows: list[dict]) -> tuple[float | None, float]:
    denominator = sum(float(row.get("denominator") or 0) for row in rows)
    if denominator <= 0:
        return None, denominator
    return (round(sum(float(row.get("numerator") or 0) for row in rows) /
                  denominator, 8), denominator)


def analyze_quality_drift(observations: list[dict], *, as_of: str,
                          thresholds: dict[str, float] | None = None) -> dict:
    end = date.fromisoformat(as_of)
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for item in observations:
        dimensions = item.get("dimensions") or {}
        if not isinstance(dimensions, dict):
            raise ValueError("quality observation dimensions must be an object")
        if (item["metric"] == "fixed_eval_quality" and
                not str(dimensions.get("eval_set_id") or "").strip()):
            raise ValueError("fixed_eval_quality requires dimensions.eval_set_id")
        dimension_key = json.dumps(
            dimensions, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        groups.setdefault((str(item["algorithm_version"]), str(item["metric"]),
                           dimension_key), []).append(dict(item))
    metrics = []
    segments = []
    for (version, metric, dimension_key), rows in sorted(groups.items()):
        dimensions = json.loads(dimension_key)
        rows.sort(key=lambda row: (row["observed_date"], row["id"]))
        segments.append({"algorithm_version": version, "metric": metric,
                         "dimensions": dimensions,
                         "start": rows[0]["observed_date"], "end": rows[-1]["observed_date"],
                         "observation_count": len(rows)})
        for days in (7, 30):
            start = end - timedelta(days=days - 1)
            baseline_start = start - timedelta(days=days)
            current_rows = [row for row in rows
                            if start <= date.fromisoformat(row["observed_date"]) <= end]
            baseline_rows = [row for row in rows if baseline_start <= date.fromisoformat(
                row["observed_date"]) < start]
            current, denominator = _aggregate(current_rows)
            baseline, baseline_denominator = _aggregate(baseline_rows)
            threshold = float(limits.get(metric, .1))
            delta = None if current is None or baseline is None else round(
                current - baseline, 8)
            if current is None or baseline is None:
                status = "insufficient_data"
            elif metric in LOWER_IS_BETTER:
                status = "degraded" if delta > threshold else "stable"
            else:
                status = "degraded" if delta < -threshold else "stable"
            metrics.append({
                "metric": metric, "window_days": days, "algorithm_version": version,
                "dimensions": dimensions,
                "value": current, "numerator": round(sum(float(
                    row.get("numerator") or 0) for row in current_rows), 8),
                "denominator": denominator, "baseline": baseline,
                "baseline_denominator": baseline_denominator, "delta": delta,
                "threshold": threshold, "status": status,
                "raw_observation_links": [f"observation://quality/{row['id']}"
                                          for row in current_rows],
                "diagnosis": (f"{metric} {days}日窗口相对同版本基线退化"
                              if status == "degraded" else
                              "分母或同版本基线不足" if status == "insufficient_data"
                              else "处于阈值内"),
            })
    return {"as_of": as_of, "metrics": metrics, "segments": segments,
            "alert_count": sum(row["status"] == "degraded" for row in metrics)}


def evaluate_columnar_triggers(*, document_count: int,
                               long_query_p95_seconds: float,
                               sqlite_write_blocked: bool,
                               backup_size_bytes: int,
                               max_backup_size_bytes: int) -> dict:
    triggers = {
        "document_volume": int(document_count) >= 500_000,
        "query_p95": float(long_query_p95_seconds) >= 1.0,
        "write_blocking": bool(sqlite_write_blocked),
        "backup_size": int(backup_size_bytes) >= int(max_backup_size_bytes),
    }
    return {"prototype_recommended": any(triggers.values()), "triggers": triggers,
            "authority": "sqlite", "write_path": "sqlite_only",
            "prototype_policy": "single-direction-derived-read-model-only"}
