"""P0 coverage for one-shot scheduling, recovery and long-horizon quality."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from intdog_core import IntDogService
from intdog_core.repository import SCHEMA_VERSION


class FakeJob:
    def __init__(self, run_id: str, status: str):
        self.run_id = run_id
        self._result = SimpleNamespace(status=status, error=(
            "partial evidence" if status == "partial" else
            "provider unavailable" if status == "paused" else
            "process failed" if status == "failed" else ""))
        self.waited = False

    def wait(self, _timeout=None):
        self.waited = True
        return self._result


class FakeJobs:
    def __init__(self, statuses=("completed",)):
        self.statuses = list(statuses)
        self.calls = []
        self.jobs = []

    def start(self, command, **kwargs):
        status = self.statuses.pop(0)
        job = FakeJob(f"job-{len(self.jobs) + 1}", status)
        self.calls.append((command, kwargs))
        self.jobs.append(job)
        return job


def _schedule(service, action="daily", *, provider="public_sources",
              pipeline_mode="aggregate"):
    return service.repo.update_schedule(
        "AI", action, enabled=True, local_time="08:00", weekday=0, monthday=1,
        timezone_name="Asia/Shanghai", catch_up=True,
        provider=provider, pipeline_mode=pipeline_mode)


def test_latest_schema_and_app_worker_share_one_atomic_period_claim(tmp_path):
    from src.background_worker import claim_due_schedules

    service = IntDogService(tmp_path)
    service.create_industry("AI")
    _schedule(service)
    now = datetime(2026, 9, 2, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    app = claim_due_schedules(
        service.repo, now=now, owner="app:one", poll_seconds=15)
    worker = claim_due_schedules(
        service.repo, now=now, owner="worker:one", poll_seconds=15)
    assert SCHEMA_VERSION == 22
    assert len(app) == 1 and worker == []
    assert app[0].period_key == "2026-09-02"
    assert "Asia/Shanghai" in app[0].period_identity


def test_child_environment_is_an_allowlist_not_a_secret_name_denylist(
        monkeypatch, tmp_path):
    from src.background_worker import _safe_environment

    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:password@private/db")
    monkeypatch.setenv("GITHUB_PAT", "scope-canary")
    monkeypatch.setenv("INTDOG_SESSION_TOKEN", "session-canary")
    environment = _safe_environment(tmp_path / "data", tmp_path / "project")
    assert environment["PATH"] == "/usr/bin"
    assert environment["DOMAIN_INTEL_DATA_ROOT"] == str(tmp_path / "data")
    assert environment["INTDOG_SEARCH_ROOT"] == str(
        tmp_path / "project" / "DomainIntelSearch")
    assert "DATABASE_URL" not in environment
    assert "GITHUB_PAT" not in environment
    assert "INTDOG_SESSION_TOKEN" not in environment


def test_worker_once_waits_for_claimed_jobs_and_persists_window_and_origin(tmp_path):
    from src.background_worker import BackgroundWorker

    service = IntDogService(tmp_path)
    service.create_industry("AI")
    _schedule(service)
    jobs = FakeJobs(("completed",))
    worker = BackgroundWorker(
        tmp_path, jobs, search_root=Path(tmp_path), project_root=Path(tmp_path),
        readiness=lambda *_: {"ready": True})
    now = datetime(2026, 9, 2, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    summary = worker.run_once(now)
    assert (summary.claimed, summary.completed, summary.paused, summary.failed) == (
        1, 1, 0, 0)
    assert jobs.jobs[0].waited is True
    metadata = jobs.calls[0][1]["metadata"]
    assert metadata["origin"] == "background_worker"
    assert metadata["time_window"] == {
        "start": "2026-09-01T04:00:00+08:00",
        "end": "2026-09-02T09:00:00+08:00",
        "timezone": "Asia/Shanghai",
    }
    saved = service.repo.get_schedule("AI", "daily")
    assert saved["last_period_key"] == "2026-09-02"
    assert saved["runtime_status"] == "completed"


def test_partial_does_not_advance_boundary_and_configuration_pause_has_no_retry(tmp_path):
    from src.background_worker import BackgroundWorker

    service = IntDogService(tmp_path)
    service.create_industry("AI")
    _schedule(service, "weekly")
    jobs = FakeJobs(("partial",))
    now = datetime(2026, 9, 7, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    summary = BackgroundWorker(
        tmp_path, jobs, search_root=tmp_path, project_root=tmp_path,
        readiness=lambda *_: {"ready": True}).run_once(now)
    saved = service.repo.get_schedule("AI", "weekly")
    assert summary.failed == 1
    assert saved["last_period_key"] is None
    assert saved["runtime_status"] == "partial"

    service.repo.update_schedule(
        "AI", "monthly", enabled=True, local_time="08:00", monthday=1,
        timezone_name="Asia/Shanghai", pipeline_mode="generate", provider="openai")
    paused = BackgroundWorker(
        tmp_path, FakeJobs(()), search_root=tmp_path, project_root=tmp_path,
        readiness=lambda *_: {"ready": False, "detail": "credential locked"},
    ).run_once(datetime(2026, 9, 1, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    monthly = service.repo.get_schedule("AI", "monthly")
    assert paused.paused == 1
    assert monthly["runtime_status"] == "paused"
    assert monthly["retry_count"] == 0 and monthly["retry_after"] is None
    assert "credential locked" in monthly["pause_reason"]


def test_retry_exhaustion_pauses_without_advancing_success_boundary(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI")
    _schedule(service)
    with service.repo.transaction() as con:
        con.execute("""UPDATE automation_schedules SET max_retries=2
            WHERE action='daily'""")
    for attempt in range(2):
        assert service.repo.claim_schedule(
            "AI", "daily", "2026-09-02", f"worker:{attempt}",
            period_identity="2026-09-02|Asia/Shanghai|2026-09-02T00:00:00Z")
        service.repo.finish_schedule(
            "AI", "daily", f"worker:{attempt}", success=False,
            outcome="failed", error="network unavailable")
        if attempt == 0:
            with service.repo.transaction() as con:
                con.execute("""UPDATE automation_schedules SET retry_after='2000-01-01T00:00:00+00:00'
                    WHERE action='daily'""")
    saved = service.repo.get_schedule("AI", "daily")
    assert saved["runtime_status"] == "paused"
    assert saved["retry_count"] == 2 and saved["retry_after"] is None
    assert saved["last_period_key"] is None
    assert service.repo.claim_schedule(
        "AI", "daily", "2026-09-02", "worker:later",
        period_identity="2026-09-02|Asia/Shanghai|2026-09-02T00:00:00Z") is False


def _items_for_plan(plan, *, peak=0, justified=False):
    items = []
    for bucket_index, bucket in enumerate(plan["buckets"]):
        count = bucket["target"]
        if bucket_index == 0 and peak:
            count = peak
        for index in range(count):
            item = {
                "title": f"event-{bucket_index}-{index}",
                "url": f"https://publisher{index % 6}.example/{bucket_index}/{index}",
                "published_at": bucket["start"], "date": bucket["start"],
                "source_domain": f"publisher{index % 6}.example",
                "credibility": .9, "review_status": "accepted",
            }
            if justified and bucket_index == 0:
                item["overflow_reason"] = "documented major event peak"
            items.append(item)
    return items


def test_two_and_five_year_plans_use_months_density_and_declared_targets():
    from src.history_backfill import plan_horizon

    end = date(2026, 12, 31)
    two = plan_horizon("biennial", end=end)
    five = plan_horizon("fiveyear", end=end)
    assert (two["target"], two["target_range"], len(two["buckets"])) == (
        4500, [3600, 5400], 24)
    assert (five["target"], five["target_range"], len(five["buckets"])) == (
        12000, [10500, 13500], 60)
    assert sum(row["target"] for row in two["buckets"]) == 4500
    assert sum(row["target"] for row in five["buckets"]) == 12000
    assert all(5 <= row["daily_density"] <= 8 for row in five["buckets"])


def test_history_gate_requires_quality_90_percent_months_and_explains_peaks():
    from src.history_backfill import evaluate_history_items, plan_horizon

    plan = plan_horizon("biennial", end=date(2026, 12, 31))
    concentrated = evaluate_history_items(
        _items_for_plan(plan, peak=700), "biennial", end=date(2026, 12, 31))
    assert concentrated["buckets_covered"] == 24
    assert concentrated["coverage_ratio"] == 1.0
    assert not concentrated["ready"]
    assert concentrated["gaps"][0]["code"] == "unexplained_bucket_concentration"

    justified = evaluate_history_items(
        _items_for_plan(plan, peak=700, justified=True), "biennial",
        end=date(2026, 12, 31))
    assert justified["ready"]
    assert justified["overflow_buckets"][0]["justified"] is True

    low_quality = _items_for_plan(plan)
    for item in low_quality[:800]:
        item["credibility"] = .2
    for item in low_quality[800:1100]:
        item["duplicate"] = True
    sparse = evaluate_history_items(
        low_quality, "biennial", end=date(2026, 12, 31))
    assert sparse["rejected_low_quality"] == 800
    assert sparse["rejected_duplicates"] == 300
    assert not sparse["ready"]
    assert {gap["code"] for gap in sparse["gaps"]} >= {
        "qualified_document_gap", "month_coverage_gap"}
