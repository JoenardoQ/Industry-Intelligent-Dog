from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOT = PROJECT_ROOT / "DomainIntelSearch"
for root in (PROJECT_ROOT, SEARCH_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from DomainIntelWeb.api.automation import AutomationScheduler, schedule_moment
from DomainIntelWeb.api.security import evaluate_request
from intdog_core import IntDogService


class FakeJobs:
    def __init__(self):
        self.calls = []

    def start(self, command, **kwargs):
        self.calls.append((command, kwargs))
        callback = kwargs.get("on_finish")
        if callback:
            callback(SimpleNamespace(status="completed", error=""))
        return SimpleNamespace(run_id=f"run-{len(self.calls)}")


def test_schedule_moment_and_exactly_once_claim(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    service.repo.update_schedule(
        "AI", "daily", enabled=True, local_time="08:00", timezone_name="Asia/Shanghai")
    now = datetime(2026, 8, 31, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    jobs = FakeJobs()
    scheduler = AutomationScheduler(
        tmp_path, jobs, search_root=tmp_path, project_root=tmp_path, now=lambda: now)

    row = service.repo.get_schedule("AI", "daily")
    key, due, following = schedule_moment(row, now)
    assert key == "2026-08-31"
    assert due.hour == 8 and following.date().isoformat() == "2026-09-01"
    assert scheduler.tick() == 1
    assert scheduler.tick() == 0
    assert len(jobs.calls) == 1
    assert jobs.calls[0][1]["env"]["INTDOG_DISABLE_EMAIL"] == "1"
    saved = service.repo.get_schedule("AI", "daily")
    assert saved["last_period_key"] == "2026-08-31"
    assert saved["last_success_at"]


@pytest.mark.parametrize(("action", "now", "expected"), [
    ("weekly", datetime(2026, 8, 31, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
     "2026-W36"),
    ("monthly", datetime(2026, 9, 1, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
     "2026-09"),
    ("quarterly", datetime(2026, 10, 1, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
     "2026-Q4"),
])
def test_all_period_schedule_keys(action, now, expected, tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    service.repo.update_schedule(
        "AI", action, enabled=True, local_time="08:00", weekday=0,
        monthday=1, timezone_name="Asia/Shanghai")
    key, _, following = schedule_moment(service.repo.get_schedule("AI", action), now)
    assert key == expected
    assert following > now


def test_unready_model_schedule_does_not_enter_job_queue(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    service.repo.update_schedule("AI", "weekly", enabled=False,
                                 local_time="08:00", pipeline_mode="generate",
                                 provider="claude")
    jobs = FakeJobs()
    scheduler = AutomationScheduler(
        tmp_path, jobs, search_root=tmp_path, project_root=tmp_path,
        readiness=lambda *_: {"ready": False, "detail": "未登录"})
    with pytest.raises(ValueError, match="未就绪"):
        scheduler.run_now("AI", "weekly")
    assert jobs.calls == []


def test_schedule_inherits_shared_provider_until_explicitly_overridden(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    service.repo.put_workflow_settings(None, "*", {
        "provider": "claude", "execution_mode": "direct"})
    service.repo.update_schedule(
        "AI", "weekly", enabled=False, local_time="08:00",
        pipeline_mode="generate")
    jobs = FakeJobs()
    checked = []
    scheduler = AutomationScheduler(
        tmp_path, jobs, search_root=tmp_path, project_root=tmp_path,
        readiness=lambda provider, *_: checked.append(provider) or {"ready": True})

    scheduler.run_now("AI", "weekly")

    assert service.repo.get_schedule("AI", "weekly")["provider"] == ""
    assert checked == ["claude"]
    assert "claude" in jobs.calls[0][0]


def test_coverage_frontier_deduplicates_queries_and_tracks_yield(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("CHIPS", "芯片")
    dimensions = {
        "region": "china", "subdomain": "equipment", "chain_stage": "光刻",
        "entity_type": "company", "source_type": "official",
        "event_type": "policy", "time_horizon": "12m",
    }
    cell_id = service.repo.upsert_coverage_cell(
        "CHIPS", dimensions, priority=90, rationale="国产设备覆盖缺口")
    first = service.repo.record_coverage_attempt(
        "CHIPS", cell_id, query="中国 光刻设备 官方 政策", status="completed",
        source_yield=2, entity_yield=3, evidence=[{"url": "https://example.cn"}])
    second = service.repo.record_coverage_attempt(
        "CHIPS", cell_id, query="中国 光刻设备 官方 政策", status="stopped",
        source_yield=1, entity_yield=0, stopping_reason="边际新增低")

    assert first == second
    cell = service.repo.list_coverage("CHIPS")[0]
    assert cell["attempts"] == 1
    assert cell["source_yield"] == 1
    assert service.repo.coverage_attempts(cell_id)[0]["stopping_reason"] == "边际新增低"


def test_story_detail_counts_independent_publishers_and_audits_split(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    documents = []
    for index in range(3):
        documents.append(service.repo.upsert_document("AI", "news", "2026-08-31", {
            "title": f"Model event {index}", "url": f"https://news{index}.example/item",
        }))
    story_id = service.repo.save_story_groups("AI", [{
        "title": "Model event", "documents": [
            {"document_id": documents[0], "publisher_cluster": "publisher-a"},
            {"document_id": documents[1], "publisher_cluster": "publisher-a"},
            {"document_id": documents[2], "publisher_cluster": "publisher-b"},
        ],
    }], "fixture-v1")[0]
    detail = service.repo.story_detail("AI", story_id)
    assert detail["publisher_count"] == 2
    assert detail["corroborated"] is True

    created = service.repo.split_story(
        "AI", story_id, [documents[2]], "Separated event", actor="test")
    assert len(service.repo.story_detail("AI", created)["documents"]) == 1
    assert service.repo.story_detail("AI", story_id)["reviews"][0]["action"] == "split"
    service.repo.save_story_groups("AI", [{
        "title": "Automatic regroup attempt",
        "documents": [{"document_id": documents[2],
                       "publisher_cluster": "publisher-b"}],
    }], "fixture-v2")
    assert [item["id"] for item in service.repo.list_stories("AI") if
            any(doc["id"] == documents[2] for doc in
                service.repo.story_detail("AI", item["id"])["documents"])] == [created]


def test_trash_industry_and_daily_restore_without_silent_overwrite(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    service.import_daily("AI", "news", "2026-08-31", [{
        "title": "Recoverable", "url": "https://news.example/recoverable",
    }])
    assert service.delete_daily("AI", [("2026-08-31", "news",
                                         "https://news.example/recoverable")]) == 1
    daily = next(item for item in service.list_trash() if item["kind"] == "daily")
    result = service.restore_trash(daily["id"])
    assert result == {"kind": "daily", "folder": "AI", "restored": 1, "skipped": 0}
    assert service.repo.list_documents("AI")[0]["title"] == "Recoverable"

    archived = service.archive_industry("AI")
    item = next(item for item in service.list_trash() if item["kind"] == "industry")
    assert item["id"] == archived.name
    assert service.restore_trash(item["id"])["folder"] == "AI"
    assert service.repo.list_industries()[0]["folder"] == "AI"


def test_local_session_rejects_foreign_origin_and_missing_capability():
    request = dict(method="POST", host="127.0.0.1",
                   origin="http://127.0.0.1:8765", capability="correct-secret")
    assert evaluate_request(**request, supplied="") == (
        401, "桌面会话凭证缺失或已失效")
    assert evaluate_request(**request, supplied="wrong")[0] == 401
    assert evaluate_request(**{**request, "origin": "https://evil.example"},
                            supplied="correct-secret")[0] == 403
    assert evaluate_request(**{**request, "host": "evil.example"},
                            supplied="correct-secret")[0] == 421
    assert evaluate_request(**request, supplied="correct-secret") is None
