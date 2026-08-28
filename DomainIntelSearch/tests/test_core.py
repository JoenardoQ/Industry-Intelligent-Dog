from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

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
from src.verification import score_group, verify_store_daily
from src.crawlers.periodic_crawlers import _matches
from src.scheduler import PeriodicScheduler
from src.services.task_executor import _safe_output
from src.services.codex_cli_service import CodexCLIService, windows_to_wsl
from src import mcp_server


class CoreContractTests(unittest.TestCase):
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

    def test_source_gate_rejects_china_foreign_imbalance(self):
        sources = seed_sources("人工智能", "AI", {"id": "ai"})
        audit = audit_sources(sources)
        self.assertIn("china_foreign_balance", audit["checks"])
        self.assertFalse(audit["checks"]["china_foreign_balance"])

    def test_source_balancer_trims_only_redundant_foreign_sources(self):
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
        self.assertLessEqual(audit["foreign_per_china"], 1.8)
        self.assertTrue(all(len(balanced[key]) >= 3 for key in sources))

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


if __name__ == "__main__":
    unittest.main()
