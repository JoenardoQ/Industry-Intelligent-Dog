"""Append-only Story and system-quality observations backed only by SQLite."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import json_text, json_value, stable_id, utc_now


def _intelligence_date(timestamp: str) -> str:
    raw = str(timestamp)
    if len(raw) == 10:
        return datetime.fromisoformat(raw).date().isoformat()
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    local_zone = ZoneInfo("Asia/Shanghai")
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_zone)
    return (value.astimezone(local_zone) - timedelta(hours=4)).date().isoformat()


def _number(value: object, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError(f"{name} must be a finite number >= {minimum}")
    return number


def _required(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class ObservabilityRepositoryMixin:
    @staticmethod
    def _normalized_story_observation(payload: dict) -> dict:
        observed_at = _required(payload.get("observed_at"), "observed_at")
        algorithm_version = _required(
            payload.get("algorithm_version"), "algorithm_version")
        classification = _required(payload.get("classification"), "classification")
        rank = int(_number(payload.get("rank"), "rank", minimum=1))
        score = _number(payload.get("score"), "score")
        evidence_strength = _number(
            payload.get("evidence_strength"), "evidence_strength", minimum=0)
        clusters = sorted({_required(value, "publisher_cluster")
                           for value in payload.get("publisher_clusters", [])})
        normalized = {
            "observed_at": observed_at, "rank": rank, "score": score,
            "publisher_clusters": clusters,
            "independent_publishers": len(clusters),
            "evidence_strength": evidence_strength,
            "classification": classification,
            "algorithm_version": algorithm_version,
            "intelligence_date": _intelligence_date(observed_at),
        }
        return normalized

    def _insert_story_observation(self, con, industry_id: str, story_id: str,
                                  payload: dict, *, canonical_snapshot: bool) -> str:
        normalized = self._normalized_story_observation(payload)
        observation_id = stable_id(
            "sobs", industry_id, story_id, _canonical(normalized))
        con.execute("""INSERT INTO story_observations
            (id,industry_id,story_id,intelligence_date,observed_at,rank,score,
             independent_publishers,publisher_clusters_json,evidence_strength,
             classification,algorithm_version,raw_json,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
            (observation_id, industry_id, story_id,
             normalized["intelligence_date"], normalized["observed_at"],
             normalized["rank"], normalized["score"],
             normalized["independent_publishers"],
             json_text(normalized["publisher_clusters"]),
             normalized["evidence_strength"], normalized["classification"],
             normalized["algorithm_version"], json_text(normalized), utc_now()))
        if canonical_snapshot:
            snapshot_id = stable_id(
                "sday", industry_id, story_id, normalized["intelligence_date"],
                normalized["algorithm_version"])
            con.execute("""INSERT INTO story_daily_snapshots
                (id,industry_id,story_id,source_observation_id,intelligence_date,
                 observed_at,rank,score,independent_publishers,publisher_clusters_json,
                 evidence_strength,classification,algorithm_version,raw_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
                (snapshot_id, industry_id, story_id, observation_id,
                 normalized["intelligence_date"], normalized["observed_at"],
                 normalized["rank"], normalized["score"],
                 normalized["independent_publishers"],
                 json_text(normalized["publisher_clusters"]),
                 normalized["evidence_strength"], normalized["classification"],
                 normalized["algorithm_version"], json_text(normalized), utc_now()))
        return observation_id

    def record_story_observation(self, folder: str, story_id: str,
                                 payload: dict) -> dict:
        industry_id = self.industry_id(folder)
        normalized = self._normalized_story_observation(payload)
        with self.transaction() as con:
            story = con.execute("SELECT industry_id FROM stories WHERE id=?",
                                (story_id,)).fetchone()
            if not story or story["industry_id"] != industry_id:
                raise FileNotFoundError(f"Story not found: {story_id}")
            observation_id = self._insert_story_observation(
                con, industry_id, story_id, payload, canonical_snapshot=True)
        return next(row for row in self.list_story_observations(folder, story_id)
                    if row["intelligence_date"] == normalized["intelligence_date"]
                    and row["algorithm_version"] == normalized["algorithm_version"])

    def list_story_observations(self, folder: str, story_id: str) -> list[dict]:
        industry_id = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM story_daily_snapshots
                WHERE industry_id=? AND story_id=?
                ORDER BY intelligence_date,observed_at,id""",
                               (industry_id, story_id)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["publisher_clusters"] = json_value(
                item.pop("publisher_clusters_json"), [])
            item["raw"] = json_value(item.pop("raw_json"), {})
            output.append(item)
        return output

    def list_story_observations_batch(self, folder: str, story_ids: list[str],
                                      *, connection=None) -> dict[str, list[dict]]:
        """Load all requested timelines with one bounded SQL query."""
        unique = list(dict.fromkeys(str(value) for value in story_ids if str(value)))[:500]
        if not unique:
            return {}
        industry_id = self.industry_id(folder)
        marks = ",".join("?" for _ in unique)
        own_connection = connection is None
        con = connection or self.connection().__enter__()
        try:
            rows = con.execute(f"""SELECT * FROM story_daily_snapshots
                WHERE industry_id=? AND story_id IN ({marks})
                ORDER BY story_id,intelligence_date,observed_at,id""",
                               [industry_id, *unique]).fetchall()
        finally:
            if own_connection:
                con.close()
        output = {story_id: [] for story_id in unique}
        for row in rows:
            item = dict(row)
            item["publisher_clusters"] = json_value(
                item.pop("publisher_clusters_json"), [])
            item["raw"] = json_value(item.pop("raw_json"), {})
            output.setdefault(item["story_id"], []).append(item)
        return output

    def list_story_run_observations(self, folder: str,
                                    story_id: str | None = None) -> list[dict]:
        industry_id = self.industry_id(folder)
        sql = "SELECT * FROM story_observations WHERE industry_id=?"
        args: list[object] = [industry_id]
        if story_id:
            sql += " AND story_id=?"; args.append(story_id)
        sql += " ORDER BY intelligence_date,observed_at,id"
        with self.connection() as con:
            rows = con.execute(sql, args).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["publisher_clusters"] = json_value(
                item.pop("publisher_clusters_json"), [])
            item["raw"] = json_value(item.pop("raw_json"), {})
            output.append(item)
        return output

    def _insert_quality_observation(self, con, industry_id: str,
                                    payload: dict) -> str:
        observed_at = _required(payload.get("observed_at"), "observed_at")
        metric = _required(payload.get("metric"), "metric")
        algorithm_version = _required(
            payload.get("algorithm_version"), "algorithm_version")
        numerator = _number(payload.get("numerator"), "numerator")
        denominator = _number(payload.get("denominator"), "denominator", minimum=0)
        dimensions = payload.get("dimensions") or {}
        if not isinstance(dimensions, dict):
            raise ValueError("dimensions must be an object")
        if metric == "fixed_eval_quality" and not str(
                dimensions.get("eval_set_id") or "").strip():
            raise ValueError("fixed_eval_quality requires dimensions.eval_set_id")
        normalized = {
            "observed_at": observed_at, "observed_date": _intelligence_date(observed_at),
            "metric": metric, "numerator": numerator, "denominator": denominator,
            "algorithm_version": algorithm_version, "dimensions": dimensions,
        }
        observation_id = stable_id("qobs", industry_id, _canonical(normalized))
        con.execute("""INSERT INTO quality_observations
            (id,industry_id,observed_date,observed_at,metric,numerator,denominator,
             algorithm_version,dimensions_json,raw_json,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
            (observation_id, industry_id, normalized["observed_date"],
             observed_at, metric, numerator, denominator, algorithm_version,
             json_text(dimensions), json_text(normalized), utc_now()))
        return observation_id

    def record_quality_observation(self, folder: str, payload: dict) -> dict:
        industry_id = self.industry_id(folder)
        with self.transaction() as con:
            observation_id = self._insert_quality_observation(con, industry_id, payload)
        return next(row for row in self.list_quality_observations(folder)
                    if row["id"] == observation_id)

    def record_quality_observations(self, folder: str,
                                    payloads: list[dict]) -> list[str]:
        industry_id = self.industry_id(folder)
        with self.transaction() as con:
            return [self._insert_quality_observation(con, industry_id, payload)
                    for payload in payloads]

    def record_sqlite_operational_metrics(self, folder: str, *, observed_at: str,
                                          write_blocked: bool = False,
                                          long_query_seconds: float | None = None,
                                          max_backup_size_bytes: int = 4 * 1024**3) -> None:
        dimensions = {"database": self.db_path.name,
                      "max_backup_size_bytes": int(max_backup_size_bytes)}
        payloads = [{
            "observed_at": observed_at, "metric": "backup_size_bytes",
            "numerator": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "denominator": 1, "algorithm_version": "sqlite-operations-v1",
            "dimensions": dimensions,
        }, {
            "observed_at": observed_at, "metric": "sqlite_write_blocked",
            "numerator": int(bool(write_blocked)), "denominator": 1,
            "algorithm_version": "sqlite-operations-v1", "dimensions": dimensions,
        }]
        if long_query_seconds is not None:
            payloads.append({
                "observed_at": observed_at,
                "metric": "long_query_latency_seconds",
                "numerator": max(0.0, float(long_query_seconds)), "denominator": 1,
                "algorithm_version": "sqlite-operations-v1", "dimensions": dimensions,
            })
        self.record_quality_observations(folder, payloads)

    def list_quality_observations(self, folder: str) -> list[dict]:
        industry_id = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM quality_observations
                WHERE industry_id=? ORDER BY observed_date,observed_at,id""",
                               (industry_id,)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["dimensions"] = json_value(item.pop("dimensions_json"), {})
            item["raw"] = json_value(item.pop("raw_json"), {})
            output.append(item)
        return output
