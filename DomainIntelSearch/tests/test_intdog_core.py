from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from intdog_core import IntDogService, IntelligenceRepository


class IntelligenceCoreTests(unittest.TestCase):
    def test_shared_source_and_entity_are_canonical_across_industries(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            service.create_industry("AI", "人工智能")
            service.create_industry("Chips", "半导体")
            source = {"name": "Example", "url": "https://www.example.com/?utm_source=x"}
            service.add_source("AI", "news", source)
            service.add_source("Chips", "news", source)
            first = service.repo.upsert_entity("AI", {"name": "NVIDIA", "type": "company"})
            second = service.repo.upsert_entity("Chips", {"name": "NVIDIA", "type": "company"})
            self.assertEqual(first, second)
            with service.repo.connection() as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 1)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM industry_sources").fetchone()[0], 2)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 1)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM industry_entities").fetchone()[0], 2)

    def test_authoritative_source_refresh_soft_deletes_removed_links(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            service.create_industry("AI")
            first = {"news": [{"name": "A", "url": "https://a.example.com"},
                              {"name": "B", "url": "https://b.example.com"}]}
            second = {"news": [first["news"][0]]}
            service.import_sources("AI", first, replace=True)
            service.import_sources("AI", second, replace=True)
            self.assertEqual([item["name"] for item in service.repo.list_sources("AI")], ["A"])

    def test_run_records_failure_without_hiding_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            service.create_industry("AI")
            with self.assertRaisesRegex(RuntimeError, "broken"):
                with service.run("AI", "bootstrap"):
                    raise RuntimeError("broken")
            with service.repo.connection() as con:
                row = con.execute("SELECT status,error_code FROM runs").fetchone()
            self.assertEqual(dict(row), {"status": "failed", "error_code": "RuntimeError"})

    def test_rapid_consecutive_runs_receive_unique_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            service.create_industry("AI")
            with service.run("AI", "verify") as first:
                pass
            with service.run("AI", "verify") as second:
                pass
            self.assertNotEqual(first, second)

    def test_full_text_search_and_claim_evidence_are_queryable(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            service.create_industry("AI")
            document_id = service.repo.upsert_document("AI", "news", "2026-08-29", {
                "title": "New inference accelerator", "abstract": "efficient AI inference",
                "url": "https://example.com/accelerator"})
            claim_id = service.repo.upsert_claim(
                "AI", "announced", {"product": "accelerator"},
                qualifiers={"scope": "global"}, status="collected")
            service.repo.add_evidence(
                claim_id, "supports", document_id=document_id,
                publisher_cluster="example.com", extraction_method="test")
            results = service.repo.search_documents("AI", "accelerator")
            self.assertEqual(results[0]["id"], document_id)
            stats = service.repo.knowledge_stats("AI")
            self.assertEqual((stats["claims"], stats["evidence"]), (1, 1))

    def test_legacy_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = IntDogService(root)
            service.create_industry("AI")
            file = root / "AI/periodic/daily/2026-08-29/news.json"
            service.write_json(file, [{"title": "A", "url": "https://example.com/a"}])
            first = service.migrate_legacy()
            second = service.migrate_legacy()
            self.assertEqual(first["documents"], 1)
            self.assertEqual(second["documents"], 0)
            self.assertGreaterEqual(second["skipped_files"], 1)
            self.assertEqual(len(service.repo.list_documents("AI")), 1)

    def test_schema_migration_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            IntelligenceRepository(temp)
            IntelligenceRepository(temp)
            with IntelligenceRepository(temp).connection() as con:
                versions = con.execute("SELECT version FROM schema_migrations").fetchall()
            self.assertEqual([row["version"] for row in versions], list(range(1, 22)))

    def test_schema_v10_recovers_when_columns_exist_before_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            with service.repo.transaction() as con:
                con.execute("DELETE FROM schema_migrations WHERE version=10")
                con.execute("DROP TABLE chain_edge_evidence")
                con.execute("DROP TABLE research_agenda_history")
                con.execute("DROP TABLE research_tasks")
            recovered = IntDogService(temp)
            with recovered.repo.connection() as con:
                version = con.execute("""SELECT 1 FROM schema_migrations
                    WHERE version=10""").fetchone()
                tables = {row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIsNotNone(version)
            self.assertTrue({"chain_edge_evidence", "research_agenda_history",
                             "research_tasks"}.issubset(tables))

    def test_connection_context_closes_and_unknown_reads_do_not_register(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = IntelligenceRepository(temp)
            with repo.connection() as con:
                self.assertEqual(con.execute("SELECT 1").fetchone()[0], 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                con.execute("SELECT 1")
            before = len(repo.list_industries())
            with self.assertRaises(FileNotFoundError):
                repo.list_sources("Ghost")
            self.assertEqual(len(repo.list_industries()), before)

    def test_dirty_compatibility_views_rebuild_from_sqlite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = IntDogService(root)
            service.create_industry("AI", "人工智能")
            service.repo.upsert_source(
                "AI", "news", {"name": "Example", "url": "https://example.com/feed"})
            service.repo.upsert_document("AI", "news", "2026-08-29", {
                "title": "A", "url": "https://example.com/a"})
            service.repo.upsert_entity("AI", {
                "name": "Example Corp", "type": "company", "chain": "Applications"})
            dirty = {row["view_key"] for row in service.repo.dirty_compat_views(["AI"])}
            self.assertEqual(dirty, {"sources", "daily:2026-08-29:news", "entities", "chains"})
            result = service.reconcile_compat(["AI"])
            self.assertEqual(result, {"repaired": 4, "failed": 0, "errors": []})
            sources = json.loads((root / "AI/sources.json").read_text(encoding="utf-8"))
            daily = json.loads((root / "AI/periodic/daily/2026-08-29/news.json")
                               .read_text(encoding="utf-8"))
            entities = json.loads((root / "AI/one_time/knowledge/entities.json")
                                  .read_text(encoding="utf-8"))
            chains = json.loads((root / "AI/one_time/knowledge/chains.json")
                                .read_text(encoding="utf-8"))
            self.assertEqual(sources["news"][0]["name"], "Example")
            self.assertEqual(daily[0]["title"], "A")
            self.assertEqual(entities[0]["name"], "Example Corp")
            self.assertEqual(chains[0]["name"], "Applications")
            self.assertEqual(service.repo.dirty_compat_views(["AI"]), [])

    def test_failed_json_write_keeps_recoverable_dirty_view(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = IntDogService(root)
            service.create_industry("AI")
            original = service.write_json
            with patch.object(service, "write_json", side_effect=OSError("disk unavailable")):
                with self.assertRaises(OSError):
                    service.add_source("AI", "news", {
                        "name": "Example", "url": "https://example.com/feed"})
            self.assertEqual(
                [row["view_key"] for row in service.repo.dirty_compat_views(["AI"])],
                ["sources"])
            service.write_json = original
            self.assertEqual(service.reconcile_compat(["AI"])["repaired"], 1)
            payload = json.loads((root / "AI/sources.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["news"][0]["name"], "Example")

    def test_publisher_registry_and_entity_identifiers_are_canonical(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            service.create_industry("AI")
            service.repo.upsert_source("AI", "news", {
                "name": "Reuters AI", "url": "https://reuters.com/technology"})
            document_id = service.repo.upsert_document("AI", "news", "2026-08-29", {
                "title": "NVIDIA company profile",
                "url": "https://reuters.com/technology/nvidia-profile",
            })
            first = service.repo.upsert_entity("AI", {
                "name": "英伟达", "name_en": "NVIDIA", "type": "company",
                "country": "US", "external_ids": {"lei": "549300S4KLFTLO7GSQ80"},
                "chain": "Compute", "references": [{"document_id": document_id}]})
            second = service.repo.upsert_entity("AI", {
                "name": "NVIDIA Corporation", "type": "company", "country": "US",
                "external_ids": {"lei": "549300S4KLFTLO7GSQ80"}, "chain": "Applications"})
            self.assertEqual(first, second)
            with service.repo.connection() as con:
                publisher = con.execute("SELECT owner_cluster,verification_status FROM publishers").fetchone()
                roles = con.execute("SELECT COUNT(*) FROM entity_chain_roles").fetchone()[0]
            self.assertEqual(dict(publisher), {"owner_cluster": "reuters",
                                               "verification_status": "verified"})
            self.assertEqual(roles, 2)
            nodes = service.repo.list_chain_nodes("AI")
            compute = next(node for node in nodes if node["name"] == "Compute")
            self.assertEqual(compute["coverage_status"], "covered")

    def test_nested_runs_are_reentrant_but_parallel_owner_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            service.create_industry("AI")
            with service.run("AI", "report") as outer:
                with service.run("AI", "aggregate") as inner:
                    self.assertEqual(inner, outer)
                with self.assertRaises(RuntimeError):
                    service.repo.acquire_lock("industry:AI", "another-owner")
            with service.repo.connection() as con:
                rows = con.execute("SELECT kind,status FROM runs").fetchall()
            self.assertEqual([dict(row) for row in rows],
                             [{"kind": "report", "status": "completed"}])

    def test_story_identity_review_and_source_health_are_persistent(self):
        with tempfile.TemporaryDirectory() as temp:
            service = IntDogService(temp)
            service.create_industry("AI")
            first = service.repo.upsert_document("AI", "news", "2026-08-30", {
                "title": "First", "url": "https://one.example/story"})
            second = service.repo.upsert_document("AI", "news", "2026-08-30", {
                "title": "Second", "url": "https://two.example/story"})
            third = service.repo.upsert_document("AI", "news", "2026-08-30", {
                "title": "Third", "url": "https://three.example/story"})
            story_ids = service.repo.save_story_groups("AI", [{
                "title": "First story", "story_family": "event",
                "documents": [
                    {"document_id": first, "publisher_cluster": "one",
                     "observed_at": "2026-08-30"},
                    {"document_id": second, "publisher_cluster": "two",
                     "observed_at": "2026-08-30"},
                ],
            }, {
                "title": "Third story", "story_family": "event",
                "documents": [{"document_id": third, "publisher_cluster": "three",
                               "observed_at": "2026-08-30"}],
            }], "test-v1")
            new_id = service.repo.split_story(
                "AI", story_ids[0], [second], "Second story", actor="test")
            service.repo.merge_stories("AI", story_ids[1], new_id, actor="test")

            source_id = service.repo.upsert_source("AI", "news", {
                "name": "Example", "url": "https://source.example/feed"})
            service.repo.update_source_health(
                "AI", source_id, adapter="feed", status="failed",
                error_code="timeout", error_message="safe timeout")
            service.repo.update_source_health(
                "AI", source_id, adapter="feed", status="fresh")

            stories = service.repo.list_stories("AI")
            source = service.repo.list_sources("AI")[0]
            with service.repo.connection() as con:
                reviews = con.execute("SELECT action FROM story_reviews ORDER BY id").fetchall()
            self.assertEqual([row["action"] for row in reviews], ["split", "merge"])
            self.assertTrue(any(row["id"] == story_ids[1] and
                                row["document_count"] == 2 for row in stories))
            self.assertEqual(source["health"]["status"], "fresh")
            self.assertEqual(source["health"]["consecutive_failures"], 0)
            self.assertIsNotNone(source["health"]["last_good_at"])


if __name__ == "__main__":
    unittest.main()
