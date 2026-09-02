"""Risk-based contract tests for docs/source-governance.* (CPHSV model)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from itertools import permutations

from src.crawlers.adapters import DEFAULT_ADAPTERS
from src.deduplication import collapse_batch, content_fingerprint, plan_history
from src.industry_store import IndustryStore
from src.source_discovery import merge_sources
from src.source_governance import category_target, govern_sources
from src.source_review import assess_source_candidate
from src.verification import group_stories, score_group


HUMAN_REVIEW_CATEGORIES = {"blogs", "platforms", "self_media", "news", "finance"}


def _verified(index: int, *, category: str = "official", origin: str = "foreign",
              **extra) -> dict:
    domain = f"s{index}.example"
    item = {
        "name": f"Source {index}",
        "url": f"https://{domain}/feed",
        "category": category,
        "tier": "authoritative",
        "access": "rss",
        "origin": origin,
        "coverage": [f"topic-{index}"],
        "identity_verification": {
            "status": "verified", "evidence_url": f"https://registry.example/{index}",
            "verified_by": "test-reviewer"},
        "ownership_verification": {
            "status": "verified", "owner_cluster": domain,
            "evidence_url": f"https://registry.example/{index}/owner",
            "verified_by": "test-reviewer"},
        "url_verification": {
            "status": "verified", "reachable": True, "status_code": 200,
            "checked_url": f"https://{domain}/feed",
            "verification_origin": "server_guarded"},
    }
    if category in HUMAN_REVIEW_CATEGORIES:
        item["human_review"] = {
            "decision": "active", "actor": "analyst", "reason": "editorial review passed"}
    item.update(extra)
    return item


class DeduplicationContractTests(unittest.TestCase):
    def test_batch_merge_is_permutation_invariant_and_retains_document_provenance(self):
        abstract = "A sufficiently detailed primary report. " * 5
        items = [
            {"id": "doc-a", "source_id": "source-a", "title": "Accelerator launch",
             "abstract": abstract, "url": "https://a.example/story?utm_source=mail"},
            {"id": "doc-b", "source_id": "source-b", "title": "Accelerator launch",
             "abstract": abstract, "url": "https://a.example/story?fbclid=tracking"},
            {"id": "doc-c", "source_id": "source-c", "title": "Accelerator launch",
             "abstract": abstract, "url": "https://mirror.example/repost"},
        ]

        signatures = set()
        for ordered in permutations(items):
            kept, audit = collapse_batch(list(ordered))
            self.assertEqual((audit["input"], audit["kept"], audit["duplicates"]),
                             (3, 1, 2))
            self.assertEqual(kept[0]["duplicate_count"], 3)
            provenance = tuple(sorted(
                (row["document_id"], row["source_id"], row["url"])
                for row in kept[0]["document_provenance"]))
            self.assertEqual({row[0] for row in provenance},
                             {"doc-a", "doc-b", "doc-c"})
            self.assertEqual({row[1] for row in provenance},
                             {"source-a", "source-b", "source-c"})
            signatures.add((kept[0]["url"],
                            tuple(sorted(kept[0]["duplicate_urls"])), provenance,
                            tuple(sorted(audit["reasons"].items()))))
        self.assertEqual(len(signatures), 1)

    def test_reposts_owner_independence_and_cross_language_event_boundaries_are_stable(self):
        reposts = [
            {"id": "wire", "title": "Company opens new chip facility",
             "url": "https://reutersagency.com/report", "date": "2026-08-31"},
            {"id": "syndicated", "title": "Company opens new chip facility",
             "url": "https://portal.example/repost", "date": "2026-08-31",
             "syndicated_from": "https://reuters.com/original"},
        ]
        independent = {
            "id": "independent", "title": "Company opens new chip facility",
            "url": "https://bloomberg.com/report", "date": "2026-08-31",
        }
        signatures = set()
        for ordered in permutations([*reposts, independent]):
            kept, _ = collapse_batch(list(ordered))
            signatures.add(tuple(sorted(
                (row["url"], row.get("duplicate_count", 1)) for row in kept)))
        self.assertEqual(len(signatures), 1)
        self.assertEqual(len(next(iter(signatures))), 2)
        self.assertEqual(score_group(reposts)["source_count"], 1)
        self.assertEqual(score_group([reposts[0], independent])["source_count"], 2)

        cross_language = [
            {"id": "zh", "title": "示例公司宣布建设新晶圆厂", "category": "news",
             "url": "https://cn.example/event", "published_at": "2026-08-31T08:00:00Z",
             "entity_ids": ["example-corp"], "event_keys": ["new-fab"]},
            {"id": "en", "title": "Example Corp announces a new semiconductor fab",
             "category": "news", "url": "https://en.example/event",
             "published_at": "2026-08-31T10:00:00Z",
             "entity_ids": ["example-corp"], "event_keys": ["new-fab"]},
            {"id": "other", "title": "Example Corp reports quarterly earnings",
             "category": "news", "url": "https://en.example/earnings",
             "published_at": "2026-08-31T11:00:00Z",
             "entity_ids": ["example-corp"], "event_keys": ["earnings"]},
        ]
        collapsed, _ = collapse_batch(cross_language)
        self.assertEqual(len(collapsed), 3)
        group_signatures = set()
        for ordered in permutations(cross_language):
            groups = group_stories(list(ordered))
            group_signatures.add(tuple(sorted(
                tuple(sorted(ordered[index]["id"] for index in group))
                for group in groups)))
        self.assertEqual(group_signatures, {
            (("en", "zh"), ("other",)),
        })

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
                "title": "Repeated report", "url": "https://same.example/a",
                "source": "Source A", "source_url": "https://source-a.example/feed"}])
            store.service.import_daily("AI", "news", "2026-08-02", [{
                "title": "Repeated report", "url": "https://same.example/b",
                "source": "Source B", "source_url": "https://source-b.example/feed"}])
            store.service.import_daily("AI", "news", "2026-08-02", [{
                "title": "Repeated report", "url": "https://independent.example/c",
                "source": "Source C", "source_url": "https://source-c.example/feed"}])
            with store.service.repo.connection() as connection:
                duplicate_id = connection.execute(
                    "SELECT id FROM documents WHERE canonical_url='https://same.example/b'"
                ).fetchone()[0]
            claim_id = store.service.repo.upsert_claim(
                "AI", "reports_event", {"title": "Repeated report"})
            evidence_id = store.service.repo.add_evidence(
                claim_id, "supports", document_id=duplicate_id,
                excerpt="retained evidence")
            preview = store.deduplicate_history()
            self.assertEqual(preview["suppressed_links"], 1)
            self.assertFalse(preview["applied"])
            applied = store.deduplicate_history(apply=True)
            self.assertEqual(applied["applied_links"], 1)
            self.assertEqual(len(store.service.repo.list_documents("AI")), 2)
            with store.service.repo.connection() as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM documents").fetchone()[0], 3)
                self.assertEqual(connection.execute(
                    "SELECT COUNT(DISTINCT source_id) FROM documents"
                ).fetchone()[0], 3)
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM source_publishers"
                ).fetchone()[0], 3)
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM evidence WHERE id=?", (evidence_id,)
                ).fetchone()[0], 1)
                audit = connection.execute("""SELECT action FROM audit_log
                    WHERE action='deduplicate_history'""").fetchone()
            self.assertIsNotNone(audit)


class SourceGovernanceContractTests(unittest.TestCase):
    @staticmethod
    def _source(index: int, **extra) -> dict:
        return _verified(index, **extra)

    def test_every_category_has_explicit_8_to_10_portfolio_boundaries(self):
        categories = ["official", "associations", "blogs", "platforms", "self_media",
                      "news", "journals", "financials", "finance"]
        for category in categories:
            with self.subTest(category=category):
                self.assertEqual(category_target(category), {
                    "minimum": 8, "target": 10, "maximum": 10, "chain_count": 0})
                for count, active, reserve, shortage in (
                        (7, 7, 0, 1), (8, 8, 0, 0),
                        (10, 10, 0, 0), (11, 10, 1, 0)):
                    governed = govern_sources({
                        category: [_verified(index, category=category)
                                   for index in range(count)]})
                    audit = governed["source_governance"]["categories"][category]
                    self.assertEqual(
                        (audit["active"], audit["reserve"], audit["shortage"]),
                        (active, reserve, shortage))

    def test_catalog_is_preserved_while_active_pool_is_bounded(self):
        sources = [self._source(index) for index in range(12)]
        sources.extend([
            {**self._source(99), "name": "Manual authority",
             "added_manually": True, "human_review": None},
            {"name": "Redundant endpoint", "url": "https://s0.example/other",
             **{key: value for key, value in self._source(0).items()
                if key not in {"name", "url", "coverage"}},
             "coverage": ["topic-0"]},
        ])
        governed = govern_sources({"official": sources}, chain_count=0)
        rows = governed["official"]
        audit = governed["source_governance"]["categories"]["official"]
        self.assertEqual(len(rows), 14)
        self.assertEqual(audit["active"], 10)
        self.assertEqual(audit["manual"], 1)
        self.assertEqual(audit["reserve"], 3)
        self.assertEqual(next(row for row in rows if row["name"] == "Manual authority")
                         ["monitoring_status"], "recommended_manual")

    def test_active_pool_prefers_a_source_that_adds_topic_coverage(self):
        common = [{**_verified(index, category="official"),
                   "name": f"A{index:02d}", "coverage": ["shared-topic"]}
                  for index in range(10)]
        frontier = {**_verified(99, category="official"),
                    "name": "Z frontier", "coverage": ["new-frontier-topic"]}

        governed = govern_sources({"official": [*common, frontier]})

        selected = next(row for row in governed["official"]
                        if row["name"] == "Z frontier")
        assert selected["monitoring_status"] == "active"
        assert "topic" in selected["coverage_gain"]

    def test_low_quality_shortage_is_reported_not_padded(self):
        governed = govern_sources({"self_media": [{
            "name": "Weak signal", "url": "https://producthunt.com/posts/x",
            "tier": "signal", "access": "web"}]})
        audit = governed["source_governance"]["categories"]["self_media"]
        self.assertEqual(audit["active"], 0)
        self.assertEqual(audit["shortage"], 8)
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
        first = govern_sources({"official": [self._source(i) for i in range(10)]})
        second = govern_sources(first)
        first_state = [(row["url"], row["monitoring_status"]) for row in first["official"]]
        second_state = [(row["url"], row["monitoring_status"]) for row in second["official"]]
        self.assertEqual(first_state, second_state)

    def test_official_auto_activation_requires_identity_ownership_and_url_evidence(self):
        complete = assess_source_candidate(
            _verified(1), category="official", now=date(2026, 9, 1))
        hint_only = assess_source_candidate({
            "name": "Government hint", "url": "https://www.gov.cn/policy",
            "tier": "primary", "access": "web"},
            category="official", now=date(2026, 9, 1))

        self.assertEqual(complete["decision"], "active")
        self.assertEqual(complete["reason"], "verified_primary_source")
        self.assertEqual(hint_only["decision"], "manual_review")
        self.assertEqual(hint_only["reason"], "verification_incomplete")
        self.assertTrue(hint_only["identity_hint"])
        self.assertFalse(hint_only["verification"]["identity_passed"])
        for result in (complete, hint_only):
            self.assertEqual(set(result) & {
                "score_components", "decision", "reason", "review_due_at"},
                {"score_components", "decision", "reason", "review_due_at"})

    def test_media_and_self_media_always_require_human_review_before_activation(self):
        for category in ("news", "self_media"):
            with self.subTest(category=category):
                result = assess_source_candidate(
                    _verified(2, category=category, human_review=None),
                    category=category, now=date(2026, 9, 1))
                self.assertEqual(result["decision"], "manual_review")
                self.assertEqual(result["reason"], "human_review_required")

    def test_same_owner_ownership_change_content_farm_and_zero_value_are_explicit(self):
        cases = [
            (_verified(3), {"duplicate_owner": True}, "reserve", "same_owner_duplicate"),
            (_verified(4, observed_owner_cluster="new-owner"), {},
             "manual_review", "ownership_changed"),
            (_verified(5, content_farm=True), {}, "rejected", "content_farm"),
            (_verified(6, days_observed=180, useful_output_count=0,
                       marginal_value_30d=0), {}, "reserve", "long_term_zero_value"),
        ]
        for item, context, decision, reason in cases:
            with self.subTest(reason=reason):
                result = assess_source_candidate(
                    item, category="official", context=context,
                    now=date(2026, 9, 1))
                self.assertEqual((result["decision"], result["reason"]),
                                 (decision, reason))

    def test_manual_addition_waits_for_review_and_china_gap_wins_equal_quality_tie(self):
        manual = assess_source_candidate(
            _verified(7, added_manually=True, human_review=None),
            category="official", now=date(2026, 9, 1))
        self.assertEqual((manual["decision"], manual["reason"]),
                         ("manual_review", "manual_addition_requires_review"))

        sources = [_verified(index, category="official") for index in range(10)]
        sources.append(_verified(
            99, category="official", origin="china", fills_china_gap=True))
        governed = govern_sources({"official": sources})
        china = next(item for item in governed["official"] if item["name"] == "Source 99")
        self.assertEqual(china["monitoring_status"], "active")
        self.assertGreater(china["score_components"]["china_gap"], 0)

    def test_periodic_review_dates_are_deterministic_by_decision(self):
        now = date(2026, 9, 1)
        active = assess_source_candidate(_verified(8), category="official", now=now)
        manual = assess_source_candidate(
            _verified(9, category="news", human_review=None), category="news", now=now)
        reserve = assess_source_candidate(
            _verified(10), category="official", context={"duplicate_owner": True}, now=now)
        rejected = assess_source_candidate(
            _verified(11, content_farm=True), category="official", now=now)
        self.assertEqual(active["review_due_at"], "2026-11-30")
        self.assertEqual(manual["review_due_at"], "2026-09-01")
        self.assertEqual(reserve["review_due_at"], "2026-10-01")
        self.assertEqual(rejected["review_due_at"], "2027-02-28")


if __name__ == "__main__":
    unittest.main()
