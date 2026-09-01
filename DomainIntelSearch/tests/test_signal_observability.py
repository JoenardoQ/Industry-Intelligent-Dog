from __future__ import annotations

from datetime import date, timedelta

import pytest

from intdog_core.repository import IntelligenceRepository


def _repo(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    industry_id = repo.ensure_industry("AI", "Artificial Intelligence")
    with repo.transaction() as con:
        con.execute("""INSERT INTO stories
            (id,industry_id,canonical_title,story_family,status,clustering_version,
             first_seen_at,last_seen_at,metadata_json,created_at,updated_at)
            VALUES('story-1',?,'Frontier model','technology','candidate','cluster-v1',
            '2026-01-01T05:00:00+08:00','2026-01-01T05:00:00+08:00','{}',
            '2026-01-01T05:00:00+08:00','2026-01-01T05:00:00+08:00')""",
                    (industry_id,))
    return repo


def _signal_api():
    from src.signal_momentum import (
        compute_story_momentum, intelligence_day, rank_signals,
    )
    return compute_story_momentum, intelligence_day, rank_signals


def test_intelligence_day_rank_ties_and_complete_momentum_state_machine(tmp_path):
    compute, intelligence_day, rank_signals = _signal_api()
    assert intelligence_day("2026-01-02T03:59:59+08:00") == "2026-01-01"
    assert intelligence_day("2026-01-02T04:00:00+08:00") == "2026-01-02"
    assert [(row["story_id"], row["rank"]) for row in rank_signals([
        {"story_id": "b", "score": 9}, {"story_id": "a", "score": 9},
        {"story_id": "c", "score": 7},
    ])] == [("a", 1), ("b", 1), ("c", 3)]

    observations = [
        {"id": "o1", "intelligence_date": "2026-01-01", "rank": 5,
         "score": 50, "independent_publishers": 1, "evidence_strength": .4,
         "classification": "open", "algorithm_version": "v1"},
        {"id": "o2", "intelligence_date": "2026-01-02", "rank": 2,
         "score": 65, "independent_publishers": 3, "evidence_strength": .7,
         "classification": "open", "algorithm_version": "v1"},
        {"id": "o3", "intelligence_date": "2026-01-03", "rank": 2,
         "score": 65, "independent_publishers": 3, "evidence_strength": .7,
         "classification": "open", "algorithm_version": "v1"},
        {"id": "o4", "intelligence_date": "2026-01-05", "rank": 7,
         "score": 40, "independent_publishers": 2, "evidence_strength": .5,
         "classification": "open", "algorithm_version": "v1"},
        {"id": "o5", "intelligence_date": "2026-01-10", "rank": 7,
         "score": 40, "independent_publishers": 2, "evidence_strength": .5,
         "classification": "unresolved", "algorithm_version": "v1"},
        {"id": "o6", "intelligence_date": "2026-01-11", "rank": 1,
         "score": 99, "independent_publishers": 6, "evidence_strength": .95,
         "classification": "open", "algorithm_version": "v2"},
    ]
    result = compute(observations)
    states = {row["intelligence_date"]: row for row in result["timeline"]}
    assert [states[day]["status"] for day in (
        "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-05",
        "2026-01-10")] == ["new", "heating", "tracking", "cooling", "unresolved"]
    assert states["2026-01-02"]["deltas"] == {
        "rank": 3, "score": 15.0, "independent_publishers": 2,
        "evidence_strength": .3}
    assert states["2026-01-05"]["missing_days"] == 1
    assert states["2026-01-10"]["seven_day_trend"]["score"] == -25.0
    assert states["2026-01-11"]["status"] == "tracking"
    assert states["2026-01-11"]["algorithm_segment_started"] is True
    assert states["2026-01-11"]["deltas"] is None


def test_story_observations_are_immutable_idempotent_and_ignore_syndicated_duplicates(
        tmp_path):
    repo = _repo(tmp_path)
    payload = {
        "observed_at": "2026-01-02T05:00:00+08:00", "rank": 2, "score": 72,
        "publisher_clusters": ["wire-owner", "wire-owner", "independent-owner"],
        "evidence_strength": .8, "classification": "open",
        "algorithm_version": "momentum-v1",
    }
    first = repo.record_story_observation("AI", "story-1", payload)
    second = repo.record_story_observation("AI", "story-1", dict(payload))
    assert first["id"] == second["id"]
    assert first["independent_publishers"] == 2
    assert len(repo.list_story_observations("AI", "story-1")) == 1
    changed_run = repo.record_story_observation("AI", "story-1", {
        **payload, "observed_at": "2026-01-02T06:00:00+08:00", "score": 73})
    assert changed_run["id"] == first["id"]
    assert len(repo.list_story_run_observations("AI", "story-1")) == 2
    with repo.connection() as con:
        try:
            con.execute("UPDATE story_observations SET score=1 WHERE id=?",
                        (first["source_observation_id"],))
        except Exception as exc:
            assert "append-only" in str(exc)
        else:
            raise AssertionError("story observations must reject mutation")


def test_story_momentum_batch_loads_timelines_without_per_story_queries(tmp_path):
    repo = _repo(tmp_path)
    repo.record_story_observation("AI", "story-1", {
        "observed_at": "2026-01-02T05:00:00+08:00", "rank": 2, "score": 72,
        "publisher_clusters": ["one", "two"], "evidence_strength": .8,
        "classification": "open", "algorithm_version": "momentum-v1"})
    statements = []
    with repo.connection() as connection:
        connection.set_trace_callback(statements.append)
        rows = repo.list_story_observations_batch("AI", ["story-1"], connection=connection)
    assert list(rows) == ["story-1"]
    selects = [sql for sql in statements if "story_daily_snapshots" in sql]
    assert len(selects) == 1


def test_quality_drift_has_7_30_day_windows_zero_denominators_and_version_segments():
    from src.quality_drift import analyze_quality_drift

    rows = []
    start = date(2026, 1, 1)
    for index in range(60):
        observed = (start + timedelta(days=index)).isoformat()
        score = .9 if index < 53 else .6
        rows.append({"id": f"v1-{index}", "observed_date": observed,
                     "metric": "fixed_eval_quality", "numerator": score,
                     "denominator": 1, "algorithm_version": "v1",
                     "dimensions": {"eval_set_id": "ai-golden-v1"}})
    rows.extend([
        {"id": "unknown-0", "observed_date": "2026-03-01",
         "metric": "classification_unknown_rate", "numerator": 0,
         "denominator": 0, "algorithm_version": "v1", "dimensions": {}},
        {"id": "v2-0", "observed_date": "2026-03-01",
         "metric": "fixed_eval_quality", "numerator": .95,
         "denominator": 1, "algorithm_version": "v2",
         "dimensions": {"eval_set_id": "ai-golden-v1"}},
    ])
    result = analyze_quality_drift(rows, as_of="2026-03-01",
                                   thresholds={"fixed_eval_quality": .1})
    v1 = {(row["metric"], row["window_days"]): row for row in result["metrics"]
          if row["algorithm_version"] == "v1"}
    assert {7, 30} <= {window for metric, window in v1
                       if metric == "fixed_eval_quality"}
    assert v1[("fixed_eval_quality", 7)]["status"] == "degraded"
    assert v1[("fixed_eval_quality", 7)]["baseline"] == .9
    assert v1[("fixed_eval_quality", 7)]["raw_observation_links"]
    assert v1[("classification_unknown_rate", 7)]["status"] == "insufficient_data"
    assert any(segment["algorithm_version"] == "v2" for segment in result["segments"])


def test_quality_observation_reruns_are_idempotent_and_schema17_is_repeatable(tmp_path):
    repo = _repo(tmp_path)
    item = {"observed_at": "2026-01-01T05:00:00+08:00",
            "metric": "source_success_rate", "numerator": 8, "denominator": 10,
            "algorithm_version": "quality-v1", "dimensions": {"source": "official"}}
    first = repo.record_quality_observation("AI", item)
    second = repo.record_quality_observation("AI", dict(item))
    repo.migrate()
    assert first["id"] == second["id"]
    assert len(repo.list_quality_observations("AI")) == 1
    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=17").fetchone()[0] == 1


def test_fixed_eval_requires_a_stable_eval_set_dimension(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError, match="eval_set_id"):
        repo.record_quality_observation("AI", {
            "observed_at": "2026-01-01T05:00:00+08:00",
            "metric": "fixed_eval_quality", "numerator": .9, "denominator": 1,
            "algorithm_version": "quality-v1", "dimensions": {}})


def test_ignoring_ranked_story_is_audited_once_and_records_quality_signal(tmp_path):
    repo = _repo(tmp_path)
    repo.record_story_observation("AI", "story-1", {
        "observed_at": "2026-01-01T05:00:00+08:00", "rank": 3, "score": 8,
        "publisher_clusters": ["authority-owner"], "evidence_strength": .7,
        "classification": "open", "algorithm_version": "momentum-v1",
    })
    repo.ignore_story("AI", "story-1", actor="local-user", reason="not relevant")
    with pytest.raises(ValueError, match="already ignored"):
        repo.ignore_story("AI", "story-1", actor="local-user", reason="again")
    assert repo.story_detail("AI", "story-1")["status"] == "ignored"
    observations = repo.list_quality_observations("AI")
    signal = next(row for row in observations
                  if row["metric"] == "top_item_ignore_rate")
    assert signal["dimensions"]["rank"] == 3
    assert signal["dimensions"]["reason"] == "not relevant"


def test_columnar_prototype_four_trigger_boundaries_keep_sqlite_authoritative():
    from src.quality_drift import evaluate_columnar_triggers

    base = dict(document_count=499_999, long_query_p95_seconds=.999,
                sqlite_write_blocked=False, backup_size_bytes=999,
                max_backup_size_bytes=1_000)
    assert evaluate_columnar_triggers(**base)["prototype_recommended"] is False
    cases = [
        {**base, "document_count": 500_000},
        {**base, "long_query_p95_seconds": 1.0},
        {**base, "sqlite_write_blocked": True},
        {**base, "backup_size_bytes": 1_000},
    ]
    reasons = ["document_volume", "query_p95", "write_blocking", "backup_size"]
    for case, reason in zip(cases, reasons, strict=True):
        result = evaluate_columnar_triggers(**case)
        assert result["prototype_recommended"] is True
        assert result["triggers"][reason] is True
        assert result["authority"] == "sqlite"
        assert result["write_path"] == "sqlite_only"
