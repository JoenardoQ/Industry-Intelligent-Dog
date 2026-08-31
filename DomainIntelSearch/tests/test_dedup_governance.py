"""Risk-based contract tests for docs/source-governance.* (CPHSV model)."""

from __future__ import annotations

import tempfile
import unittest

from src.crawlers.adapters import DEFAULT_ADAPTERS
from src.deduplication import collapse_batch, content_fingerprint, plan_history
from src.industry_store import IndustryStore
from src.source_discovery import merge_sources
from src.source_governance import category_target, govern_sources


class DeduplicationContractTests(unittest.TestCase):
    def test_tracking_and_location_do_not_change_content_identity(self):
        abstract = "A" * 100
        left = {"title": "New accelerator released", "abstract": abstract,
                "url": "https://alpha.example/story?utm_source=x"}
        right = {"title": "New accelerator released", "abstract": abstract,
                 "url": "https://mirror.example/copy"}
        self.assertEqual(content_fingerprint(left), content_fingerprint(right))
        kept, audit = collapse_batch([left, right])
        self.assertEqual(len(kept), 1)
        self.assertEqual(audit["reasons"], {"content_fingerprint": 1})
        self.assertEqual(kept[0]["duplicate_count"], 2)

    def test_equal_headlines_from_independent_publishers_remain_corroboration(self):
        items = [
            {"title": "Company announces a chip", "url": "https://a.example/report"},
            {"title": "Company announces a chip", "url": "https://b.example/report"},
        ]
        kept, audit = collapse_batch(items)
        self.assertEqual(len(kept), 2)
        self.assertEqual(audit["duplicates"], 0)

    def test_same_publisher_replay_collapses_but_cross_language_does_not(self):
        items = [
            {"title": "Company announces a chip", "url": "https://a.example/one",
             "date": "2026-08-30"},
            {"title": "Company announces a chip", "url": "https://a.example/two",
             "date": "2026-08-31"},
            {"title": "该公司发布新芯片", "url": "https://a.example/zh",
             "date": "2026-08-31"},
        ]
        kept, audit = collapse_batch(items)
        self.assertEqual(len(kept), 2)
        self.assertEqual(audit["reasons"], {"publisher_exact_title": 1})

    def test_series_parts_and_distant_reissues_are_not_near_title_duplicates(self):
        items = [
            {"id": "one", "title": "大模型微调实践（上）", "url": "https://a.example/1",
             "date": "2026-08-01", "category": "news"},
            {"id": "two", "title": "大模型微调实践（下）", "url": "https://a.example/2",
             "date": "2026-08-01", "category": "news"},
            {"id": "old", "title": "A complete guide to agents",
             "url": "https://a.example/old", "date": "2025-01-01", "category": "news"},
            {"id": "new", "title": "A complete guide to agents",
             "url": "https://a.example/new", "date": "2026-01-01", "category": "news"},
        ]
        self.assertEqual(plan_history(items)["suppressed_links"], 0)

    def test_cross_day_and_cross_category_replays_are_suppressed_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI")
            item = {"title": "One event", "url": "https://example.com/event",
                    "source": "Example"}
            store.save_daily("news", [item], "2026-08-01")
            store.save_daily("news", [item], "2026-08-02")
            store.save_daily("funding", [item], "2026-08-01")
            self.assertEqual(len(store.service.repo.list_documents("AI")), 1)
            self.assertEqual(store.list_daily(date="2026-08-02"), [])
            self.assertEqual(store.list_daily(date="2026-08-01", category="funding"), [])

    def test_history_cleanup_is_auditable_soft_suppression(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI")
            # Import through the repository to emulate legacy data that predates v1 dedup.
            store.service.import_daily("AI", "news", "2026-08-01", [{
                "title": "Repeated report", "url": "https://same.example/a"}])
            store.service.import_daily("AI", "news", "2026-08-02", [{
                "title": "Repeated report", "url": "https://same.example/b"}])
            store.service.import_daily("AI", "news", "2026-08-02", [{
                "title": "Repeated report", "url": "https://independent.example/c"}])
            preview = store.deduplicate_history()
            self.assertEqual(preview["suppressed_links"], 1)
            self.assertFalse(preview["applied"])
            applied = store.deduplicate_history(apply=True)
            self.assertEqual(applied["applied_links"], 1)
            self.assertEqual(len(store.service.repo.list_documents("AI")), 2)
            with store.service.repo.connection() as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM documents").fetchone()[0], 3)
                audit = connection.execute("""SELECT action FROM audit_log
                    WHERE action='deduplicate_history'""").fetchone()
            self.assertIsNotNone(audit)


class SourceGovernanceContractTests(unittest.TestCase):
    @staticmethod
    def _source(index: int, **extra) -> dict:
        return {"name": f"Source {index}", "url": f"https://s{index}.example/feed",
                "tier": "authoritative", "access": "rss",
                "coverage": [f"topic-{index}"], **extra}

    def test_dynamic_boundary_is_clamped_and_complexity_sensitive(self):
        self.assertEqual(category_target("news", 0)["target"], 8)
        self.assertEqual(category_target("news", 12)["target"], 10)
        self.assertEqual(category_target("news", 100)["target"], 11)
        self.assertLessEqual(category_target("news", 100)["target"],
                             category_target("news", 100)["maximum"])

    def test_catalog_is_preserved_while_active_pool_is_bounded(self):
        sources = [self._source(index) for index in range(12)]
        sources.extend([
            {**self._source(99), "name": "Manual authority",
             "monitoring_status": "recommended_manual"},
            {"name": "Redundant endpoint", "url": "https://s0.example/other",
             "tier": "authoritative", "access": "rss", "coverage": ["topic-0"]},
        ])
        governed = govern_sources({"news": sources}, chain_count=0)
        rows = governed["news"]
        audit = governed["source_governance"]["categories"]["news"]
        self.assertEqual(len(rows), 14)
        self.assertEqual(audit["active"], 8)
        self.assertEqual(audit["manual"], 1)
        self.assertGreaterEqual(audit["reserve"], 5)
        self.assertEqual(next(row for row in rows if row["name"] == "Manual authority")
                         ["monitoring_status"], "recommended_manual")

    def test_low_quality_shortage_is_reported_not_padded(self):
        governed = govern_sources({"self_media": [{
            "name": "Weak signal", "url": "https://producthunt.com/posts/x",
            "tier": "signal", "access": "web"}]})
        audit = governed["source_governance"]["categories"]["self_media"]
        self.assertEqual(audit["active"], 0)
        self.assertEqual(audit["shortage"], 2)
        self.assertEqual(audit["stopping_reason"], "insufficient_qualified_sources")

    def test_reserve_and_manual_sources_never_select_an_automatic_adapter(self):
        for status in ("reserve", "recommended_manual", "quarantined"):
            adapter = DEFAULT_ADAPTERS.select({"monitoring_status": status,
                                               "access": "rss"})
            self.assertEqual(adapter.name, "manual")

    def test_governance_and_source_merge_are_idempotent(self):
        base = {"news": [{"name": "A", "url": "https://www.example.com/x?utm_source=a"}]}
        merged = merge_sources(base, {"news": [
            {"name": "A duplicate", "url": "https://example.com/x?utm_source=b"}]})
        self.assertEqual(len(merged["news"]), 1)
        first = govern_sources({"news": [self._source(i) for i in range(10)]})
        second = govern_sources(first)
        first_state = [(row["url"], row["monitoring_status"]) for row in first["news"]]
        second_state = [(row["url"], row["monitoring_status"]) for row in second["news"]]
        self.assertEqual(first_state, second_state)


if __name__ == "__main__":
    unittest.main()
