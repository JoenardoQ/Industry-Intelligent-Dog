from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Collection modules treat feedparser as an install-time dependency.  Core
# tests do not perform network parsing, so a tiny import stub keeps them
# runnable in a minimal checkout.
sys.modules.setdefault("feedparser", types.SimpleNamespace(parse=lambda value: value))

from src.agents.base import AgentContext
from src.industry_store import IndustryStore
from src.profiles import apply_profile, find_profile
from src.schema import IIOSRecord
from src.source_discovery import balance_source_origins, seed_sources
from src.research_bootstrap import (audit_chains, audit_entities, audit_sources,
                                    build_tasks, normalize_entities, prepare_bootstrap)
from src.verification import group_stories, score_group, verify_store_daily
from src.crawlers.periodic_crawlers import _matches
from src.crawlers.adapters import (DEFAULT_ADAPTERS, FeedAdapter, ManualAdapter,
                                   bounded_backoff)
from src.scheduler import PeriodicScheduler
from src.services.task_executor import _safe_output
from src.services.codex_cli_service import CodexCLIService, windows_to_wsl
from src.services.llm_service import LLMConfigurationError, LLMService
from src import mcp_server
from src.report_generation import _safe_output as _safe_report_output, generate_periodic
from src.research_bootstrap import _FeedLinkParser
from src.landscape import build_landscape


class CoreContractTests(unittest.TestCase):
    def test_source_adapter_selection_and_backoff_are_explicit_and_bounded(self):
        self.assertIsInstance(DEFAULT_ADAPTERS.select({"access": "rss"}), FeedAdapter)
        self.assertIsInstance(DEFAULT_ADAPTERS.select({
            "access": "web", "monitoring_status": "recommended_manual"}), ManualAdapter)
        self.assertEqual(DEFAULT_ADAPTERS.select({"note": "maybe RSS"}).name,
                         "unconfigured")
        self.assertEqual(bounded_backoff(1), 60)
        self.assertEqual(bounded_backoff(99), 21_600)

    def test_three_representative_sources_per_adapter_class_are_explicit(self):
        primary = [
            {"name": "SEC filings", "access": "api"},
            {"name": "Crossref", "access": "api"},
            {"name": "GitHub", "access": "api"},
        ]
        feeds = [
            {"name": "Authority feed", "access": "rss"},
            {"name": "Journal feed", "feed_url": "https://example.invalid/journal.xml"},
            {"name": "Media feed", "rss_url": "https://example.invalid/media.xml"},
        ]
        manual = [
            {"name": "Paywalled database", "access": "manual"},
            {"name": "Official account", "monitoring_status": "recommended_manual"},
            {"name": "Conference portal", "monitoring_status": "manual"},
        ]
        self.assertEqual([DEFAULT_ADAPTERS.select(item).name for item in primary],
                         ["api"] * 3)
        self.assertEqual([DEFAULT_ADAPTERS.select(item).name for item in feeds],
                         ["feed"] * 3)
        self.assertEqual([DEFAULT_ADAPTERS.select(item).name for item in manual],
                         ["manual"] * 3)

    def test_feed_adapter_never_turns_failure_into_empty_success(self):
        result = FeedAdapter().collect(
            {"health": {"consecutive_failures": 2}},
            lambda source: (_ for _ in ()).throw(TimeoutError("offline")))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.items, ())
        self.assertEqual(result.error_code, "timeouterror")
        self.assertIsNotNone(result.retry_after)

    def test_cross_language_story_merge_requires_canonical_entity_and_time(self):
        items = [
            {"title": "英伟达发布新一代加速器", "category": "news",
             "entity_ids": ["company:nvidia"], "event_key": "launch:accelerator-x",
             "date": "2026-08-30"},
            {"title": "NVIDIA unveils its next accelerator", "category": "news",
             "entity_ids": ["company:nvidia"], "event_key": "launch:accelerator-x",
             "date": "2026-08-31"},
            {"title": "NVIDIA updates software licensing", "category": "news",
             "entity_ids": ["company:nvidia"], "event_key": "policy:software-license",
             "date": "2026-08-30"},
        ]
        groups = sorted((sorted(group) for group in group_stories(items)), key=lambda x: x[0])
        self.assertEqual(groups, [[0, 1], [2]])

    def test_versioned_story_corpus_reports_precision_and_recall(self):
        fixture = Path(__file__).parent / "fixtures" / "story-clustering-v1.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        items = payload["items"]
        predicted = group_stories(items)
        predicted_pairs = {
            tuple(sorted((items[left]["id"], items[right]["id"])))
            for group in predicted for pos, left in enumerate(group)
            for right in group[pos + 1:]
        }
        truth_pairs = {
            tuple(sorted((left["id"], right["id"])))
            for pos, left in enumerate(items) for right in items[pos + 1:]
            if left["story"] == right["story"]
        }
        true_positive = len(predicted_pairs & truth_pairs)
        precision = true_positive / len(predicted_pairs) if predicted_pairs else 1.0
        recall = true_positive / len(truth_pairs) if truth_pairs else 1.0
        self.assertGreaterEqual(precision, payload["acceptance"]["min_precision"])
        self.assertGreaterEqual(recall, payload["acceptance"]["min_recall"])

    def test_profile_agents_share_canonical_industry_root(self):
        profile = find_profile("ai")
        with tempfile.TemporaryDirectory() as temp:
            cfg = apply_profile({"data_layer": {"root": temp}, "output": {}}, profile)
            ctx = AgentContext.from_config(cfg)
            self.assertEqual(ctx.industry_root, Path(temp) / "AI")
            self.assertEqual(ctx.industry_dir, Path(temp) / "AI" / "one_time" / "research")

    def test_profile_exposes_value_chain_template(self):
        profile = find_profile("semiconductor")
        cfg = apply_profile({"domain": {}, "academic": {}, "news": {}}, profile)
        self.assertEqual(cfg["_profile"]["value_chain_template"], "半导体")

    def test_ai_profile_includes_verified_domestic_feeds(self):
        profile = find_profile("ai")
        cfg = apply_profile({"domain": {}, "academic": {}, "news": {}}, profile)
        feeds = cfg["news"]["rss_feeds"]["general"]
        self.assertGreaterEqual(sum(feed.get("origin") == "china" for feed in feeds), 3)

    def test_scheduler_excludes_manual_recommendations_from_feeds(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(Path(temp), "AI", "人工智能")
            store.save_sources({"news": [
                {"name": "manual", "url": "https://manual.example/feed",
                 "rss_url": "https://manual.example/feed",
                 "monitoring_status": "recommended_manual"},
                {"name": "active", "url": "https://active.example/",
                 "rss_url": "https://active.example/feed", "origin": "china",
                 "monitoring_status": "active"},
            ]})
            # This unit isolates scheduler admission from source-governance review:
            # only an explicitly active catalog row may enter collection.
            with patch.object(store, "get_sources", return_value={"news": [
                {"name": "manual", "url": "https://manual.example/feed",
                 "rss_url": "https://manual.example/feed",
                 "monitoring_status": "recommended_manual"},
                {"name": "active", "url": "https://active.example/",
                 "rss_url": "https://active.example/feed", "origin": "china",
                 "monitoring_status": "active"},
            ]}):
                cfg = PeriodicScheduler._with_discovered_feeds({"news": {}}, store)
            urls = [feed["url"] for feed in cfg["news"]["rss_feeds"]["general"]]
            self.assertIn("https://active.example/feed", urls)
            self.assertNotIn("https://manual.example/feed", urls)

    def test_daily_items_are_validated_enriched_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI")
            store.save_daily("news", [
                {"title": "A", "url": "https://example.com/x?utm_source=a", "source": "X"},
                {"title": "A copy", "url": "https://www.example.com/x?utm_source=b", "source": "X"},
                {"title": "invalid", "url": ""},
            ], "2026-08-01")
            items = store.list_daily(date="2026-08-01")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["url"], "https://example.com/x")
            self.assertIn("content_hash", items[0])
            self.assertIn("retrieved_at", items[0])

    def test_verification_separates_source_quality_and_corroboration(self):
        official = {"title": "Policy", "url": "https://www.gov.cn/policy/1",
                    "source": "中国政府网", "category": "news"}
        official_score = score_group([official])
        self.assertEqual(official_score["evidence_type"], "official_primary")
        self.assertFalse(official_score["corroborated"])
        same_publisher = dict(official, url="https://www.gov.cn/policy/2")
        self.assertEqual(score_group([official, same_publisher])["source_count"], 1)

    def test_publisher_trust_rejects_name_spoofing_and_collapses_syndication(self):
        spoof = {"title": "x", "url": "https://random.example/x",
                 "source": "某官方权威媒体", "tier": "primary", "category": "news"}
        self.assertEqual(score_group([spoof])["evidence_type"], "secondary_source")
        copies = [
            {"title": "same event", "url": "https://site-a.example/a",
             "syndicated_from": "https://reuters.com/original", "category": "news"},
            {"title": "same event", "url": "https://site-b.example/b",
             "syndicated_from": "https://reutersagency.com/original", "category": "news"},
        ]
        self.assertEqual(score_group(copies)["source_count"], 1)

    def test_cross_day_verification_uses_requested_window(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI")
            base = {"title": "Company launches a new AI chip platform",
                    "abstract": "", "category": "news"}
            store.save_daily("news", [{**base, "url": "https://reuters.com/a",
                                         "source": "Reuters"}], "2026-08-01")
            store.save_daily("news", [{**base, "url": "https://ft.com/b",
                                         "source": "FT"}], "2026-08-02")
            stats = verify_store_daily(store, date="2026-08-02", days=3)
            self.assertEqual(stats["verified_items"], 2)

    def test_verification_window_does_not_supersede_historical_events(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI")
            store.save_daily("news", [{"title": "First historical event",
                "url": "https://www.gov.cn/first", "source": "Government"}],
                "2026-08-01")
            verify_store_daily(store, date="2026-08-01")
            store.save_daily("news", [{"title": "Second historical event",
                "url": "https://www.gov.cn/second", "source": "Government"}],
                "2026-08-10")
            verify_store_daily(store, date="2026-08-10")
            with store.service.repo.connection() as con:
                active = con.execute("""SELECT COUNT(*) FROM claims
                    WHERE predicate='reports_event' AND superseded_at IS NULL""").fetchone()[0]
            self.assertEqual(active, 2)

    def test_daily_collection_reports_failed_and_partial_outcomes(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI")
            failures = [patch("src.scheduler.NewsAggregator.collect", side_effect=OSError("n")),
                        patch("src.scheduler.AcademicAggregator.collect", side_effect=OSError("p")),
                        patch("src.scheduler.pc.fetch_github", side_effect=OSError("g")),
                        patch("src.scheduler.pc.fetch_funding", side_effect=OSError("f")),
                        patch("src.scheduler.pc.fetch_hiring", side_effect=OSError("h")),
                        patch("src.scheduler.pc.fetch_ceo", side_effect=OSError("c"))]
            for item in failures:
                item.start(); self.addCleanup(item.stop)
            config = {"news": {}, "domain": {}, "output": {"data_dir": temp}}
            failed = PeriodicScheduler(config, store).run_daily()
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(set(failed["failed_categories"]),
                             {"news", "papers", "github", "funding", "hiring", "ceo"})
            failures[0].stop()
            with patch("src.scheduler.NewsAggregator.collect", return_value=[]):
                partial = PeriodicScheduler(config, store).run_daily()
            self.assertEqual(partial["status"], "partial")
            self.assertEqual(partial["successful_categories"], ["news"])

    def test_api_credentials_are_environment_only_and_remote_base_requires_tls(self):
        config = {"llm": {"provider": "openai", "model": "test",
                          "api_base": "https://api.openai.com/v1",
                          "api_key": "stored-secret"}}
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(LLMConfigurationError):
                LLMService(config)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "runtime-secret",
                                        "INTDOG_LLM_API_BASE": "http://remote.example/v1"},
                        clear=True):
            with self.assertRaisesRegex(LLMConfigurationError, "HTTPS"):
                LLMService(config)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "runtime-secret",
                                        "INTDOG_LLM_API_BASE": "http://127.0.0.1:8080/v1"},
                        clear=True):
            self.assertEqual(LLMService(config).api_key, "runtime-secret")

    def test_short_ascii_keyword_is_a_word(self):
        self.assertEqual(_matches("said the company", ["AI"]), [])
        self.assertEqual(_matches("new AI model", ["AI"]), ["AI"])

    def test_domain_specific_sources_do_not_default_to_semiconductors(self):
        sources = seed_sources("生物医药", "Biomedicine", {"id": "biomed"})
        names = {entry["name"] for values in sources.values() if isinstance(values, list)
                 for entry in values}
        self.assertIn("PubMed", names)
        self.assertNotIn("Semiconductor Engineering", names)

    def test_quarterly_task_accepts_company_objects(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI", "人工智能")
            cfg = {"domain": {"tracked_companies": [{"name": "公司A", "symbol": "1"}]}}
            result = PeriodicScheduler(cfg, store).run_quarterly()
            payload = json.loads(Path(result["quarterly"]).read_text(encoding="utf-8"))
            self.assertIn("公司A", payload["task"]["prompt"])

    def test_schema_rejects_invalid_confidence(self):
        with self.assertRaises(ValueError):
            IIOSRecord(type="news", title="x", confidence=1.1)

    def test_task_output_cannot_escape_industry(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                _safe_output({"output_file": "../../outside.md"}, Path(temp), "fallback")

    def test_mcp_rejects_industry_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            mcp_server.DATA_ROOT = Path(temp)
            with self.assertRaises(ValueError):
                mcp_server._industry_dir("../secret")

    def test_bootstrap_is_source_first_and_blocks_downstream(self):
        tasks = build_tasks("量子计算")
        self.assertEqual([task["stage"] for task in tasks],
                         ["sources", "value_chain", "entities"])
        self.assertEqual(tasks[1]["depends_on"], ["sources:passed"])
        self.assertEqual(tasks[2]["depends_on"], ["value_chain:passed"])
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "Quantum", "量子计算")
            status = prepare_bootstrap(store)
            self.assertEqual(status["stages"]["value_chain"]["state"], "blocked")
            self.assertTrue(Path(status["task_file"]).exists())

    def test_quality_gates_reject_uncited_chain_and_thin_entities(self):
        chains = [{"name": str(i), "inputs": [], "outputs": [], "references": []}
                  for i in range(5)]
        self.assertFalse(audit_chains(chains)["passed"])
        self.assertFalse(audit_entities([], chains)["passed"])

    def test_source_gate_records_scope_not_fact_verification(self):
        audit = audit_sources(seed_sources("人工智能", "AI", {"id": "ai"}))
        self.assertEqual(audit["verification_scope"], "structure_and_provenance")

    def test_source_gate_uses_live_reachability_when_present(self):
        sources = seed_sources("人工智能", "AI", {"id": "ai"})
        for values in sources.values():
            if isinstance(values, list):
                for item in values:
                    item["access_check"] = {"reachable": False}
        audit = audit_sources(sources)
        self.assertFalse(audit["checks"]["live_reachability"])

    def test_source_gate_treats_china_foreign_imbalance_as_advisory(self):
        sources = seed_sources("人工智能", "AI", {"id": "ai"})
        audit = audit_sources(sources)
        self.assertNotIn("china_foreign_balance", audit["checks"])
        self.assertEqual(audit["balance_policy"], "advisory_domestic_recall_preferred")

    def test_source_balancer_preserves_sources_and_only_annotates(self):
        sources = {key: [] for key in ("official", "associations", "blogs", "platforms",
                                       "self_media", "news", "journals", "financials", "finance")}
        for category in sources:
            sources[category] = [
                {"url": f"https://cn-{category}-{i}.cn", "origin": "china", "tier": "primary"}
                for i in range(2)
            ] + [
                {"url": f"https://foreign-{category}-{i}.com", "origin": "international",
                 "tier": "signal"}
                for i in range(4)
            ]
        balanced = balance_source_origins(sources)
        audit = audit_sources(balanced)
        self.assertEqual(audit["foreign_per_china"], 2.0)
        self.assertTrue(all(len(balanced[key]) == 6 for key in sources))
        self.assertFalse(balanced["origin_balance"]["hard_limit"])

    def test_codex_executor_is_ephemeral_read_only_and_search_enabled(self):
        service = CodexCLIService.__new__(CodexCLIService)
        service.workspace = Path("/tmp/intdog")
        service.model = ""
        service._windows = False
        service.executable = "/usr/bin/codex"
        service.codex_command = "codex"
        service.codex_home = ""
        command = service.build_command(Path("/tmp/intdog/result.txt"))
        self.assertIn("--search", command)
        self.assertLess(command.index("--search"), command.index("exec"))
        self.assertIn("--ephemeral", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--ask-for-approval") + 1], "never")
        self.assertLess(command.index("--ask-for-approval"), command.index("exec"))

    def test_windows_paths_are_converted_without_shell(self):
        self.assertEqual(windows_to_wsl(r"D:\IntDog\DomainIntelData"),
                         "/mnt/d/IntDog/DomainIntelData")

    def test_windows_codex_command_explicitly_passes_codex_home(self):
        service = CodexCLIService.__new__(CodexCLIService)
        service.workspace = Path("/tmp/intdog")
        service.model = ""
        service._windows = True
        service.executable = "wsl.exe"
        service.codex_command = "/mnt/c/Users/Test/.codex/bin/wsl/x/codex"
        service.codex_home = "/mnt/c/Users/Test/.codex"
        command = service.build_command(Path("/tmp/intdog/result.txt"))
        self.assertIn("CODEX_HOME=/mnt/c/Users/Test/.codex", command)

    def test_entity_linked_to_multiple_chains_is_expanded(self):
        rows = normalize_entities([{"name": "A", "chain": ["上游", "下游"]}])
        self.assertEqual([row["chain"] for row in rows], ["上游", "下游"])

    def test_semicolon_joined_chains_are_split_against_valid_names(self):
        rows = normalize_entities([{"name": "A", "chain": "设计；制造；不存在"}],
                                  {"设计", "制造"})
        self.assertEqual([row["chain"] for row in rows], ["设计", "制造"])

    def test_report_output_cannot_escape_industry(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI")
            with self.assertRaises(ValueError):
                _safe_report_output(store, "../../outside.md")

    def test_periodic_direct_generation_writes_markdown_and_visualization(self):
        class FakeClient:
            def complete(self, _prompt):
                return types.SimpleNamespace(text="# 周报\n\n可核验内容。",
                                             provider="test", model="fake")
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI", "人工智能")
            store.save_daily("news", [{"title": "AI event", "url": "https://example.com/a",
                                        "source": "Example", "date": "2026-08-29",
                                        "category": "news"}], "2026-08-29")
            with patch("src.report_generation._client", return_value=FakeClient()):
                result = generate_periodic({"domain": {"keywords": ["AI"]}},
                                           store, "weekly", "codex")
            self.assertTrue(Path(result["path"]).exists())
            metadata = json.loads(Path(result["metadata"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "partial")
            self.assertIn("artifact_too_short", {
                failure["code"] for failure in metadata["quality"]["failures"]})
            self.assertEqual(metadata["visualization"]["type"], "bar")

    def test_feed_link_parser_finds_declared_rss(self):
        parser = _FeedLinkParser()
        parser.feed('<html><head><link rel="alternate" type="application/rss+xml" '
                    'href="/feed.xml"></head></html>')
        self.assertEqual(parser.links, ["/feed.xml"])

    def test_landscape_deduplicates_company_across_chains(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI", "人工智能")
            store._write_json(store.knowledge / "chains.json",
                              [{"name": "模型"}, {"name": "应用"}])
            store._write_json(store.knowledge / "entities.json", [
                {"id": "a1", "name": "Company A", "type": "company", "chain": "模型"},
                {"id": "a2", "name": "Company A", "type": "company", "chain": "应用"},
            ])
            result = build_landscape(store, {"domain": {"tracked_companies": []}})
            names = [item["name"] for item in result["tiers"]["watchlist"]]
            self.assertEqual(names, ["Company A"])
            self.assertEqual(result["tiers"]["challenger"], [])


if __name__ == "__main__":
    unittest.main()
