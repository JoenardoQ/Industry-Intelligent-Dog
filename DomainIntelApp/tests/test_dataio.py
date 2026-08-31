from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime import dataio


class DataIOTests(unittest.TestCase):
    def tearDown(self):
        dataio._cached_service.cache_clear()

    def test_read_startup_does_not_rewrite_existing_industry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "AI", "Artificial Intelligence")

            # Settle the one-time legacy-import bookkeeping, then give the
            # existing row a hand-derived timestamp that a read must preserve.
            dataio._cached_service.cache_clear()
            dataio.list_industries(root)
            dataio._cached_service.cache_clear()
            db_path = root / "intdog.sqlite3"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    "UPDATE industries SET updated_at=? WHERE folder=?",
                    ("2001-02-03T04:05:06+00:00", "AI"),
                )
                connection.commit()
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()

            self.assertEqual(dataio.list_industries(root)[0]["folder"], "AI")

            with sqlite3.connect(
                f"file:{db_path}?mode=ro", uri=True
            ) as connection:
                updated_at = connection.execute(
                    "SELECT updated_at FROM industries WHERE folder=?", ("AI",)
                ).fetchone()[0]
            self.assertEqual(updated_at, "2001-02-03T04:05:06+00:00")
            self.assertEqual(
                hashlib.sha256(db_path.read_bytes()).hexdigest(), before_hash
            )

    def test_industry_lifecycle_is_recoverable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "Quantum", "量子计算")
            self.assertEqual(dataio.list_industries(root)[0]["folder"], "Quantum")
            dataio.rename_industry(root, "Quantum", "Quantum-Tech", "量子科技")
            self.assertTrue((root / "Quantum-Tech" / "control.json").exists())
            archived = dataio.archive_industry(root, "Quantum-Tech")
            self.assertTrue(archived.exists())
            self.assertEqual(dataio.list_industries(root), [])

    def test_bulk_daily_delete_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "AI")
            path = root / "AI" / "periodic" / "daily" / "2026-08-29" / "news.json"
            dataio.write_json(path, [
                {"title": "A", "url": "https://example.com/a"},
                {"title": "B", "url": "https://example.com/b"},
            ])
            removed = dataio.delete_daily_items(
                root, "AI", [("2026-08-29", "news", "https://example.com/a")])
            self.assertEqual(removed, 1)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))), 1)
            self.assertEqual(len(list((root / "_trash" / "daily").glob("*.json"))), 1)

    def test_sources_can_overlap_between_industries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "AI")
            dataio.create_industry(root, "Chips")
            source = {"name": "Shared", "url": "https://example.com/feed",
                      "origin": "international"}
            self.assertTrue(dataio.add_source(root, "AI", "news", source))
            self.assertTrue(dataio.add_source(root, "Chips", "news", source))
            self.assertFalse(dataio.add_source(root, "AI", "news", source))
            status = dataio.read_core_status(root, "AI")
            self.assertEqual(status["sources"], 1)

    def test_report_list_excludes_bootstrap_transcripts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "AI")
            report = root / "AI" / "one_time" / "reports" / "tech_6m.md"
            transcript = (root / "AI" / "one_time" / "research" / "bootstrap" /
                          "codex_runs" / "last_message.txt")
            dataio.write_json(root / "AI" / "one_time" / "reports" / "tasks.json", {})
            report.parent.mkdir(parents=True, exist_ok=True); report.write_text("# report")
            transcript.parent.mkdir(parents=True, exist_ok=True)
            transcript.write_text('{"candidate": true}')
            listed = dataio.list_reports(root, "AI")
            self.assertEqual([item["name"] for item in listed],
                             ["one_time/reports/tech_6m.md"])

    def test_industry_report_index_has_exact_product_ids_and_excludes_other_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "AI")
            reports = root / "AI" / "one_time" / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            for report_id in ("trend_5y", "popular_2y", "tech_6m"):
                (reports / f"{report_id}.md").write_text(
                    f"# {report_id}", encoding="utf-8"
                )
            (reports / "deep").mkdir()
            (reports / "deep" / "chain.md").write_text("# deep", encoding="utf-8")
            transcript = (
                root / "AI" / "one_time" / "research" / "bootstrap"
                / "codex_runs" / "last_message.txt"
            )
            transcript.parent.mkdir(parents=True)
            transcript.write_text("bootstrap transcript", encoding="utf-8")

            listed = dataio.list_reports(root, "AI")

            self.assertEqual(
                [item["id"] for item in listed],
                ["trend_5y", "popular_2y", "tech_6m"],
            )
            self.assertEqual(
                [Path(item["path"]).name for item in listed],
                ["trend_5y.md", "popular_2y.md", "tech_6m.md"],
            )

    def test_intelligence_lab_artifacts_are_read_without_becoming_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "AI")
            base = root / "AI" / "one_time" / "intelligence"
            dataio.write_json(base / "evidence_graph.json", {"metrics": {"claims": 2}})
            dataio.write_json(base / "scenarios" / "shock.json", {"event": "shock"})
            lab = dataio.read_intelligence_lab(root, "AI")
            self.assertEqual(lab["evidence"]["metrics"]["claims"], 2)
            self.assertEqual(lab["scenarios"][0]["event"], "shock")
            self.assertEqual(dataio.list_reports(root, "AI"), [])

    def test_research_agenda_status_uses_application_service(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "AI")
            service = dataio._service(root)
            item = {"dimension": "claim", "target_key": "c1", "title": "Check",
                    "priority": 80, "rationale": "single source"}
            item_id = service.repo.upsert_research_agenda("AI", [item])[0]
            self.assertTrue(dataio.update_agenda_status(root, "AI", item_id, "done"))
            self.assertEqual(dataio.list_research_agenda(root, "AI")[0]["status"], "done")

    def test_lab_reader_prefers_versioned_scenarios_and_creates_task(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataio.create_industry(root, "AI")
            base = root / "AI" / "one_time" / "intelligence"
            dataio.write_json(base / "scenarios" / "legacy.json", {"event": "legacy"})
            from src.lab.artifacts import write_bundle
            write_bundle(dataio._service(root), base, "chain_scenario", "a1",
                         {"artifact_id": "a1", "event": "versioned",
                          "generated_at": "2026-08-29T00:00:00Z"}, "# versioned")
            self.assertEqual(dataio.read_intelligence_lab(root, "AI")["scenarios"][0]["event"],
                             "versioned")
            service = dataio._service(root)
            agenda_id = service.repo.upsert_research_agenda("AI", [{
                "dimension": "source", "target_key": "official", "title": "补齐来源",
                "priority": 90, "rationale": "缺口", "queries": ["official source"]}])[0]
            task = dataio.create_research_task(root, "AI", agenda_id, 5)
            self.assertEqual(task["budget"], 5)
            self.assertEqual(dataio.list_research_tasks(root, "AI", agenda_id)[0]["id"],
                             task["id"])


if __name__ == "__main__":
    unittest.main()
