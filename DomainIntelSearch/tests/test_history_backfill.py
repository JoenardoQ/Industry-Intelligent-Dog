from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from src.history_backfill import POLICIES, backfill_history, evaluate_history
from src.industry_store import IndustryStore
from src.report_generation import _context
from intdog_core.source_trust import publisher_key, publisher_profile


def _store(root: Path) -> IndustryStore:
    return IndustryStore(root, "AI", "Artificial Intelligence")


def test_weekly_backfill_is_time_stratified_admitted_and_resumable():
    with tempfile.TemporaryDirectory() as temp:
        store = _store(Path(temp))
        calls = []

        def gdelt(_session, _query, start, _end, _limit):
            calls.append(start.isoformat())
            return [{"title": f"event {start}", "url": f"https://p{start.day}.test/{start}",
                     "date": start.isoformat(), "published_at": start.isoformat(),
                     "source": f"p{start.day}.test", "source_domain": f"p{start.day}.test",
                     "category": "news", "history_provider": "fake"}]

        result = backfill_history(
            {"domain": {"name_en": "Artificial Intelligence", "keywords": ["AI"]}},
            store, "weekly", target=7, session=object(), gdelt_fetch=gdelt,
            openalex_fetch=lambda *_args: [],
        )
        assert result["ready"]
        assert result["admitted_total"] == 7
        assert result["buckets_covered"] == 7
        assert len(calls) == 7
        backfill_history(
            {"domain": {"name_en": "Artificial Intelligence", "keywords": ["AI"]}},
            store, "weekly", target=7, session=object(),
            gdelt_fetch=lambda *_args: (_ for _ in ()).throw(AssertionError("reran bucket")),
            openalex_fetch=lambda *_args: [],
        )


def test_evaluation_rejects_large_count_concentrated_in_one_time_bucket():
    with tempfile.TemporaryDirectory() as temp:
        store = _store(Path(temp))
        today = date.today().isoformat()
        store.save_daily("news", [{"title": f"row {index}",
            "url": f"https://publisher{index % 6}.test/{index}",
            "date": today, "published_at": today} for index in range(100)], date=today)
        result = evaluate_history(store, "weekly")
        assert result["admitted_total"] >= result["required_total"]
        assert result["buckets_covered"] < result["required_buckets"]
        assert not result["ready"]


def test_report_context_samples_across_months_not_only_recent_items():
    with tempfile.TemporaryDirectory() as temp:
        store = _store(Path(temp))
        for month in range(1, 7):
            day = f"2026-{month:02d}-15"
            store.save_daily("news", [{"title": f"month-{month}",
                "url": f"https://m{month}.test/item", "date": day,
                "published_at": day, "credibility": 0.8}], date=day)
        context = _context(store, days=365, max_items=6, limit=100_000)
        for month in range(1, 7):
            assert f"month-{month}" in context


def test_policy_targets_match_documented_horizons():
    assert {name: policy.target for name, policy in POLICIES.items()} == {
        "weekly": 28, "monthly": 120, "quarterly": 360,
        "semiannual": 720, "biennial": 3000, "fiveyear": 8000,
    }


def test_news_fallback_fills_bucket_when_gdelt_is_empty():
    with tempfile.TemporaryDirectory() as temp:
        store = _store(Path(temp))
        result = backfill_history(
            {"domain": {"name_en": "Artificial Intelligence", "keywords": ["AI"]}},
            store, "weekly", target=7, max_buckets=1, session=object(),
            gdelt_fetch=lambda *_args: [], openalex_fetch=lambda *_args: [],
            google_fetch=lambda _session, _query, start, _end, _limit: [{
                "title": "indexed event", "url": "https://indexed.test/event",
                "date": start.isoformat(), "published_at": start.isoformat(),
                "source": "Indexed Publisher", "source_domain": "indexed.test",
                "category": "news", "history_provider": "google_news_rss",
            }],
        )
        assert result["admitted_total"] == 1
        rows = store.list_daily_range(days=7)
        assert rows[0]["history_provider"] == "google_news_rss"


def test_empty_bucket_remains_pending_for_next_resume():
    with tempfile.TemporaryDirectory() as temp:
        store = _store(Path(temp)); calls = []
        common = {
            "config": {"domain": {"name_en": "Artificial Intelligence"}},
            "store": store, "horizon": "weekly", "target": 7,
            "max_buckets": 1, "session": object(),
            "gdelt_fetch": lambda *_args: [], "openalex_fetch": lambda *_args: [],
        }
        backfill_history(**common, google_fetch=lambda *_args: [])

        def recovered(_session, _query, start, _end, _limit):
            calls.append(start)
            return [{"title": "recovered", "url": "https://recover.test/1",
                     "date": start.isoformat(), "published_at": start.isoformat(),
                     "source": "Recovery", "source_domain": "recover.test"}]

        backfill_history(**common, google_fetch=recovered)
        assert len(calls) == 1


def test_google_news_uses_indexed_publisher_without_granting_authority():
    item = {"url": "https://news.google.com/rss/articles/token",
            "source": "Example Publisher", "source_domain": "Example Publisher",
            "history_provider": "google_news_rss"}
    assert publisher_key(item) == "indexed:example publisher"
    profile = publisher_profile(item)
    assert profile["owner_cluster"] == "indexed:example publisher"
    assert profile["verification_status"] == "unverified"
    assert profile["quality"] == 0.50
