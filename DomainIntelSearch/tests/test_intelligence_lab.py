from __future__ import annotations

import tempfile
import time
import unittest
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from intdog_core import IntDogService
from src.intelligence_lab import IntelligenceLab


class IntelligenceLabTests(unittest.TestCase):
    def make_lab(self, temp: str) -> tuple[IntDogService, IntelligenceLab]:
        service = IntDogService(temp)
        service.create_industry("AI", "人工智能")
        return service, IntelligenceLab(temp, "AI")

    def test_evidence_compiler_counts_independent_publishers_and_contradictions(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            claim = service.repo.upsert_claim("AI", "market_share", {"value": 20})
            service.repo.add_evidence(claim, "supports", excerpt="first",
                                      publisher_cluster="publisher-a")
            service.repo.add_evidence(claim, "supports", excerpt="second",
                                      publisher_cluster="publisher-b")
            result = lab.compile_evidence()
            self.assertEqual(result["claims"][0]["evidence_state"], "corroborated")
            self.assertEqual(result["claims"][0]["independent_supporting_publishers"], 2)
            service.repo.add_evidence(claim, "contradicts", excerpt="conflict",
                                      publisher_cluster="publisher-c")
            result = lab.compile_evidence()
            self.assertEqual(result["claims"][0]["evidence_state"], "contested")

    def test_source_observatory_reports_local_observation_not_live_reachability(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            service.add_source("AI", "official", {
                "name": "SEC", "url": "https://www.sec.gov/", "added_manually": True})
            result = lab.observe_sources(stale_days=30)
            self.assertEqual(result["metrics"]["source_links"], 1)
            self.assertEqual(result["sources"][0]["health_status"], "unused")
            self.assertIn("news", result["missing_categories"])
            self.assertIn("本地已观察", result["limitation"])

    def test_source_observatory_exposes_snapshot_delta_after_new_document(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            service.add_source("AI", "news", {
                "name": "Example", "url": "https://example.com/"})
            first = lab.observe_sources()
            service.repo.upsert_document("AI", "news", "2026-08-29", {
                "title": "New event", "url": "https://example.com/event",
                "source": "Example", "source_url": "https://example.com/"})
            second = lab.observe_sources()
            self.assertGreater(second["metrics"]["documents"], first["metrics"]["documents"])
            self.assertGreater(second["metric_delta"]["documents"], 0)
            self.assertTrue(second["history"])

    def test_source_metrics_do_not_inflate_documents_across_categories(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            source = {"name": "Manual", "url": "https://example.com/",
                      "monitoring_status": "recommended_manual"}
            service.add_source("AI", "news", source)
            service.add_source("AI", "blogs", dict(source, url="https://example.com/blog"))
            document = {"title": "Same", "url": "https://example.com/item",
                        "source": "Manual", "source_url": "https://example.com/"}
            service.repo.upsert_document("AI", "news", "2026-08-29", document)
            service.repo.upsert_document("AI", "blogs", "2026-08-29", document)
            result = lab.observe_sources()
            self.assertEqual(result["metrics"]["documents"], 1)
            self.assertEqual(result["metrics"]["source_links"], 2)
            self.assertIn("manual_watch", {item["health_status"]
                                           for item in result["sources"]})

    def test_chain_scenario_propagates_monotonically_with_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            for position, name in enumerate(("设计", "制造", "封装", "终端"), 1):
                service.repo.upsert_chain_node("AI", {"name": name, "order": position})
            result = lab.simulate_chain("制造环节停产", chain="制造", max_hops=2)
            self.assertEqual(result["status"], "completed")
            distances = {}
            for item in result["impacts"]:
                distances.setdefault(item["distance"], []).append(item["score"])
                self.assertEqual(len(item["path"]), item["distance"] + 1)
            self.assertGreater(min(distances[0]), max(distances[1]))
            self.assertGreater(min(distances[1]), max(distances[2]))
            unresolved = lab.simulate_chain("无法映射的宏观事件", max_hops=2)
            self.assertEqual((unresolved["status"], unresolved["impacts"]),
                             ("unresolved", []))

    def test_boundary_agenda_is_stable_and_identical_snapshots_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            service.repo.upsert_chain_node("AI", {"name": "模型层", "order": 1})
            first = lab.plan_boundaries()
            first_ids = [item["id"] for item in first["active_items"]]
            second = lab.plan_boundaries()
            second_ids = [item["id"] for item in second["active_items"]]
            self.assertEqual(first_ids, second_ids)
            self.assertTrue(first_ids)
            with service.repo.connection() as con:
                versions = [row[0] for row in con.execute(
                    "SELECT version FROM schema_migrations ORDER BY version")]
                artifacts = con.execute(
                    "SELECT COUNT(*) FROM analysis_artifacts WHERE kind='research_agenda'").fetchone()[0]
            self.assertIn(9, versions)
            self.assertEqual(artifacts, 1)
            self.assertTrue((Path(temp) / "AI/one_time/intelligence/research_agenda.md").exists())

    def test_evidence_chain_edges_override_ordered_fallback_and_escape_mermaid(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            names = ('设计"] --> X["bad', "制造", "终端")
            node_ids = [service.repo.upsert_chain_node(
                "AI", {"name": name, "order": index}) for index, name in enumerate(names, 1)]
            edge_id = service.repo.upsert_chain_edge("AI", {
                "src_node_id": node_ids[0], "dst_node_id": node_ids[2],
                "relation": "supplies", "confidence": 0.9, "evidence_count": 2})
            service.repo.add_chain_edge_evidence(
                edge_id, "supports", url="https://example.com/chain-proof")
            result = lab.simulate_chain("设计受限", chain=names[0], max_hops=1)
            self.assertEqual(result["topology"], "evidence_edges")
            self.assertEqual({item["node"] for item in result["impacts"]},
                             {names[0], names[2]})
            self.assertEqual(result["impacts"][1]["path_edges"][0]["relation"], "supplies")
            mermaid = Path(result["mermaid_path"]).read_text(encoding="utf-8")
            self.assertNotIn(names[0], mermaid)

    def test_parallel_equal_weight_edges_do_not_compare_payloads(self):
        from src.lab.scenario import build_chain_scenario
        nodes = [{"id": key, "name": name} for key, name in
                 (("a", "A"), ("b", "B"), ("c", "C"))]
        edges = [{"id": f"e-{dst}", "src_node_id": "a", "dst_node_id": dst,
                  "relation": "supplies", "confidence": .8, "evidence_count": 1}
                 for dst in ("b", "c")]
        result = build_chain_scenario("A shock", "A", 2, nodes, [], edges)
        self.assertEqual({item["node"] for item in result["impacts"]}, {"A", "B", "C"})

    def test_depends_on_propagates_dependency_failure_toward_dependent(self):
        from src.lab.scenario import build_chain_scenario
        nodes = [{"id": "dependent", "name": "整机"},
                 {"id": "dependency", "name": "芯片"}]
        edge = {"id": "edge", "src_node_id": "dependent",
                "dst_node_id": "dependency", "relation": "depends_on",
                "confidence": 1, "evidence_count": 1}
        from_dependency = build_chain_scenario(
            "芯片中断", "芯片", 1, nodes, [], [edge])
        from_dependent = build_chain_scenario(
            "整机需求", "整机", 1, nodes, [], [edge])
        strong = next(item for item in from_dependency["impacts"] if item["node"] == "整机")
        weak = next(item for item in from_dependent["impacts"] if item["node"] == "芯片")
        self.assertGreater(strong["score"], weak["score"])
        self.assertEqual(strong["path_edges"][0]["direction"], "upstream")

    def test_candidate_edge_is_excluded_until_evidence_is_linked(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            ids = [service.repo.upsert_chain_node(
                "AI", {"name": name, "order": index})
                   for index, name in enumerate(("A", "B", "C"), 1)]
            service.repo.upsert_chain_edge("AI", {
                "src_node_id": ids[0], "dst_node_id": ids[2],
                "relation": "supplies", "confidence": .9})
            result = lab.simulate_chain("A", chain="A", max_hops=1)
            self.assertEqual(result["topology"], "ordered_fallback")
            self.assertEqual(result["candidate_edges_excluded"], 1)
            self.assertEqual({item["node"] for item in result["impacts"]}, {"A", "B"})

    def test_scenario_bundle_is_versioned_and_hash_validated(self):
        from src.lab.artifacts import audit_bundles, validate_bundle
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            service.repo.upsert_chain_node("AI", {"name": "模型", "order": 1})
            first = lab.simulate_chain("模型涨价", chain="模型")
            second = lab.simulate_chain("模型降价", chain="模型")
            self.assertNotEqual(first["artifact_id"], second["artifact_id"])
            self.assertEqual(validate_bundle(Path(first["bundle_path"]))["event"], "模型涨价")
            (lab.output / "latest" / "chain_scenario.json").write_text(
                '{"bundle":"missing"}', encoding="utf-8")
            audit = audit_bundles(lab.output, repair_latest=True)
            self.assertEqual((audit["valid"], audit["invalid"]), (2, 0))
            self.assertEqual((audit["invalid_pointers"], audit["repaired_pointers"]), (1, 1))

    def test_agenda_history_and_bounded_task_package_are_persisted(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            service.repo.upsert_chain_node("AI", {"name": "模型", "order": 1})
            item = lab.plan_boundaries()["active_items"][0]
            service.update_research_agenda_status("AI", item["id"], "in_progress")
            task = service.create_research_task("AI", item["id"], 7)
            self.assertEqual(task["constraints"]["max_documents"], 7)
            self.assertTrue(Path(task["path"]).exists())
            self.assertEqual(service.repo.list_research_agenda_history(
                "AI", item["id"])[0]["to_status"], "in_progress")
            self.assertEqual(service.repo.list_research_tasks(
                "AI", item["id"])[0]["id"], task["id"])

    def test_mcp_lab_tools_are_read_only_and_explain_paths(self):
        import src.mcp_server as mcp
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            service.repo.upsert_chain_node("AI", {"name": "模型", "order": 1})
            scenario = lab.simulate_chain("模型变化", chain="模型")
            previous = mcp.DATA_ROOT
            mcp.DATA_ROOT = Path(temp)
            try:
                listed = mcp.tool_list_scenarios({"industry": "AI"})
                explained = mcp.tool_explain_scenario_path({
                    "industry": "AI", "artifact_id": scenario["artifact_id"],
                    "node_id": scenario["impacts"][0]["node_id"]})
            finally:
                mcp.DATA_ROOT = previous
            self.assertEqual(listed["count"], 1)
            self.assertEqual(explained["score_semantics"],
                             "heuristic_exposure_not_probability")

    def test_unresolved_status_reaches_artifact_and_run(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            result = lab.simulate_chain("unmapped event")
            self.assertEqual(result["status"], "unresolved")
            with service.repo.connection() as con:
                artifact = con.execute("SELECT status FROM analysis_artifacts").fetchone()[0]
                run = con.execute("SELECT status FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()[0]
            self.assertEqual((artifact, run), ("unresolved", "unresolved"))

    def test_industry_lock_rejects_parallel_lab_run(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            service.repo.acquire_lock("industry:AI", "another-run")
            try:
                with self.assertRaisesRegex(RuntimeError, "正在运行"):
                    lab.compile_evidence()
            finally:
                service.repo.release_lock("industry:AI", "another-run")

    def test_resolved_gap_requires_human_confirmation_and_keeps_user_status(self):
        with tempfile.TemporaryDirectory() as temp:
            service, lab = self.make_lab(temp)
            service.repo.upsert_chain_node("AI", {"name": "模型", "order": 1})
            first = lab.plan_boundaries()["active_items"][0]
            service.update_research_agenda_status("AI", first["id"], "in_progress")
            for index in range(3):
                service.repo.upsert_entity("AI", {
                    "name": f"Company {index}", "type": "company", "chain": "模型",
                    "references": [f"https://example.com/{index}"]}, "模型")
            lab.plan_boundaries()
            rows = service.repo.list_research_agenda("AI", include_closed=True)
            preserved = next(row for row in rows if row["id"] == first["id"])
            self.assertEqual(preserved["status"], "in_progress")
            service.update_research_agenda_status("AI", first["id"], "open")
            lab.plan_boundaries()
            rows = service.repo.list_research_agenda("AI", include_closed=True)
            resolved = next(row for row in rows if row["id"] == first["id"])
            self.assertEqual(resolved["status"], "resolved_candidate")

    def test_atomic_text_replace_preserves_previous_file_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "artifact.md"
            path.write_text("previous", encoding="utf-8")
            with patch.object(Path, "replace", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    IntDogService.write_text(path, "new")
            self.assertEqual(path.read_text(encoding="utf-8"), "previous")

    def test_evidence_builder_handles_ten_thousand_claims_with_linear_work(self):
        from src.lab.evidence import build_evidence_graph
        claims = [{"id": f"c{i}", "subject_id": None, "subject_name": "",
                   "predicate": "p", "object": i, "qualifiers": {}, "status": "candidate",
                   "evidence": []} for i in range(10_000)]
        started = time.perf_counter()
        result = build_evidence_graph(claims, [])
        self.assertEqual(result["metrics"]["claims"], 10_000)
        self.assertLess(time.perf_counter() - started, 2.0)

    def test_cli_end_to_end_and_unresolved_exit_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            service, _lab = self.make_lab(temp)
            env = {**os.environ, "DOMAIN_INTEL_DATA_ROOT": temp}
            complete = subprocess.run(
                [sys.executable, "-m", "src.main", "run-lab", "--folder", "AI"],
                cwd=Path(__file__).resolve().parents[1], env=env,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(complete.returncode, 0, complete.stderr)
            audit = subprocess.run(
                [sys.executable, "-m", "src.main", "audit-artifacts", "--folder", "AI"],
                cwd=Path(__file__).resolve().parents[1], env=env,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(audit.returncode, 0, audit.stderr)
            self.assertIn("产物审计", audit.stdout)
            unresolved = subprocess.run(
                [sys.executable, "-m", "src.main", "simulate-chain", "--folder", "AI",
                 "--event", "unknown"], cwd=Path(__file__).resolve().parents[1], env=env,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(unresolved.returncode, 4, unresolved.stderr)
            with service.repo.connection() as con:
                statuses = [row[0] for row in con.execute(
                    "SELECT status FROM runs ORDER BY rowid")]
            self.assertIn("unresolved", statuses)


if __name__ == "__main__":
    unittest.main()
