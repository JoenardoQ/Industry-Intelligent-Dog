from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from intdog_core import IntelligenceRepository
from intdog_core import repository as repository_module
from intdog_core.evidence_repository import NON_FACT_ASSERTION_TYPES
from src import agent_evidence as agent_evidence_module
from src.agent_evidence import (
    AssertionVerifier,
    ConfiguredSemanticEvaluator,
    EvidenceProbe,
    SemanticEvaluation,
    probe_agent_evidence,
    verify_agent_assertion,
)


def result_record(suffix: str = "one") -> dict:
    digest = (suffix.encode("utf-8").hex() + "0" * 64)[:64]
    return {
        "result_id": digest,
        "content_sha256": digest,
        "task_id": f"task-{suffix}",
        "agent_id": "test-agent",
        "summary": "A bounded result",
        "status": "draft_review_required",
        "created_at": "2026-09-01T00:00:00+00:00",
        "assertions": [{
            "text": f"Atomic assertion {suffix}",
            "type": "identity",
            "citations": ["https://example.com/source"],
            "atomic": {
                "subject": "Example",
                "predicate": "identity",
                "object": f"Atomic assertion {suffix}",
                "time": "2026-09-01",
                "region": "global",
                "qualifiers": {},
            },
        }],
    }


def passing_verification_checks() -> dict:
    names = {
        "atomization", "reachability", "publisher_identity", "publication_time",
        "entity_alignment", "semantic_support", "locator_integrity",
        "numeric_consistency", "corroboration", "conflict",
        "verifier_independence", "type_policy", "fact_projection",
    }
    checks = {name: {"status": "passed"} for name in names}
    checks["fact_projection"]["evidence"] = [{
        "url": "https://example.com/source",
        "content_hash": "a" * 64,
        "published_at": "2026-09-01T00:00:00+00:00",
        "excerpt": "Atomic assertion",
        "publisher_cluster": "example.com",
        "relation": "supports",
        "locator": {"type": "text_offset", "start": 0, "end": 16},
        "reachable": True,
    }]
    return checks


def write_artifact(tmp_path, folder: str, record: dict, name: str = "result.json") -> Path:
    raw_path = tmp_path / folder / "one_time" / "agent_results" / name
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(record), encoding="utf-8")
    return raw_path


def index_result(repo: IntelligenceRepository, tmp_path, suffix: str = "one") -> dict:
    record = result_record(suffix)
    raw_path = write_artifact(tmp_path, "AI", record, f"{record['result_id']}.json")
    return repo.index_agent_result("AI", record, str(raw_path))


def test_schema_14_migrates_to_latest_repeatably_without_changing_existing_claims(tmp_path):
    assert repository_module.SCHEMA_VERSION == 23
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    claim_id = repo.upsert_claim("AI", "existing", {"value": 1})
    with repo.transaction() as con:
        con.execute("DELETE FROM schema_migrations WHERE version=15")
        con.execute("DROP TABLE claim_evidence_snapshots")
        con.execute("DROP TABLE document_snapshots")

    IntelligenceRepository(tmp_path).migrate()
    with IntelligenceRepository(tmp_path).connection() as con:
        versions = [row[0] for row in con.execute(
            "SELECT version FROM schema_migrations ORDER BY version")]
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        claim = con.execute("SELECT status FROM claims WHERE id=?", (claim_id,)).fetchone()
    assert versions == list(range(1, repository_module.SCHEMA_VERSION + 1))
    assert {"agent_results", "agent_assertions", "agent_citations",
            "agent_result_reviews"}.issubset(tables)
    assert claim["status"] == "candidate"


def test_schema_15_backfills_legacy_document_evidence_and_citation_snapshots(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="legacy-backfill")
    accepted = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())
    with repo.transaction() as con:
        con.execute("UPDATE evidence SET snapshot_id=NULL WHERE claim_id=?",
                    (accepted.claim_id,))
        con.execute("UPDATE agent_citations SET snapshot_id=NULL WHERE assertion_id=?",
                    (assertion_id,))
        con.execute("DELETE FROM claim_evidence_snapshots")
        con.execute("DELETE FROM document_snapshots")
        con.execute("DROP TABLE claim_evidence_snapshots")
        con.execute("DROP TABLE document_snapshots")
        con.execute("DELETE FROM schema_migrations WHERE version=15")

    migrated = IntelligenceRepository(tmp_path)
    migrated.migrate()
    with migrated.connection() as con:
        evidence = con.execute(
            "SELECT snapshot_id FROM evidence WHERE claim_id=?",
            (accepted.claim_id,)).fetchone()
        citation = con.execute(
            "SELECT snapshot_id FROM agent_citations WHERE assertion_id=?",
            (assertion_id,)).fetchone()
        snapshot = con.execute(
            "SELECT status,content_hash,content_text FROM document_snapshots WHERE id=?",
            (evidence["snapshot_id"],)).fetchone()
    assert evidence["snapshot_id"] == citation["snapshot_id"]
    assert snapshot["status"] == "legacy_unresolved"
    assert sha256(snapshot["content_text"].encode()).hexdigest() == snapshot["content_hash"]
    with migrated.connection() as con:
        audit = con.execute("""SELECT COUNT(*) FROM audit_log
            WHERE action='schema15_backfill_needs_reverification'""").fetchone()[0]
    assert audit >= 1


def test_schema_15_backfill_keeps_multi_evidence_links_without_guessing_citations(tmp_path):
    repo = _verification_repo(tmp_path)
    url = "https://sec.gov/legacy-multi"
    assertion_ids, claim_ids = [], []
    for suffix, assertion_type, predicate, text in (
        ("one", "identity", "identity", "NVIDIA is an AI company legacy one"),
        ("two", "regulatory_status", "regulatory_status",
         "NVIDIA is registered legacy two"),
    ):
        _, assertion_id = submitted_assertion(
            repo, tmp_path, suffix=f"legacy-multi-{suffix}",
            assertion_type=assertion_type, citations=[url], atomic={
                "subject": "NVIDIA", "predicate": predicate, "object": text,
                "time": "2026", "region": "US", "qualifiers": {}})
        decision = verify_agent_assertion(
            repo, "AI", assertion_id,
            fetch=lambda _url, value=text: evidence_probe(url, text=value),
            semantic_evaluator=configured_evaluator())
        assertion_ids.append(assertion_id)
        claim_ids.append(decision.claim_id)
    with repo.transaction() as con:
        con.execute("UPDATE evidence SET snapshot_id=NULL")
        con.execute("UPDATE agent_citations SET snapshot_id=NULL")
        con.execute("DELETE FROM claim_evidence_snapshots")
        con.execute("DELETE FROM document_snapshots")
        con.execute("DROP TABLE claim_evidence_snapshots")
        con.execute("DROP TABLE document_snapshots")
        con.execute("DELETE FROM schema_migrations WHERE version=15")

    migrated = IntelligenceRepository(tmp_path)
    with migrated.connection() as con:
        evidence_links = [row[0] for row in con.execute(
            "SELECT snapshot_id FROM evidence ORDER BY claim_id")]
        citation_links = [row[0] for row in con.execute(
            "SELECT snapshot_id FROM agent_citations ORDER BY assertion_id")]
        unresolved = con.execute("""SELECT COUNT(*) FROM audit_log
            WHERE action='schema15_backfill_needs_reverification'""").fetchone()[0]
    assert len(set(evidence_links)) == 2 and all(evidence_links)
    assert set(citation_links) == set(evidence_links)
    assert unresolved >= 2


def test_schema_15_never_links_candidate_citation_to_accepted_snapshot(tmp_path):
    repo = _verification_repo(tmp_path)
    shared_url = "https://sec.gov/legacy-shared"
    _, accepted_assertion = submitted_assertion(
        repo, tmp_path, suffix="legacy-accepted", citations=[shared_url])
    accepted = verify_agent_assertion(
        repo, "AI", accepted_assertion,
        fetch=lambda url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())
    _, candidate_assertion = submitted_assertion(
        repo, tmp_path, suffix="legacy-candidate", citations=[shared_url])
    with repo.transaction() as con:
        accepted_document = con.execute(
            "SELECT document_id FROM evidence WHERE claim_id=?",
            (accepted.claim_id,)).fetchone()[0]
        con.execute("""UPDATE agent_citations SET document_id=?,snapshot_id=NULL
            WHERE assertion_id=?""", (accepted_document, candidate_assertion))
        con.execute("UPDATE evidence SET snapshot_id=NULL WHERE claim_id=?",
                    (accepted.claim_id,))
        con.execute("UPDATE agent_citations SET snapshot_id=NULL")
        con.execute("DELETE FROM claim_evidence_snapshots")
        con.execute("DELETE FROM document_snapshots")
        con.execute("DROP TABLE claim_evidence_snapshots")
        con.execute("DROP TABLE document_snapshots")
        con.execute("DELETE FROM schema_migrations WHERE version=15")

    migrated = IntelligenceRepository(tmp_path)
    with migrated.connection() as con:
        accepted_link = con.execute("""SELECT ac.snapshot_id
            FROM agent_citations ac WHERE ac.assertion_id=?""",
            (accepted_assertion,)).fetchone()[0]
        candidate_link = con.execute("""SELECT ac.snapshot_id
            FROM agent_citations ac WHERE ac.assertion_id=?""",
            (candidate_assertion,)).fetchone()[0]
        evidence_link = con.execute(
            "SELECT snapshot_id FROM evidence WHERE claim_id=?",
            (accepted.claim_id,)).fetchone()[0]
        candidate_audit = con.execute("""SELECT COUNT(*) FROM audit_log
            WHERE action='schema15_backfill_needs_reverification'
            AND object_type='agent_citation' AND object_id=(
                SELECT id FROM agent_citations WHERE assertion_id=?)""",
            (candidate_assertion,)).fetchone()[0]
    assert accepted_link == evidence_link
    assert candidate_link is None
    assert candidate_audit == 1


def test_repeated_import_preserves_review_and_original_artifact(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    first = index_result(repo, tmp_path)
    raw_path = Path(first["original_file"])
    original = raw_path.read_bytes()
    assertion_id = first["assertions"][0]["id"]
    repo.review_agent_assertion(
        "AI", assertion_id, decision="opinion", actor="tester", note="judgment")

    duplicate = repo.index_agent_result("AI", result_record(), str(raw_path))
    page = repo.list_agent_results("AI", limit=10, offset=0)
    detail = repo.get_agent_result("AI", first["result_id"])
    with repo.connection() as con:
        counts = {table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("agent_results", "agent_assertions", "agent_citations",
                                "agent_result_reviews")}
        imports = con.execute("""SELECT COUNT(*) FROM audit_log
            WHERE action='import_agent_result' AND object_id=?""",
            (first["result_id"],)).fetchone()[0]
    assert duplicate["assertions"][0]["status"] == "opinion"
    assert duplicate["original_file"] == str(raw_path)
    assert page["total"] == 1 and detail["status"] == "opinion"
    assert counts == {"agent_results": 1, "agent_assertions": 1,
                      "agent_citations": 1, "agent_result_reviews": 1}
    assert imports == 1
    assert raw_path.read_bytes() == original


def test_agent_result_index_rolls_back_when_import_audit_fails(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    record = result_record("audit-rollback")
    raw_path = write_artifact(tmp_path, "AI", record, "audit-rollback.json")
    with repo.connection() as con:
        con.execute("""CREATE TRIGGER fail_agent_import_audit
            BEFORE INSERT ON audit_log
            WHEN NEW.action='import_agent_result'
            BEGIN SELECT RAISE(ABORT, 'forced audit failure'); END""")

    with pytest.raises(sqlite3.IntegrityError, match="forced audit failure"):
        repo.index_agent_result("AI", record, str(raw_path))

    with repo.connection() as con:
        counts = {
            table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("agent_results", "agent_assertions", "agent_citations",
                          "agent_result_reviews")
        }
        imports = con.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='import_agent_result'"
        ).fetchone()[0]
    assert counts == {"agent_results": 0, "agent_assertions": 0,
                      "agent_citations": 0, "agent_result_reviews": 0}
    assert imports == 0


def test_agent_result_repository_rejects_oversized_artifact_before_json_decode(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    record = result_record("oversized-repository")
    raw_path = tmp_path / "AI" / "one_time" / "agent_results" / "oversized.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"{" + b"x" * 512_000)

    with pytest.raises(ValueError, match="500 KiB"):
        repo.index_agent_result("AI", record, str(raw_path))

    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM agent_results").fetchone()[0] == 0


def test_agent_result_repository_compares_single_bounded_replacement_snapshot(
        monkeypatch, tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    supplied = result_record("before-replacement")
    replacement = result_record("after-replacement")
    raw_path = write_artifact(tmp_path, "AI", supplied, "replace.json")
    replacement_path = write_artifact(
        tmp_path, "AI", replacement, "replacement-source.json")
    original_open = Path.open
    replaced = False

    def replacing_open(path, mode="r", *args, **kwargs):
        nonlocal replaced
        if path == raw_path.resolve() and mode == "rb" and not replaced:
            replaced = True
            os.replace(replacement_path, raw_path)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replacing_open)
    with pytest.raises(ValueError, match="does not match supplied record"):
        repo.index_agent_result("AI", supplied, str(raw_path))

    assert replaced
    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM agent_results").fetchone()[0] == 0


def test_agent_assertion_review_rolls_back_when_audit_fails(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    indexed = index_result(repo, tmp_path, "review-audit-rollback")
    assertion_id = indexed["assertions"][0]["id"]
    with repo.connection() as con:
        con.execute("""CREATE TRIGGER fail_agent_review_audit
            BEFORE INSERT ON audit_log
            WHEN NEW.action='review_agent_assertion'
            BEGIN SELECT RAISE(ABORT, 'forced review audit failure'); END""")

    with pytest.raises(sqlite3.IntegrityError, match="forced review audit failure"):
        repo.review_agent_assertion(
            "AI", assertion_id, decision="opinion", actor="tester", note="rollback")

    detail = repo.get_agent_result("AI", indexed["result_id"])
    with repo.connection() as con:
        reviews = con.execute(
            "SELECT COUNT(*) FROM agent_result_reviews WHERE assertion_id=?",
            (assertion_id,)).fetchone()[0]
        audits = con.execute("""SELECT COUNT(*) FROM audit_log
            WHERE action='review_agent_assertion' AND object_id=?""",
            (assertion_id,)).fetchone()[0]
    assert detail["status"] == "draft_review_required"
    assert detail["assertions"][0]["status"] == "draft_review_required"
    assert reviews == 0
    assert audits == 0


def test_draft_assertion_cannot_skip_directly_to_accepted(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    assertion = index_result(repo, tmp_path)["assertions"][0]
    with pytest.raises(ValueError, match="draft_review_required.*accepted"):
        repo.review_agent_assertion(
            "AI", assertion["id"], decision="accepted", actor="tester", note="skip")
    assert repo.knowledge_stats("AI")["claims"] == 0


@pytest.mark.parametrize("decision", ["candidate", "disputed", "accepted", "rejected"])
def test_human_review_rejects_verifier_only_transitions_without_side_effects(
        tmp_path, decision):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    indexed = index_result(repo, tmp_path)
    assertion_id = indexed["assertions"][0]["id"]
    repo.review_agent_assertion(
        "AI", assertion_id, decision="submitted_for_verification",
        actor="tester", note="verify")

    with pytest.raises(ValueError, match=f"submitted_for_verification.*{decision}"):
        repo.review_agent_assertion(
            "AI", assertion_id, decision=decision, actor="tester", note="wrong layer")

    detail = repo.get_agent_result("AI", indexed["result_id"])
    with repo.connection() as con:
        review_count = con.execute(
            "SELECT COUNT(*) FROM agent_result_reviews").fetchone()[0]
    assert detail["status"] == "submitted_for_verification"
    assert detail["assertions"][0]["status"] == "submitted_for_verification"
    assert review_count == 1
    assert repo.knowledge_stats("AI")["claims"] == 0


@pytest.mark.parametrize("disposition", [
    "submitted_for_verification", "opinion", "rejected",
])
def test_verifier_rejects_human_or_wrong_source_transitions_without_side_effects(
        tmp_path, disposition):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    indexed = index_result(repo, tmp_path)
    assertion_id = indexed["assertions"][0]["id"]

    with pytest.raises(ValueError, match=f"draft_review_required.*{disposition}"):
        repo.apply_assertion_verification(
            "AI", assertion_id, checks={}, disposition=disposition)

    detail = repo.get_agent_result("AI", indexed["result_id"])
    with repo.connection() as con:
        review_count = con.execute(
            "SELECT COUNT(*) FROM agent_result_reviews").fetchone()[0]
    assert detail["status"] == "draft_review_required"
    assert detail["assertions"][0]["status"] == "draft_review_required"
    assert review_count == 0
    assert repo.knowledge_stats("AI")["claims"] == 0


def test_opinion_does_not_change_knowledge_statistics(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    assertion = index_result(repo, tmp_path)["assertions"][0]
    before = repo.knowledge_stats("AI")
    reviewed = repo.review_agent_assertion(
        "AI", assertion["id"], decision="opinion", actor="tester", note="analysis")
    assert reviewed["status"] == "opinion" and reviewed["claim_id"] is None
    assert repo.knowledge_stats("AI") == before


def test_claim_is_created_and_promoted_only_for_accepted_verification(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    assertion = index_result(repo, tmp_path)["assertions"][0]
    submitted = repo.review_agent_assertion(
        "AI", assertion["id"], decision="submitted_for_verification",
        actor="tester", note="verify")
    assert submitted["claim_id"] is None
    assert repo.knowledge_stats("AI")["claims"] == 0

    with pytest.raises(ValueError, match="trusted verifier orchestration"):
        repo.apply_assertion_verification(
            "AI", assertion["id"], checks=passing_verification_checks(),
            disposition="accepted")
    assert repo.knowledge_stats("AI")["claims"] == 0


@pytest.mark.parametrize("disposition", ["candidate", "disputed", "rejected"])
def test_non_accepted_verification_never_projects_a_claim(tmp_path, disposition):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    indexed = index_result(repo, tmp_path, disposition)
    assertion_id = indexed["assertions"][0]["id"]
    repo.review_agent_assertion(
        "AI", assertion_id, decision="submitted_for_verification",
        actor="tester", note="verify")

    verified = repo.apply_assertion_verification(
        "AI", assertion_id, checks={"semantic_support": {"status": "failed"}},
        disposition=disposition)

    assert verified["status"] == disposition and verified["claim_id"] is None
    assert repo.get_agent_result("AI", indexed["result_id"])["status"] == disposition
    assert repo.knowledge_stats("AI")["claims"] == 0


def test_mid_index_failure_rolls_back_result_assertions_and_citations(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    record = result_record("rollback")
    record["assertions"].append({
        "text": "Invalid second assertion",
        "type": "identity",
        "citations": ["file:///not-http"],
    })
    raw_path = write_artifact(tmp_path, "AI", record, "rollback.json")

    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        repo.index_agent_result("AI", record, str(raw_path))

    with repo.connection() as con:
        counts = [con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("agent_results", "agent_assertions", "agent_citations",
                                "agent_result_reviews")]
    assert counts == [0, 0, 0, 0]


def test_spoofed_caller_hashes_do_not_change_substantive_idempotency(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    record = result_record("spoof")
    raw_path = write_artifact(tmp_path, "AI", record, "spoof.json")
    first = repo.index_agent_result("AI", record, str(raw_path))
    spoofed = {**record, "content_sha256": "f" * 64, "content_hash": "e" * 64,
               "result_id": "caller-controlled", "status": "accepted",
               "created_at": "2099-01-01T00:00:00+00:00", "duplicate": True,
               "path": "/caller/path", "review": {"decision": "accepted"}}

    second = repo.index_agent_result("AI", spoofed, str(raw_path))

    assert second["result_id"] == first["result_id"]
    assert second["content_sha256"] == first["content_sha256"]
    assert second["content_sha256"] not in {"e" * 64, "f" * 64}
    assert repo.list_agent_results("AI", limit=10, offset=0)["total"] == 1


def test_identical_substantive_content_uses_industry_scoped_internal_ids(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    repo.ensure_industry("Chips")
    record = result_record("shared")
    ai_path = write_artifact(tmp_path, "AI", record, "shared.json")
    chips_path = write_artifact(tmp_path, "Chips", record, "shared.json")

    ai = repo.index_agent_result("AI", record, str(ai_path))
    chips = repo.index_agent_result("Chips", record, str(chips_path))

    assert ai["result_id"] != chips["result_id"]
    assert ai["content_sha256"] == chips["content_sha256"]
    assert repo.list_agent_results("AI", limit=10, offset=0)["total"] == 1
    assert repo.list_agent_results("Chips", limit=10, offset=0)["total"] == 1


def test_existing_raw_artifact_must_match_substantive_record(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    supplied = result_record("supplied")
    raw_path = write_artifact(
        tmp_path, "AI", {**supplied, "summary": "different"}, "mismatch.json")

    with pytest.raises(ValueError, match="artifact.*record"):
        repo.index_agent_result("AI", supplied, str(raw_path))

    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM agent_results").fetchone()[0] == 0


@pytest.mark.parametrize("assertions", [
    [],
    [{"text": "   ", "citations": ["https://example.com/source"]}],
    [{"text": "No citation", "citations": []}],
    [{"text": "No valid citation", "citations": ["file:///local", "not-a-url"]}],
])
def test_invalid_empty_assertions_are_rejected_atomically(tmp_path, assertions):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    record = {**result_record("invalid"), "assertions": assertions}
    raw_path = write_artifact(tmp_path, "AI", record, "invalid.json")

    with pytest.raises(ValueError):
        repo.index_agent_result("AI", record, str(raw_path))

    with repo.connection() as con:
        counts = [con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("agent_results", "agent_assertions", "agent_citations",
                                "agent_result_reviews")]
    assert counts == [0, 0, 0, 0]


def test_canonical_equivalent_citations_are_deduplicated(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    record = result_record("citations")
    record["assertions"][0]["citations"] = [
        "https://www.example.com/source?utm_source=agent",
        "https://example.com/source?utm_medium=duplicate",
    ]
    raw_path = write_artifact(tmp_path, "AI", record, "citations.json")

    indexed = repo.index_agent_result("AI", record, str(raw_path))

    citations = indexed["assertions"][0]["citations"]
    assert len(citations) == 1
    assert citations[0]["canonical_url"] == "https://example.com/source"


def test_missing_raw_artifact_is_rejected_atomically(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    missing = tmp_path / "AI" / "one_time" / "agent_results" / "missing.json"

    with pytest.raises(ValueError, match="regular JSON file"):
        repo.index_agent_result("AI", result_record("missing"), str(missing))

    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM agent_results").fetchone()[0] == 0


def test_directory_raw_artifact_is_rejected_atomically(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    directory = tmp_path / "AI" / "one_time" / "agent_results" / "directory.json"
    directory.mkdir(parents=True)

    with pytest.raises(ValueError, match="regular JSON file"):
        repo.index_agent_result("AI", result_record("directory"), str(directory))

    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM agent_results").fetchone()[0] == 0


def test_broken_symlink_raw_artifact_is_rejected_atomically(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    broken = tmp_path / "AI" / "one_time" / "agent_results" / "broken.json"
    broken.parent.mkdir(parents=True)
    broken.symlink_to(broken.parent / "absent.json")

    with pytest.raises(ValueError, match="regular JSON file"):
        repo.index_agent_result("AI", result_record("broken"), str(broken))

    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM agent_results").fetchone()[0] == 0


def test_matching_artifact_outside_industry_directory_is_rejected_atomically(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    record = result_record("outside")
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match="managed industry directory"):
        repo.index_agent_result("AI", record, str(outside))

    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM agent_results").fetchone()[0] == 0


def test_matching_regular_artifact_inside_industry_directory_is_stored_resolved(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    record = result_record("inside")
    inside = write_artifact(tmp_path, "AI", record, "inside.json")

    indexed = repo.index_agent_result("AI", record, str(inside))

    assert indexed["original_file"] == str(inside.resolve())


def submitted_assertion(
        repo: IntelligenceRepository, tmp_path, *, suffix: str,
        assertion_type: str = "identity", citations: list[object] | None = None,
        atomic: dict | None = None, generation_call_id: str = "generation-call-1",
        ensure_subject_id: bool = True) -> tuple[str, str]:
    record = result_record(suffix)
    record["generation_call_id"] = generation_call_id
    atomic_record = dict(atomic) if atomic is not None else {
        "subject": "NVIDIA", "predicate": "identity", "object": "AI company",
        "time": "2026-09-01", "region": "US", "qualifiers": {},
    }
    if ensure_subject_id and atomic_record.get("subject"):
        entity_id = repo.upsert_entity("AI", {
            "name": str(atomic_record["subject"]), "type": "company", "country": "US",
            "status": "accepted"})
        atomic_record["subject_id"] = entity_id
    record["assertions"][0].update({
        "type": assertion_type,
        "citations": citations or ["https://sec.gov/evidence"],
        "atomic": atomic_record,
    })
    raw_path = write_artifact(tmp_path, "AI", record, f"{suffix}.json")
    indexed = repo.index_agent_result("AI", record, str(raw_path))
    assertion_id = indexed["assertions"][0]["id"]
    repo.review_agent_assertion(
        "AI", assertion_id, decision="submitted_for_verification",
        actor="tester", note="decision table")
    return indexed["result_id"], assertion_id


def evidence_probe(
        url: str, *, text: str = "NVIDIA is an AI company.",
        semantic: str = "supported", publisher_kind: str = "",
        entity_ids: tuple[str, ...] = ("ent_d04204f835586f6cbde8bf9c",),
        numeric_observations: tuple[dict, ...] = (),
        verifier_id: str = "independent-verifier",
        verifier_call_id: str = "verification-call-1") -> EvidenceProbe:
    content_hash = sha256(text.encode("utf-8")).hexdigest()
    return EvidenceProbe(
        reachable=True,
        final_url=url,
        status_code=200,
        published_at="2026-08-31T12:00:00+00:00",
        content=text,
        content_hash=content_hash,
        locator={"type": "text_offset", "start": 0, "end": len(text)},
        located_text=text,
        semantic=semantic,
        semantic_reason="independently evaluated against the located text",
        verification_method="independent_model",
        verifier_id=verifier_id,
        verifier_call_id=verifier_call_id,
        entity_ids=entity_ids,
        numeric_observations=numeric_observations,
        publisher_kind=publisher_kind,
        experimental_conditions=(("batch", "1"), ("precision", "FP16"))
        if publisher_kind == "academic_result" else (),
    )


def _verification_repo(tmp_path) -> IntelligenceRepository:
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI")
    return repo


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        ({"reachable": False, "status_code": 503}, "reachability"),
        ({"final_url": "https://unknown.invalid/evidence"}, "publisher_identity"),
        ({"published_at": ""}, "publication_time"),
        ({"entity_ids": ("ent_nvidia", "ent_other")}, "entity_alignment"),
    ],
)
def test_verification_keeps_candidate_when_foundational_evidence_gate_fails(
        tmp_path, mutation, failed_check):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix=failed_check)
    base = evidence_probe("https://sec.gov/evidence")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda _url: replace(base, **mutation))

    assert decision.disposition == "candidate"
    assert decision.claim_id is None
    assert decision.checks[failed_check]["status"] in {"failed", "unknown"}
    assert repo.knowledge_stats("AI")["claims"] == 0


def test_non_atomic_assertion_is_persisted_as_candidate_instead_of_erroring(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="missing-atomization", atomic={})

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["atomization"]["status"] == "failed"
    assert repo._get_agent_assertion("AI", assertion_id)["status"] == "candidate"
    assert repo.knowledge_stats("AI")["claims"] == 0


@pytest.mark.parametrize(
    ("semantic", "status", "disposition"),
    [
        ("supported", "passed", "accepted"),
        ("partial", "partial", "candidate"),
        ("unknown", "unknown", "candidate"),
        ("contradicted", "failed", "disputed"),
    ],
)
def test_semantic_support_decision_table(tmp_path, semantic, status, disposition):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"semantic-{semantic}")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, semantic="unknown"),
        semantic_evaluator=configured_evaluator(semantic))

    assert decision.disposition == disposition
    assert decision.checks["semantic_support"] == {
        **decision.checks["semantic_support"],
        "status": status,
        "decision": semantic,
    }
    assert bool(decision.claim_id) is (disposition == "accepted")


@pytest.mark.parametrize("locator_mutation", [
    {"locator": {}},
    {"content_hash": "0" * 64},
    {"locator": {"type": "text_offset", "start": 0, "end": 999}},
])
def test_missing_or_changed_reproducible_locator_blocks_acceptance(
        tmp_path, locator_mutation):
    repo = _verification_repo(tmp_path)
    expected_hash = sha256(b"NVIDIA is an AI company.").hexdigest()
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"locator-{len(str(locator_mutation))}",
        citations=[{
            "url": "https://sec.gov/evidence",
            "content_hash": expected_hash,
        }])
    probe = evidence_probe("https://sec.gov/evidence")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda _url: replace(probe, **locator_mutation))

    assert decision.disposition == "candidate"
    assert decision.checks["locator_integrity"]["status"] == "failed"
    assert decision.claim_id is None


NUMERIC_ATOMIC = {
    "subject": "Example Corp",
    "subject_id": "ent_example",
    "predicate": "financial_figure",
    "object": "FY2025 revenue",
    "time": "2025",
    "region": "US",
    "value": 100,
    "unit": "million",
    "currency": "USD",
    "period": "FY2025",
    "statistical_definition": "GAAP revenue",
    "qualifiers": {},
}
MATCHING_OBSERVATION = {
    "value": 100,
    "unit": "million",
    "currency": "USD",
    "period": "FY2025",
    "statistical_definition": "GAAP revenue",
}


@pytest.mark.parametrize("observation", [
    {**MATCHING_OBSERVATION, "value": -100},
    {**MATCHING_OBSERVATION, "value": 100_000},
    {**MATCHING_OBSERVATION, "unit": "billion"},
    {**MATCHING_OBSERVATION, "currency": "CNY"},
    {**MATCHING_OBSERVATION, "period": "FY2024"},
    {**MATCHING_OBSERVATION, "statistical_definition": "non-GAAP revenue"},
])
def test_numeric_sign_magnitude_unit_currency_period_and_definition_must_match(
        tmp_path, observation):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"numeric-{abs(hash(str(observation)))}",
        assertion_type="financial", atomic=NUMERIC_ATOMIC)

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, text="Example Corp reported FY2025 GAAP revenue.",
            entity_ids=("ent_example",), publisher_kind="regulatory_filing",
            numeric_observations=(observation,)),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["numeric_consistency"]["status"] == "failed"
    assert decision.claim_id is None


def test_auditable_numeric_conversion_can_pass(tmp_path):
    repo = _verification_repo(tmp_path)
    support_url = "https://sec.gov/Archives/edgar/data/1/filing"
    benchmark_url = "https://sec.gov/exchange-rate"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="numeric-conversion",
        assertion_type="financial", atomic=NUMERIC_ATOMIC,
        citations=[{"url": support_url, "role": "support"},
                   {"url": benchmark_url, "role": "conversion_benchmark"}])
    converted = {
        "value": 90,
        "unit": "million",
        "currency": "EUR",
        "period": "FY2025",
        "statistical_definition": "GAAP revenue",
        "conversion": {
            "original_value": 90,
            "target_value": 100,
            "target_unit": "million",
            "target_currency": "USD",
            "formula": "multiply",
            "rate": "1.111111111111111111",
            "benchmark_source": benchmark_url,
        },
    }

    probes = {
        support_url: evidence_probe(
            support_url, text="Example Corp reported FY2025 GAAP revenue.",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            publisher_kind="regulatory_filing", numeric_observations=(converted,)),
        benchmark_url: evidence_probe(
            benchmark_url, text=("EUR to USD multiply rate 1.111111111111111111; "
                                 "million to million; FY2025; tolerance 0.000001"),
            entity_ids=(),
            numeric_observations=({"kind": "conversion_rate",
                "rate": "1.111111111111111111", "formula": "multiply",
                "from_currency": "EUR", "to_currency": "USD",
                "from_unit": "million", "to_unit": "million",
                "period": "FY2025", "tolerance": "0.000001"},)),
    }
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=probes.__getitem__,
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "accepted"
    assert decision.checks["numeric_consistency"]["status"] == "passed"
    conversion = decision.checks["numeric_consistency"]["conversions"][0]
    assert conversion["original_value"] == 90
    assert conversion["target_value"] == 100
    assert conversion["benchmark_source"] == "https://sec.gov/exchange-rate"


def test_conversion_without_located_tolerance_records_zero_and_stays_candidate(tmp_path):
    repo = _verification_repo(tmp_path)
    support_url = "https://sec.gov/filing"
    benchmark_url = "https://sec.gov/exchange-rate-no-tolerance"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="numeric-conversion-no-tolerance",
        assertion_type="financial", atomic=NUMERIC_ATOMIC,
        citations=[{"url": support_url, "role": "support"},
                   {"url": benchmark_url, "role": "conversion_benchmark"}])
    converted = {
        **MATCHING_OBSERVATION, "value": 90, "currency": "EUR",
        "conversion": {
            "original_value": 90, "target_value": 100,
            "target_unit": "million", "target_currency": "USD",
            "formula": "multiply", "rate": "1.111111111111111111",
            "benchmark_source": benchmark_url,
        },
    }
    benchmark = {
        "kind": "conversion_rate", "rate": "1.111111111111111111",
        "formula": "multiply", "from_currency": "EUR", "to_currency": "USD",
        "from_unit": "million", "to_unit": "million", "period": "FY2025",
    }
    probes = {
        support_url: evidence_probe(
            support_url, text="Example Corp reported FY2025 GAAP revenue.",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            publisher_kind="regulatory_filing", numeric_observations=(converted,)),
        benchmark_url: evidence_probe(
            benchmark_url,
            text="EUR to USD multiply rate 1.111111111111111111; million to million; FY2025",
            entity_ids=(), numeric_observations=(benchmark,)),
    }

    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=probes.__getitem__,
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    numeric = decision.checks["numeric_consistency"]
    assert numeric["status"] in {"failed", "partial"}
    assert numeric["conversions"] == [{
        "benchmark_source": benchmark_url,
        "tolerance": "0",
        "tolerance_status": "default_unverified",
    }]


@pytest.mark.parametrize(
    ("assertion_type", "urls", "publisher_kind", "expected"),
    [
        ("identity", ["https://sec.gov/a"], "official_record", "accepted"),
        ("event", ["https://sec.gov/a"], "direct_first_party", "candidate"),
        ("event", ["https://reuters.com/a"], "news_report", "candidate"),
        ("event", ["https://reuters.com/a", "https://bloomberg.com/b"], "news_report", "accepted"),
        ("market_size", ["https://reuters.com/a"], "market_estimate", "candidate"),
        ("market_size", ["https://reuters.com/a", "https://bloomberg.com/b"], "market_estimate", "candidate"),
        ("financial", ["https://sec.gov/a"], "regulatory_filing", "candidate"),
        ("technical_performance", ["https://nature.com/a"], "academic_result", "accepted"),
        ("unspecified", ["https://reuters.com/a", "https://bloomberg.com/b"], "news_report", "candidate"),
    ],
)
def test_claim_type_corroboration_policy(
        tmp_path, assertion_type, urls, publisher_kind, expected):
    repo = _verification_repo(tmp_path)
    atomic = {
        "subject": "NVIDIA", "predicate": assertion_type,
        "object": "observable assertion", "time": "2026-09-01",
        "region": "US", "qualifiers": {},
    }
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"policy-{assertion_type}-{len(urls)}-{publisher_kind}",
        assertion_type=assertion_type, citations=urls, atomic=atomic)
    if assertion_type == "event" and publisher_kind == "direct_first_party" \
            and len(urls) == 1:
        with repo.transaction() as con:
            subject_id = con.execute(
                "SELECT json_extract(record_json,'$.assertions[0].atomic.subject_id') "
                "FROM agent_results WHERE id=(SELECT result_id FROM agent_assertions WHERE id=?)",
                (assertion_id,)).fetchone()[0]
            metadata = json.loads(con.execute(
                "SELECT metadata_json FROM entities WHERE id=?", (subject_id,)
                ).fetchone()[0])
            metadata["official_domains"] = ["sec.gov"]
            con.execute("UPDATE entities SET metadata_json=? WHERE id=?",
                        (json.dumps(metadata), subject_id))
    probes = {url: replace(evidence_probe(
        url, text=("NVIDIA observable assertion; batch=1, precision=FP16."
                   if assertion_type == "technical_performance"
                   else "NVIDIA observable assertion."),
        publisher_kind=publisher_kind),
        experimental_conditions=(("batch", "1"), ("precision", "FP16"))
        if assertion_type == "technical_performance" else ())
        for url in urls}

    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=probes.__getitem__,
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == expected
    corroboration_should_pass = (
        expected == "accepted" or assertion_type == "unspecified" or
        (assertion_type == "market_size" and len(urls) >= 2))
    expected_status = "passed" if corroboration_should_pass else "failed"
    assert decision.checks["corroboration"]["status"] == expected_status
    if expected == "candidate" and assertion_type in {"market_size", "financial"}:
        assert decision.checks["numeric_consistency"]["status"] == "failed"


def test_common_ownership_does_not_count_as_independent_corroboration(tmp_path):
    repo = _verification_repo(tmp_path)
    urls = ["https://reuters.com/a", "https://reutersagency.com/b"]
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="common-owner", assertion_type="market_size",
        citations=urls, atomic={
            "subject": "NVIDIA", "predicate": "market_size",
            "object": "market reached a threshold", "time": "2026",
            "region": "global", "qualifiers": {},
        })

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, text="NVIDIA market reached a threshold."),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["corroboration"]["independent_clusters"] == ["reuters"]
    assert decision.checks["corroboration"]["status"] == "failed"


@pytest.mark.parametrize("assertion_type", [
    "causal", "forecast", "investment_judgment", "opinion",
])
def test_judgment_types_are_never_automatically_promoted(tmp_path, assertion_type):
    repo = _verification_repo(tmp_path)
    urls = ["https://reuters.com/a", "https://bloomberg.com/b"]
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"judgment-{assertion_type}",
        assertion_type=assertion_type, citations=urls,
        atomic={
            "subject": "NVIDIA", "predicate": assertion_type,
            "object": "a judgment", "time": "2026", "region": "global",
            "qualifiers": {},
        })

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, text="NVIDIA judgment evidence."),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["type_policy"]["status"] == "failed"
    assert decision.claim_id is None


def test_generation_call_cannot_be_its_own_only_semantic_judge(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="self-judging", generation_call_id="same-call")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, verifier_id="test-agent", verifier_call_id="same-call"),
        semantic_evaluator=configured_evaluator(
            evaluator_id="test-agent", call_id="same-call"))

    assert decision.disposition == "candidate"
    assert decision.checks["verifier_independence"]["status"] == "failed"
    assert decision.checks["semantic_support"]["status"] == "unknown"


def test_conflict_with_existing_accepted_claim_enters_disputed(tmp_path):
    repo = _verification_repo(tmp_path)
    entity_id = repo.upsert_entity("AI", {
        "name": "Example Corp", "type": "company", "country": "US",
        "status": "accepted",
    })
    accepted_claim_id = repo.upsert_claim(
        "AI", "market_share", {"value": 40, "unit": "%"},
        subject_id=entity_id,
        qualifiers={"period": "2025", "statistical_definition": "global revenue"},
        status="accepted")
    urls = ["https://reuters.com/a", "https://bloomberg.com/b"]
    atomic = {
        "subject": "Example Corp", "subject_id": entity_id,
        "predicate": "market_share", "object": {"value": 50, "unit": "%"},
        "time": "2025", "region": "global", "value": 50, "unit": "%",
        "period": "2025", "statistical_definition": "global revenue",
        "qualifiers": {},
    }
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="accepted-conflict", assertion_type="market_share",
        citations=urls, atomic=atomic)
    observation = {
        "value": 50, "unit": "%", "currency": "", "period": "2025",
        "statistical_definition": "global revenue",
    }

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, text="Example Corp has 50% global revenue share.",
            entity_ids=(entity_id,), numeric_observations=(observation,)),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "disputed"
    assert decision.checks["conflict"]["status"] == "failed"
    assert decision.checks["conflict"]["conflicting_claim_ids"] == [accepted_claim_id]
    conflict_group_id = decision.checks["conflict"]["conflict_group_id"]
    assert conflict_group_id.startswith("cfg_")
    assert decision.checks["conflict"]["conflict_group_members"] == {
        "accepted_claim_ids": [accepted_claim_id],
        "disputed_assertion_ids": [assertion_id],
    }
    assert decision.claim_id is None

    second_atomic = {
        **atomic, "object": {"value": 60, "unit": "%"}, "value": 60,
    }
    _, second_assertion_id = submitted_assertion(
        repo, tmp_path, suffix="accepted-conflict-second",
        assertion_type="market_share", citations=urls, atomic=second_atomic)
    second_observation = {**observation, "value": 60}
    second = verify_agent_assertion(
        repo, "AI", second_assertion_id,
        fetch=lambda url: evidence_probe(
            url, text="Example Corp has 60% global revenue share.",
            entity_ids=(entity_id,), numeric_observations=(second_observation,)),
        semantic_evaluator=configured_evaluator())

    assert second.disposition == "disputed"
    assert second.checks["conflict"]["conflict_group_id"] == conflict_group_id
    assert second.checks["conflict"]["conflict_group_members"] == {
        "accepted_claim_ids": [accepted_claim_id],
        "disputed_assertion_ids": [second_assertion_id],
    }
    with repo.connection() as con:
        accepted = con.execute(
            "SELECT status FROM claims WHERE id=?", (accepted_claim_id,)).fetchone()
        claim_count = con.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        stored = con.execute(
            "SELECT verification_json FROM agent_assertions WHERE id=?",
            (second_assertion_id,)).fetchone()[0]
        audit = con.execute("""SELECT details_json FROM audit_log
            WHERE action='verify_agent_assertion' AND object_id=?""",
            (second_assertion_id,)).fetchone()[0]
    assert accepted["status"] == "accepted" and claim_count == 1
    assert json.loads(stored)["conflict"]["conflict_group_id"] == conflict_group_id
    assert json.loads(audit)["conflict_group_id"] == conflict_group_id


def test_repeated_verification_is_idempotent_and_does_not_refetch(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="idempotent")
    first = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())

    def must_not_refetch(_url):
        raise AssertionError("completed verification must be returned from storage")

    second = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=must_not_refetch)
    with repo.connection() as con:
        review_count = con.execute(
            "SELECT COUNT(*) FROM agent_result_reviews WHERE assertion_id=?",
            (assertion_id,)).fetchone()[0]
        claim_count = con.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

    assert second == first
    assert review_count == 2  # one human submission plus one verifier transition
    assert claim_count == 1


def test_candidate_observations_are_not_labeled_as_verified_facts(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="candidate-label")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, semantic="unknown"),
        semantic_evaluator=configured_evaluator("partial"))

    assert decision.disposition == "candidate"
    with repo.connection() as con:
        document = con.execute("""SELECT d.content_hash,x.review_status,x.credibility
            FROM documents d JOIN industry_documents x ON x.document_id=d.id
            WHERE x.industry_id=? AND x.category='agent_evidence'""",
            (repo.industry_id("AI"),)).fetchone()
        citation = con.execute(
            "SELECT reachability,document_id FROM agent_citations WHERE assertion_id=?",
            (assertion_id,)).fetchone()
    assert document["content_hash"]
    assert document["review_status"] == "evidence_observed"
    assert document["credibility"] == "collected"
    assert citation["reachability"] == "reachable" and citation["document_id"]
    assert repo.knowledge_stats("AI")["claims"] == 0


@pytest.mark.parametrize("blocking_status", [
    "failed", "partial", "unknown", "not_applicable",
])
def test_repository_refuses_accepted_projection_with_any_blocking_check(
        tmp_path, blocking_status):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"defensive-{blocking_status}")
    checks = {
        "atomization": {"status": "passed"},
        "semantic_support": {"status": blocking_status},
    }

    with pytest.raises(ValueError, match="trusted verifier orchestration"):
        repo.apply_assertion_verification(
            "AI", assertion_id, checks=checks, disposition="accepted")

    assertion = repo._get_agent_assertion("AI", assertion_id)
    assert assertion["status"] == "submitted_for_verification"
    assert assertion["claim_id"] is None
    assert repo.knowledge_stats("AI")["claims"] == 0


def test_repository_refuses_accepted_projection_when_required_checks_are_missing(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="defensive-missing")

    with pytest.raises(ValueError, match="trusted verifier orchestration"):
        repo.apply_assertion_verification(
            "AI", assertion_id,
            checks={"semantic_support": {"status": "passed"}},
            disposition="accepted")

    assert repo._get_agent_assertion("AI", assertion_id)["status"] == \
        "submitted_for_verification"
    assert repo.knowledge_stats("AI")["claims"] == 0


def test_repository_refuses_accepted_projection_from_non_supporting_evidence(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="defensive-relation")
    checks = passing_verification_checks()
    checks["fact_projection"]["evidence"][0]["url"] = "https://sec.gov/evidence"
    checks["fact_projection"]["evidence"][0]["relation"] = "contradicts"

    with pytest.raises(ValueError, match="trusted verifier orchestration"):
        repo.apply_assertion_verification(
            "AI", assertion_id, checks=checks, disposition="accepted")

    assert repo._get_agent_assertion("AI", assertion_id)["status"] == \
        "submitted_for_verification"
    assert repo.knowledge_stats("AI")["claims"] == 0


def test_fact_projection_and_verifier_review_are_atomic(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="atomic-promotion")
    with repo.connection() as con:
        con.execute("""CREATE TRIGGER fail_verifier_review
            BEFORE INSERT ON agent_result_reviews
            WHEN NEW.actor='assertion-verifier'
            BEGIN SELECT RAISE(ABORT, 'forced verifier review failure'); END""")

    with pytest.raises(sqlite3.IntegrityError, match="forced verifier review failure"):
        verify_agent_assertion(
            repo, "AI", assertion_id,
            fetch=lambda url: evidence_probe(url),
            semantic_evaluator=configured_evaluator())

    assertion = repo._get_agent_assertion("AI", assertion_id)
    assert assertion["status"] == "submitted_for_verification"
    assert assertion["claim_id"] is None
    assert repo.knowledge_stats("AI")["claims"] == 0


def configured_evaluator(
        decision: str = "supported", *, evaluator_id: str = "independent-verifier",
        method: str = "independent_model", call_id: str = "verification-call-1"):
    def evaluate(request):
        return [SemanticEvaluation(
            evidence_id=item.evidence_id,
            decision=decision,
            reason=f"{decision} by configured evaluator",
            content_hash=item.content_hash,
            locator=item.locator,
            evaluator_call_id=call_id,
            assertion_type=agent_evidence_module._normalized_type(
                str(request.atomic.get("predicate") or "")),
        ) for item in request.evidence if item.role == "support"]

    return ConfiguredSemanticEvaluator(
        evaluator_id=evaluator_id, method=method, evaluate=evaluate)


def test_unconfigured_semantic_verifier_returns_actionable_candidate(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="unconfigured-evaluator",
        generation_call_id="generation-call-1")
    probe = evidence_probe("https://sec.gov/evidence", semantic="supported")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda _url: probe,
        semantic_evaluator=None)

    assert decision.disposition == "candidate"
    assert decision.checks["semantic_support"]["status"] == "unknown"
    assert "configure" in decision.checks["semantic_support"]["reason"].casefold()
    assert decision.claim_id is None


def test_explicit_verifier_orchestration_can_promote_without_probe_self_scoring(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="configured-evaluator",
        generation_call_id="generation-call-1")
    probe = replace(
        evidence_probe("https://sec.gov/evidence"),
        semantic="unknown", verification_method="", verifier_id="")
    verifier = AssertionVerifier(
        fetch=lambda _url: probe,
        semantic_evaluator=configured_evaluator())

    decision = verifier.verify(repo, "AI", assertion_id)

    assert decision.disposition == "accepted"
    assert decision.checks["semantic_support"]["decision"] == "supported"
    assert decision.checks["verifier_independence"]["status"] == "passed"


@pytest.mark.parametrize(("evaluator_id", "call_id", "method"), [
    ("test-agent", "different-call", "human"),
    ("independent-verifier", "generation-call-1", "deterministic"),
    ("test-agent", "generation-call-1", "independent_model"),
])
def test_same_generator_or_call_is_never_an_independent_semantic_judge(
        tmp_path, evaluator_id, call_id, method):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"same-origin-{method}-{evaluator_id}",
        generation_call_id="generation-call-1")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, semantic="unknown"),
        semantic_evaluator=configured_evaluator(
            evaluator_id=evaluator_id, call_id=call_id, method=method))

    assert decision.disposition == "candidate"
    assert decision.checks["verifier_independence"]["status"] == "failed"


def test_missing_generation_call_id_blocks_fact_promotion(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="missing-generation-call", generation_call_id="")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, semantic="unknown"),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["generation_provenance"]["status"] == "failed"


@pytest.mark.parametrize("atomic_mutation", [
    {"value": None, "object": {"value": 100}, "unit": "", "period": ""},
    {"value": None, "object": "Revenue was 100"},
    {"value": None, "qualifiers": {"value": 100}, "unit": "", "period": ""},
    {"value": 100, "unit": "", "currency": "USD"},
    {"value": 100, "unit": "million", "currency": "", "period": "FY2025"},
    {"value": 100, "unit": "million", "currency": "USD", "period": ""},
    {"value": 100, "unit": "million", "currency": "USD",
     "period": "FY2025", "statistical_definition": ""},
])
def test_numeric_claims_in_any_structured_location_require_complete_schema(
        tmp_path, atomic_mutation):
    repo = _verification_repo(tmp_path)
    atomic = {**NUMERIC_ATOMIC, **atomic_mutation}
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"numeric-schema-{abs(hash(str(atomic_mutation)))}",
        assertion_type="financial", atomic=atomic,
        generation_call_id="generation-call-1")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, text="Example Corp reported revenue 100.",
            entity_ids=("ent_example",), publisher_kind="regulatory_filing",
            numeric_observations=(MATCHING_OBSERVATION,), semantic="unknown"),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["numeric_consistency"]["status"] == "failed"
    assert "structured" in decision.checks["numeric_consistency"]["reason"]


def test_conversion_requires_second_locatable_benchmark_evidence(tmp_path):
    repo = _verification_repo(tmp_path)
    support_url = "https://sec.gov/filing"
    benchmark_url = "https://sec.gov/rate"
    citations = [
        {"url": support_url, "role": "support"},
        {"url": benchmark_url, "role": "conversion_benchmark"},
    ]
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="conversion-second-evidence",
        assertion_type="financial", atomic=NUMERIC_ATOMIC,
        citations=citations, generation_call_id="generation-call-1")
    conversion = {
        "value": 90, "unit": "million", "currency": "EUR",
        "period": "FY2025", "statistical_definition": "GAAP revenue",
        "conversion": {
            "original_value": 90, "target_value": 100,
            "target_unit": "million", "target_currency": "USD",
            "formula": "multiply", "rate": "1.111111111111111111",
            "benchmark_source": benchmark_url,
        },
    }
    support = evidence_probe(
        support_url, text="Example Corp reported FY2025 GAAP revenue.",
        entity_ids=("ent_example",), publisher_kind="regulatory_filing",
        numeric_observations=(conversion,), semantic="unknown")
    missing_benchmark = replace(
        evidence_probe(benchmark_url, text="unrelated benchmark page", semantic="unknown"),
        numeric_observations=({
            "kind": "conversion_rate", "rate": "1.111111111111111111",
            "formula": "multiply", "period": "FY2025",
        },))

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch={support_url: support, benchmark_url: missing_benchmark}.__getitem__,
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["numeric_consistency"]["status"] == "failed"
    assert "benchmark" in decision.checks["numeric_consistency"]["reason"]


def test_conversion_rejects_excessive_tolerance_even_with_benchmark(tmp_path):
    repo = _verification_repo(tmp_path)
    support_url = "https://sec.gov/filing"
    benchmark_url = "https://sec.gov/rate"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="conversion-wide-tolerance",
        assertion_type="financial", atomic=NUMERIC_ATOMIC,
        citations=[{"url": support_url, "role": "support"},
                   {"url": benchmark_url, "role": "conversion_benchmark"}],
        generation_call_id="generation-call-1")
    conversion = {
        **MATCHING_OBSERVATION, "value": 90, "currency": "EUR",
        "conversion": {
            "original_value": 90, "target_value": 100,
            "target_unit": "million", "target_currency": "USD",
            "formula": "multiply", "rate": "1.111111111111111111",
            "benchmark_source": benchmark_url,
        },
    }
    benchmark_text = "1.111111111111111111"
    probes = {
        support_url: evidence_probe(
            support_url, text="Example Corp reported FY2025 GAAP revenue.",
            entity_ids=("ent_example",), publisher_kind="regulatory_filing",
            numeric_observations=(conversion,), semantic="unknown"),
        benchmark_url: replace(
            evidence_probe(benchmark_url, text=benchmark_text, semantic="unknown"),
            numeric_observations=({
                "kind": "conversion_rate", "rate": "1.111111111111111111",
                "formula": "multiply", "from_currency": "EUR",
                "to_currency": "USD", "from_unit": "million",
                "to_unit": "million", "period": "FY2025", "tolerance": "50",
            },)),
    }

    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=probes.__getitem__,
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert "tolerance" in decision.checks["numeric_consistency"]["reason"]


@pytest.mark.parametrize(("probe", "expected_status"), [
    (EvidenceProbe(
        True, "https://sec.gov/html", 200,
        published_at="2026-08-31T12:00:00+00:00",
        content='<div id="evidence"><b>NVIDIA</b> is an AI company.</div>',
        content_hash=sha256(
            '<div id="evidence"><b>NVIDIA</b> is an AI company.</div>'.encode()).hexdigest(),
        locator={"type": "html_selector", "selector": "#evidence"},
        located_text="NVIDIA is an AI company.", entity_ids=("ent_nvidia",)), "passed"),
    (EvidenceProbe(
        True, "https://sec.gov/pdf", 200,
        published_at="2026-08-31T12:00:00+00:00",
        content="page one\fNVIDIA is an AI company.",
        content_hash=sha256("page one\fNVIDIA is an AI company.".encode()).hexdigest(),
        locator={"type": "pdf_page", "page": 2, "start": 0, "end": 24},
        located_text="NVIDIA is an AI company.",
        page_texts=("page one", "NVIDIA is an AI company."),
        entity_ids=("ent_nvidia",)), "passed"),
    (EvidenceProbe(
        True, "https://sec.gov/api", 200,
        published_at="2026-08-31T12:00:00+00:00",
        content='{"data":{"statement":"NVIDIA is an AI company."}}',
        content_hash=sha256(
            '{"data":{"statement":"NVIDIA is an AI company."}}'.encode()).hexdigest(),
        locator={"type": "api_field", "path": "/data/statement"},
        located_text="NVIDIA is an AI company.", entity_ids=("ent_nvidia",)), "passed"),
])
def test_locator_types_are_actually_resolved_against_source_content(
        tmp_path, probe, expected_status):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"locator-real-{probe.locator['type']}",
        citations=[probe.final_url], generation_call_id="generation-call-1")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda _url: probe,
        semantic_evaluator=configured_evaluator())

    assert decision.checks["locator_integrity"]["status"] == expected_status


@pytest.mark.parametrize("probe", [
    EvidenceProbe(
        True, "https://sec.gov/pdf-bad", 200,
        published_at="2026-08-31T12:00:00+00:00",
        content="wrong page\fNVIDIA is an AI company.",
        content_hash=sha256("wrong page\fNVIDIA is an AI company.".encode()).hexdigest(),
        locator={"type": "pdf_page", "page": 1, "start": 0, "end": 24},
        located_text="NVIDIA is an AI company.",
        page_texts=("wrong page", "NVIDIA is an AI company."),
        entity_ids=("ent_d04204f835586f6cbde8bf9c",)),
    EvidenceProbe(
        True, "https://sec.gov/api-bad", 200,
        published_at="2026-08-31T12:00:00+00:00",
        content='{"data":{"other":"NVIDIA is an AI company."}}',
        content_hash=sha256(
            '{"data":{"other":"NVIDIA is an AI company."}}'.encode()).hexdigest(),
        locator={"type": "api_field", "path": "/data/statement"},
        located_text="NVIDIA is an AI company.",
        entity_ids=("ent_d04204f835586f6cbde8bf9c",)),
])
def test_pdf_page_and_api_field_locators_reject_wrong_coordinates(tmp_path, probe):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"locator-negative-{probe.locator['type']}",
        citations=[probe.final_url], generation_call_id="generation-call-1")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda _url: probe,
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["locator_integrity"]["status"] == "failed"


@pytest.mark.parametrize(("declared_type", "classification_status"), [
    ("unknown_type", "failed"), ("forecast_estimate", "failed"),
    ("identity", "failed"),
])
def test_assertion_type_is_controlled_and_consistent_with_predicate_and_text(
        tmp_path, declared_type, classification_status):
    repo = _verification_repo(tmp_path)
    atomic = {
        "subject": "NVIDIA", "predicate": "forecast_estimate",
        "object": "Revenue will increase next year", "time": "2027",
        "region": "US", "qualifiers": {},
    }
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"type-{declared_type}",
        assertion_type=declared_type, atomic=atomic,
        generation_call_id="generation-call-1")

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, text="NVIDIA revenue will increase next year.", semantic="unknown"),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["type_classification"]["status"] == classification_status
    assert decision.checks["type_policy"]["status"] == "failed"


def test_missing_subject_id_cannot_skip_conflict_scope(tmp_path):
    repo = _verification_repo(tmp_path)
    atomic = {
        "subject": "NVIDIA", "predicate": "identity", "object": "AI company",
        "time": "2026-09-01", "region": "US", "qualifiers": {},
    }
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="missing-subject-id", atomic=atomic,
        generation_call_id="generation-call-1", ensure_subject_id=False)

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, semantic="unknown"),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "candidate"
    assert decision.checks["conflict"]["status"] == "unknown"
    assert "subject_id" in decision.checks["conflict"]["reason"]


def test_structured_numeric_conflict_is_detected_across_object_and_qualifiers(tmp_path):
    repo = _verification_repo(tmp_path)
    entity_id = repo.upsert_entity("AI", {
        "name": "Example Corp", "type": "company", "country": "US",
        "status": "accepted"})
    repo.upsert_claim(
        "AI", "financial_figure", {"label": "revenue"}, subject_id=entity_id,
        qualifiers={"value": 100, "unit": "million", "currency": "USD",
                    "period": "FY2025", "statistical_definition": "GAAP revenue"},
        status="accepted")
    atomic = {**NUMERIC_ATOMIC, "subject_id": entity_id,
              "object": {"label": "revenue"}, "value": 101}
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="structured-conflict", assertion_type="financial",
        atomic=atomic, generation_call_id="generation-call-1")
    observation = {**MATCHING_OBSERVATION, "value": 101}

    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, text="Example Corp reported FY2025 GAAP revenue.",
            entity_ids=(entity_id,), publisher_kind="regulatory_filing",
            numeric_observations=(observation,), semantic="unknown"),
        semantic_evaluator=configured_evaluator())

    assert decision.disposition == "disputed"
    assert decision.checks["conflict"]["conflicting_claim_ids"]


def test_document_snapshots_are_content_addressed_and_candidate_cannot_downgrade(
        tmp_path):
    repo = _verification_repo(tmp_path)
    entity_id = repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US",
        "status": "accepted"})
    url = "https://sec.gov/versioned"
    atomic = {
        "subject": "NVIDIA", "subject_id": entity_id, "predicate": "identity",
        "object": "AI company", "time": "2026", "region": "US", "qualifiers": {},
    }
    _, first_id = submitted_assertion(
        repo, tmp_path, suffix="snapshot-first", atomic=atomic, citations=[url],
        generation_call_id="generation-call-1")
    first_text = "NVIDIA is an AI company. version one"
    first = verify_agent_assertion(
        repo, "AI", first_id,
        fetch=lambda _url: evidence_probe(url, text=first_text,
                                          entity_ids=(entity_id,), semantic="unknown"),
        semantic_evaluator=configured_evaluator())
    assert first.disposition == "accepted"

    _, second_id = submitted_assertion(
        repo, tmp_path, suffix="snapshot-second", atomic=atomic, citations=[url],
        generation_call_id="generation-call-2")
    second_text = "NVIDIA is an AI company. version two"
    second = verify_agent_assertion(
        repo, "AI", second_id,
        fetch=lambda _url: evidence_probe(url, text=second_text,
                                          entity_ids=(entity_id,), semantic="unknown"),
        semantic_evaluator=configured_evaluator("partial"))
    assert second.disposition == "candidate"

    with repo.connection() as con:
        snapshots = [dict(row) for row in con.execute("""SELECT content_hash,status
            FROM document_snapshots ORDER BY content_hash""")]
        sources = con.execute("""SELECT COUNT(DISTINCT d.source_id)
            FROM document_snapshots s JOIN documents d ON d.id=s.document_id
            WHERE d.source_id IS NOT NULL""").fetchone()[0]
    assert {row["content_hash"] for row in snapshots} == {
        sha256(first_text.encode()).hexdigest(), sha256(second_text.encode()).hexdigest()}
    assert sorted(row["status"] for row in snapshots) == ["observed", "verified"]
    assert sources == 1


def test_repository_rejects_forged_passed_checks_and_fake_hash(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="forged-checks", generation_call_id="generation-call-1")
    checks = passing_verification_checks()
    checks["semantic_support"] = {"status": "passed"}
    checks["fact_projection"]["evidence"][0].update({
        "url": "https://sec.gov/evidence", "content_hash": "g" * 64,
        "content": "different content", "citation_id": "not-a-real-citation",
    })

    with pytest.raises(ValueError, match="trusted verifier orchestration"):
        repo.apply_assertion_verification(
            "AI", assertion_id, checks=checks, disposition="accepted")

    assert repo._get_agent_assertion("AI", assertion_id)["status"] == \
        "submitted_for_verification"


def test_accepted_evidence_links_governed_source_and_immutable_snapshot(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="governed-source", generation_call_id="generation-call-1")
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, semantic="unknown"),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "accepted"

    with repo.connection() as con:
        row = con.execute("""SELECT c.source_id,c.snapshot_id,e.snapshot_id AS evidence_snapshot,
            s.content_hash,s.status,p.owner_cluster
            FROM agent_citations c
            JOIN document_snapshots s ON s.id=c.snapshot_id
            JOIN documents d ON d.id=s.document_id
            JOIN source_publishers sp ON sp.source_id=d.source_id
            JOIN publishers p ON p.id=sp.publisher_id
            JOIN evidence e ON e.claim_id=?
            WHERE c.assertion_id=?""", (decision.claim_id, assertion_id)).fetchone()
    assert row["source_id"] and row["snapshot_id"] == row["evidence_snapshot"]
    assert row["status"] == "verified" and row["owner_cluster"] == "us-government"


def test_unconfigured_verification_remains_retryable_then_promotes_when_configured(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="retryable-evaluator",
        generation_call_id="generation-call-1")
    probe = evidence_probe("https://sec.gov/evidence", semantic="unknown")

    pending = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda _url: probe,
        semantic_evaluator=None)
    assert pending.disposition == "candidate"
    assert pending.checks["semantic_support"]["retryable"] is True
    assert repo._get_agent_assertion("AI", assertion_id)["status"] == \
        "submitted_for_verification"

    accepted = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda _url: probe,
        semantic_evaluator=configured_evaluator())
    assert accepted.disposition == "accepted"
    assert repo._get_agent_assertion("AI", assertion_id)["status"] == "accepted"

    repeated = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda _url: (_ for _ in ()).throw(AssertionError("must not refetch")),
        semantic_evaluator=configured_evaluator())
    assert repeated == accepted


@pytest.mark.parametrize("benchmark_mutation", [
    {"from_currency": "CNY"}, {"to_currency": "CNY"},
    {"from_unit": "billion"}, {"to_unit": "billion"},
    {"period": "FY2024"},
])
def test_conversion_benchmark_binds_currency_unit_and_period(
        tmp_path, benchmark_mutation):
    repo = _verification_repo(tmp_path)
    support_url, benchmark_url = "https://sec.gov/filing", "https://sec.gov/rate"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"conversion-binding-{abs(hash(str(benchmark_mutation)))}",
        assertion_type="financial", atomic=NUMERIC_ATOMIC,
        citations=[{"url": support_url, "role": "support"},
                   {"url": benchmark_url, "role": "conversion_benchmark"}])
    conversion = {
        **MATCHING_OBSERVATION, "value": 90, "currency": "EUR",
        "conversion": {"original_value": 90, "target_value": 100,
            "target_unit": "million", "target_currency": "USD",
            "formula": "multiply", "rate": "1.111111111111111111",
            "benchmark_source": benchmark_url},
    }
    benchmark = {"kind": "conversion_rate", "rate": "1.111111111111111111",
        "formula": "multiply", "from_currency": "EUR", "to_currency": "USD",
        "from_unit": "million", "to_unit": "million", "period": "FY2025",
        "tolerance": "0.000001", **benchmark_mutation}
    probes = {
        support_url: evidence_probe(
            support_url, text="Example Corp reported FY2025 GAAP revenue.",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            publisher_kind="regulatory_filing", numeric_observations=(conversion,)),
        benchmark_url: evidence_probe(
            benchmark_url, text="1.111111111111111111", entity_ids=(),
            numeric_observations=(benchmark,)),
    }
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=probes.__getitem__,
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["numeric_consistency"]["status"] == "failed"


def test_conversion_tolerance_must_come_from_located_benchmark(tmp_path):
    repo = _verification_repo(tmp_path)
    support_url, benchmark_url = "https://sec.gov/filing", "https://sec.gov/rate"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="conversion-untrusted-tolerance",
        assertion_type="financial", atomic=NUMERIC_ATOMIC,
        citations=[{"url": support_url, "role": "support"},
                   {"url": benchmark_url, "role": "conversion_benchmark"}])
    conversion = {
        **MATCHING_OBSERVATION, "value": 90, "currency": "EUR",
        "conversion": {"original_value": 90, "target_value": 100.5,
            "target_unit": "million", "target_currency": "USD",
            "formula": "multiply", "rate": "1.111111111111111111",
            "benchmark_source": benchmark_url, "tolerance": "1"},
    }
    benchmark = {"kind": "conversion_rate", "rate": "1.111111111111111111",
        "formula": "multiply", "from_currency": "EUR", "to_currency": "USD",
        "from_unit": "million", "to_unit": "million", "period": "FY2025"}
    probes = {
        support_url: evidence_probe(
            support_url, text="Example Corp reported FY2025 GAAP revenue.",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            publisher_kind="regulatory_filing", numeric_observations=(conversion,)),
        benchmark_url: evidence_probe(
            benchmark_url, text="1.111111111111111111", entity_ids=(),
            numeric_observations=(benchmark,)),
    }
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=probes.__getitem__,
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert "tolerance" in decision.checks["numeric_consistency"]["reason"]


def test_conversion_metadata_is_rejected_when_bindings_are_absent_from_excerpt(tmp_path):
    repo = _verification_repo(tmp_path)
    support_url, benchmark_url = "https://sec.gov/filing", "https://sec.gov/rate"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="conversion-unlocated-bindings",
        assertion_type="financial", atomic=NUMERIC_ATOMIC,
        citations=[{"url": support_url, "role": "support"},
                   {"url": benchmark_url, "role": "conversion_benchmark"}])
    conversion = {
        **MATCHING_OBSERVATION, "value": 90, "currency": "EUR",
        "conversion": {"original_value": 90, "target_value": 100,
            "target_unit": "million", "target_currency": "USD",
            "formula": "multiply", "rate": "1.111111111111111111",
            "benchmark_source": benchmark_url},
    }
    benchmark = {"kind": "conversion_rate", "rate": "1.111111111111111111",
        "formula": "multiply", "from_currency": "EUR", "to_currency": "USD",
        "from_unit": "million", "to_unit": "million", "period": "FY2025",
        "tolerance": "0.000001"}
    probes = {
        support_url: evidence_probe(
            support_url, text="Example Corp reported FY2025 GAAP revenue.",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            publisher_kind="regulatory_filing", numeric_observations=(conversion,)),
        benchmark_url: evidence_probe(
            benchmark_url, text="rate 1.111111111111111111", entity_ids=(),
            numeric_observations=(benchmark,)),
    }
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=probes.__getitem__,
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert "located" in decision.checks["numeric_consistency"]["reason"]


@pytest.mark.parametrize(("declared", "predicate", "text"), [
    ("identity", "identity", "NVIDIA revenue will increase next year"),
    ("identity", "identity", "NVIDIA growth is caused by demand"),
    ("identity", "forecast_estimate", "NVIDIA is an AI company"),
])
def test_any_high_risk_type_signal_blocks_fact_promotion(
        tmp_path, declared, predicate, text):
    repo = _verification_repo(tmp_path)
    atomic = {"subject": "NVIDIA", "predicate": predicate,
              "object": text, "time": "2027", "region": "US", "qualifiers": {}}
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"high-risk-{abs(hash(text))}",
        assertion_type=declared, atomic=atomic)
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, text=text),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["type_policy"]["status"] == "failed"
    assert decision.checks["type_policy"]["high_risk_signals"]


@pytest.mark.parametrize(("signal_text", "expected_signal"), [
    ("NVIDIA has 80 percent market share in accelerators", "market_share"),
    ("The accelerator market size reached USD 50 billion", "market_size"),
])
def test_identity_declaration_cannot_hide_market_signal(
        tmp_path, signal_text, expected_signal):
    repo = _verification_repo(tmp_path)
    text = signal_text
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"identity-hidden-{expected_signal}",
        assertion_type="identity", atomic={
            "subject": "NVIDIA", "predicate": "identity", "object": text,
            "time": "2026", "region": "US", "qualifiers": {}})
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(url, text=text),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["type_classification"]["status"] == "failed"
    assert expected_signal in decision.checks["type_classification"]["signals"]


EXPECTED_FINANCIAL_SIGNAL_TERMS = (
    "assets", "liabilities", "debt", "equity", "EBITDA", "EBIT",
    "operating income", "net income", "free cash flow", "capital expenditure",
    "capex", "revenue", "profit", "earnings", "cash flow", "EPS",
    "diluted EPS", "R&D expense", "dividend", "COGS",
    "资产", "负债", "债务", "股东权益", "息税折旧摊销前利润", "息税前利润",
    "营业利润", "净利润", "自由现金流", "资本开支", "营收", "每股收益",
    "稀释每股收益", "研发费用", "股息", "营业成本",
)


def test_financial_signal_classifier_has_explicit_controlled_vocabulary():
    assert {term.casefold() for term in EXPECTED_FINANCIAL_SIGNAL_TERMS}.issubset(
        set(agent_evidence_module._FINANCIAL_SIGNAL_TERMS))


@pytest.mark.parametrize("term", EXPECTED_FINANCIAL_SIGNAL_TERMS)
def test_identity_declaration_cannot_hide_controlled_financial_signal(tmp_path, term):
    repo = _verification_repo(tmp_path)
    text = f"NVIDIA reported {term} for FY2025"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"identity-financial-{EXPECTED_FINANCIAL_SIGNAL_TERMS.index(term)}",
        assertion_type="identity", atomic={
            "subject": "NVIDIA", "predicate": "identity", "object": text,
            "time": "FY2025", "region": "US", "qualifiers": {}})
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(url, text=text),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["type_classification"]["status"] == "failed"
    assert "financial" in decision.checks["type_classification"]["signals"]


def _typed_evaluator(*assertion_types: str):
    def evaluate(request):
        support = [item for item in request.evidence if item.role == "support"]
        return [SemanticEvaluation(
            evidence_id=item.evidence_id, decision="supported",
            reason="independent type and semantic decision",
            content_hash=item.content_hash, locator=item.locator,
            evaluator_call_id=f"type-call-{index}",
            assertion_type=assertion_types[min(index, len(assertion_types) - 1)],
        ) for index, item in enumerate(support)]
    return ConfiguredSemanticEvaluator(
        evaluator_id="independent-type-verifier", method="independent_model",
        evaluate=evaluate)


def test_independent_evaluator_financial_type_blocks_agent_identity_spoof(tmp_path):
    repo = _verification_repo(tmp_path)
    text = "NVIDIA reported its annual results for FY2025"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="independent-financial-type",
        assertion_type="identity", atomic={
            "subject": "NVIDIA", "predicate": "identity", "object": text,
            "time": "FY2025", "region": "US", "qualifiers": {}})
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(url, text=text),
        semantic_evaluator=_typed_evaluator("financial"))
    assert decision.disposition == "candidate"
    classification = decision.checks["type_classification"]
    assert classification["status"] == "failed"
    assert classification["independent_assertion_types"] == ["financial"]


@pytest.mark.parametrize("evaluator_types", [("",), ("identity", "financial")])
def test_missing_or_divergent_independent_evaluator_type_is_candidate(
        tmp_path, evaluator_types):
    repo = _verification_repo(tmp_path)
    citations = ["https://sec.gov/type-one"]
    if len(evaluator_types) > 1:
        citations.append("https://sec.gov/type-two")
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"independent-type-{len(evaluator_types)}",
        citations=citations)
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(url),
        semantic_evaluator=_typed_evaluator(*evaluator_types))
    assert decision.disposition == "candidate"
    assert decision.checks["type_classification"]["status"] == "failed"


def test_repository_non_fact_aliases_cover_forecast_estimates():
    assert {"forecast_estimate", "estimate", "causality"}.issubset(
        NON_FACT_ASSERTION_TYPES)


class _OfflineResponse:
    def __init__(self, url: str, body: str, *, status: int = 200,
                 headers: dict | None = None, peer_unavailable: bool = False):
        self.url = url
        self.body = body.encode()
        self.status_code = status
        self.headers = headers or {"Last-Modified": "Mon, 31 Aug 2026 12:00:00 GMT"}
        self.encoding = "utf-8"
        self.raw = type("Raw", (), {})()
        self.peer_unavailable = peer_unavailable

    def iter_content(self, _size):
        yield self.body

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _offline_network(monkeypatch, responses: dict[str, _OfflineResponse], dns: dict[str, str]):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return responses[url]

    class Session:
        def __init__(self):
            self.trust_env = True

        def get(self, url, **kwargs):
            calls.append((url, {**kwargs, "trust_env": self.trust_env}))
            response = responses[url]
            if (not response.peer_unavailable and
                    not getattr(response.raw, "_connection", None)):
                host = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(url).hostname
                address = dns.get(host, host)
                response.raw._connection = type("Connection", (), {
                    "sock": type("Socket", (), {
                        "getpeername": lambda self: (address, 443)})()
                })()
            return response

        def close(self):
            return None

    monkeypatch.setattr(agent_evidence_module.requests, "get", get)
    monkeypatch.setattr(agent_evidence_module.requests, "Session", Session)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *_args, **_kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (dns.get(host, host), 443))])
    return calls


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/private", "http://169.254.169.254/latest/meta-data",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://public.example/private-dns",
])
def test_production_fetch_rejects_private_metadata_and_private_dns(
        monkeypatch, url):
    body = "public evidence"
    calls = _offline_network(
        monkeypatch, {url: _OfflineResponse(url, body)},
        {"public.example": "10.1.2.3", "metadata.google.internal": "169.254.169.254"})
    probe = probe_agent_evidence(
        url, locator={"type": "text_offset", "start": 0, "end": len(body)},
        expected_hash=sha256(body.encode()).hexdigest())
    assert not probe.reachable
    assert "blocked" in probe.reason
    assert calls == []


def test_production_fetch_revalidates_redirect_and_ignores_proxy_environment(
        monkeypatch):
    public = "https://public.example/start"
    private = "http://10.0.0.7/secret"
    responses = {public: _OfflineResponse(
        public, "", status=302, headers={"Location": private})}
    calls = _offline_network(monkeypatch, responses, {"public.example": "93.184.216.34"})
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    probe = probe_agent_evidence(
        public, locator={"type": "text_offset", "start": 0, "end": 1},
        expected_hash="0" * 64)
    assert not probe.reachable and "blocked" in probe.reason
    assert len(calls) == 1
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["trust_env"] is False


def test_production_fetch_rejects_peer_address_outside_validated_dns(monkeypatch):
    url, body = "https://public.example/rebind", "evidence"
    response = _OfflineResponse(url, body)
    response.raw._connection = type("Connection", (), {
        "sock": type("Socket", (), {"getpeername": lambda self: ("10.0.0.9", 443)})()
    })()
    calls = _offline_network(
        monkeypatch, {url: response}, {"public.example": "93.184.216.34"})
    probe = probe_agent_evidence(
        url, locator={"type": "text_offset", "start": 0, "end": len(body)},
        expected_hash=sha256(body.encode()).hexdigest())
    assert not probe.reachable
    assert probe.reason == "blocked_dns_rebinding_or_peer_address"
    assert len(calls) == 1


@pytest.mark.parametrize(("body", "locator", "excerpt"), [
    ("prefix evidence suffix", {"type": "text_offset", "start": 7, "end": 15},
     "evidence"),
    ("<html><p id='fact'>Evidence only</p><p>secret page</p></html>",
     {"type": "html_selector", "selector": "#fact"}, "Evidence only"),
    ('{"result":{"value":12,"private_field":"never-send"}}',
     {"type": "api_field", "path": "result.value"}, "12"),
])
def test_production_fetch_replays_submitted_locator_and_hash_locally(
        monkeypatch, body, locator, excerpt):
    url = "https://sec.gov/located"
    _offline_network(monkeypatch, {url: _OfflineResponse(url, body)},
                     {"sec.gov": "23.50.20.10"})
    probe = probe_agent_evidence(
        url, locator=locator, expected_hash=sha256(body.encode()).hexdigest())
    assert probe.reachable
    assert probe.locator == locator
    assert probe.located_text == excerpt
    assert probe.located_text != body or excerpt == body


def test_production_fetch_replays_pdf_page_locator_with_local_extractor(
        monkeypatch):
    url, body = "https://sec.gov/filing.pdf", "normalized pdf bytes"
    _offline_network(monkeypatch, {url: _OfflineResponse(url, body)},
                     {"sec.gov": "23.50.20.10"})
    monkeypatch.setattr(agent_evidence_module, "_pdf_pages",
                        lambda _raw: ("cover", "Evidence on page two"))
    locator = {"type": "pdf_page", "page": 2, "start": 0, "end": 8}
    probe = probe_agent_evidence(
        url, locator=locator, expected_hash=sha256(body.encode()).hexdigest())
    assert probe.reachable
    assert probe.located_text == "Evidence"
    assert probe.page_texts == ("cover", "Evidence on page two")


def test_production_fetch_rejects_bare_url_as_whole_page_evidence(monkeypatch):
    url, body = "https://sec.gov/bare", "whole page must not become evidence"
    _offline_network(monkeypatch, {url: _OfflineResponse(url, body)},
                     {"sec.gov": "23.50.20.10"})
    probe = probe_agent_evidence(url)
    assert not probe.reachable
    assert probe.located_text == ""
    assert "locator" in probe.reason


def test_verifier_passes_submitted_locator_and_hash_to_production_fetch(tmp_path):
    repo = _verification_repo(tmp_path)
    text = "NVIDIA is an AI company."
    locator = {"type": "text_offset", "start": 0, "end": len(text)}
    content_hash = sha256(text.encode()).hexdigest()
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="fetch-contract", citations=[{
            "url": "https://sec.gov/evidence", "locator": locator,
            "content_hash": content_hash}])
    received = []

    def fetch(url, *, locator, expected_hash):
        received.append((url, locator, expected_hash))
        return evidence_probe(url, text=text)

    decision = AssertionVerifier(
        fetch=fetch, semantic_evaluator=configured_evaluator()).verify(
            repo, "AI", assertion_id)
    assert decision.disposition == "accepted"
    assert received == [("https://sec.gov/evidence", locator, content_hash)]


@pytest.mark.parametrize("object_value", [100, 1e6, "12%", "3万亿"])
def test_scalar_numeric_objects_cannot_bypass_required_numeric_schema(
        tmp_path, object_value):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"scalar-{abs(hash(str(object_value)))}",
        assertion_type="financial", atomic={
            "subject": "Example Corp", "predicate": "financial",
            "object": object_value, "time": "FY2025", "region": "US",
            "qualifiers": {}})
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, text=f"Example Corp reported {object_value}",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            numeric_observations=()),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["numeric_consistency"]["status"] == "failed"


def test_scalar_numeric_object_merges_with_structured_qualifiers(tmp_path):
    repo = _verification_repo(tmp_path)
    atomic = {
        "subject": "Example Corp", "predicate": "financial", "object": 100,
        "time": "FY2025", "region": "US", "qualifiers": {
            "unit": "million", "currency": "USD", "period": "FY2025",
            "statistical_definition": "GAAP revenue"}}
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="scalar-structured", assertion_type="financial",
        atomic=atomic,
        citations=["https://sec.gov/Archives/edgar/data/1/scalar-filing"])
    observation = {"value": 100, "unit": "million", "currency": "USD",
                   "period": "FY2025", "statistical_definition": "GAAP revenue"}
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(
            url, text="Example Corp FY2025 GAAP revenue was USD 100 million",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            numeric_observations=(observation,)),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "accepted"
    assert decision.checks["numeric_consistency"]["status"] == "passed"


def test_market_type_without_structured_number_is_candidate(tmp_path):
    repo = _verification_repo(tmp_path)
    urls = ["https://reuters.com/market", "https://bloomberg.com/market"]
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="market-no-number", assertion_type="market_share",
        citations=urls, atomic={"subject": "NVIDIA", "predicate": "market_share",
            "object": "NVIDIA leads accelerators", "time": "2026", "region": "US",
            "qualifiers": {}})
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, text="NVIDIA leads accelerators"),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["numeric_consistency"]["status"] == "failed"


def test_model_declared_official_cannot_upgrade_reuters_to_primary(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="reuters-self-official",
        citations=["https://reuters.com/not-official"])
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, publisher_kind="official_record"),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["corroboration"]["status"] == "failed"


def test_transient_evaluator_failure_is_retryable_and_not_terminal(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="transient-retry")
    failing = ConfiguredSemanticEvaluator(
        evaluator_id="independent-verifier", method="independent_model",
        evaluate=lambda _request: (_ for _ in ()).throw(TimeoutError("temporary")))
    first = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(url),
        semantic_evaluator=failing)
    assert first.disposition == "candidate"
    assert first.checks["semantic_support"]["retryable"] is True
    assert repo._get_agent_assertion("AI", assertion_id)["status"] == \
        "submitted_for_verification"
    second = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())
    assert second.disposition == "accepted"


def test_concurrent_verification_is_projection_idempotent(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="concurrent-verify")
    barrier = threading.Barrier(2)

    def fetch(url):
        barrier.wait(timeout=5)
        return evidence_probe(url)

    verifier = AssertionVerifier(fetch=fetch, semantic_evaluator=configured_evaluator())
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(verifier.verify, repo, "AI", assertion_id)
                   for _ in range(2)]
        decisions = [future.result(timeout=15) for future in futures]
    assert [item.disposition for item in decisions] == ["accepted", "accepted"]
    assert len({item.claim_id for item in decisions}) == 1
    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1


@pytest.mark.parametrize("assertion_type", ["financial", "valuation", "market_size"])
def test_canonical_monetary_type_requires_currency_even_when_predicate_is_identity(
        tmp_path, assertion_type):
    repo = _verification_repo(tmp_path)
    atomic = {"subject": "Example Corp", "predicate": "identity",
              "object": "FY2025 value", "time": "FY2025", "region": "US",
              "value": 100, "unit": "million", "period": "FY2025",
              "statistical_definition": "reported monetary value", "qualifiers": {}}
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"canonical-currency-{assertion_type}",
        assertion_type=assertion_type, atomic=atomic)
    observation = {"value": 100, "unit": "million", "period": "FY2025",
                   "statistical_definition": "reported monetary value"}
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(
            url, text="Example Corp FY2025 reported monetary value was 100 million",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            numeric_observations=(observation,)),
        semantic_evaluator=_typed_evaluator(assertion_type))
    assert decision.disposition == "candidate"
    assert "currency" in decision.checks["numeric_consistency"]["reason"]


def test_non_monetary_market_share_ratio_does_not_require_currency(tmp_path):
    repo = _verification_repo(tmp_path)
    urls = ["https://reuters.com/share", "https://bloomberg.com/share"]
    atomic = {"subject": "NVIDIA", "predicate": "market_share", "object": "share",
              "time": "FY2025", "region": "US", "value": 80, "unit": "%",
              "period": "FY2025", "statistical_definition": "accelerator share",
              "qualifiers": {}}
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="share-ratio-no-currency",
        assertion_type="market_share", atomic=atomic, citations=urls)
    observation = {"value": 80, "unit": "%", "period": "FY2025",
                   "statistical_definition": "accelerator share"}
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(
            url, text="NVIDIA FY2025 accelerator share was 80 percent",
            numeric_observations=(observation,)),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "accepted"


@pytest.mark.parametrize("url", [
    "https://github.com/random/repository",
    "https://nist.gov/blog/random-post",
])
def test_generic_primary_domain_cannot_authorize_technical_claim(tmp_path, url):
    repo = _verification_repo(tmp_path)
    text = "NVIDIA benchmark precision was 90; batch=1, precision=FP16"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix=f"generic-technical-{abs(hash(url))}",
        assertion_type="technical_performance", citations=[url], atomic={
            "subject": "NVIDIA", "predicate": "technical_performance",
            "object": "benchmark precision", "time": "2026", "region": "US",
            "qualifiers": {}})
    probe = replace(evidence_probe(url, text=text),
                    experimental_conditions=(("batch", "1"),
                                             ("precision", "FP16")))
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda _url: probe,
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["corroboration"]["status"] == "failed"


def test_governed_nist_standard_document_can_authorize_technical_claim(tmp_path):
    repo = _verification_repo(tmp_path)
    url = "https://nist.gov/publications/ai-standard"
    text = "NVIDIA benchmark precision was 90; batch=1, precision=FP16"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="governed-nist-standard",
        assertion_type="technical_performance", citations=[url], atomic={
            "subject": "NVIDIA", "predicate": "technical_performance",
            "object": "benchmark precision", "time": "2026", "region": "US",
            "qualifiers": {}})
    probe = replace(evidence_probe(url, text=text),
                    experimental_conditions=(("batch", "1"),
                                             ("precision", "FP16")))
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda _url: probe,
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "accepted"


def test_regulatory_filing_period_must_be_located_for_financial_authority(tmp_path):
    repo = _verification_repo(tmp_path)
    url = "https://sec.gov/Archives/edgar/data/1/filing"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="filing-period-mismatch",
        assertion_type="financial", atomic=NUMERIC_ATOMIC, citations=[url])
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda _url: evidence_probe(
            url, text="Example Corp FY2024 GAAP revenue was USD 100 million",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            numeric_observations=(MATCHING_OBSERVATION,)),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["corroboration"]["status"] == "failed"


def test_concurrent_different_evaluators_return_repository_decision(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="concurrent-different")
    barrier = threading.Barrier(2)

    def fetch(url):
        barrier.wait(timeout=5)
        return evidence_probe(url)

    verifiers = [
        AssertionVerifier(fetch=fetch, semantic_evaluator=configured_evaluator("supported")),
        AssertionVerifier(fetch=fetch, semantic_evaluator=configured_evaluator("partial")),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(verifier.verify, repo, "AI", assertion_id)
                   for verifier in verifiers]
        decisions = [future.result(timeout=15) for future in futures]
    stored = repo._get_agent_assertion("AI", assertion_id)
    assert {decision.disposition for decision in decisions} == {stored["status"]}
    assert all(decision.claim_id == stored["claim_id"] for decision in decisions)
    assert all(decision.checks == stored["verification"] for decision in decisions)


def test_production_fetch_fails_closed_when_peer_address_is_unavailable(monkeypatch):
    url, body = "https://public.example/no-peer", "evidence"
    _offline_network(monkeypatch, {url: _OfflineResponse(
        url, body, peer_unavailable=True)},
                     {"public.example": "93.184.216.34"})
    probe = probe_agent_evidence(
        url, locator={"type": "text_offset", "start": 0, "end": len(body)},
        expected_hash=sha256(body.encode()).hexdigest())
    assert not probe.reachable
    assert probe.reason == "blocked_peer_address_unverifiable"


def test_runtime_citation_budget_blocks_before_fetch(tmp_path):
    repo = _verification_repo(tmp_path)
    citations = [f"https://sec.gov/budget/{index}" for index in range(20)]
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="citation-budget", citations=citations)
    with repo.transaction() as con:
        con.execute("""INSERT INTO agent_citations
            (id,assertion_id,url,canonical_url,reachability,created_at)
            VALUES(?,?,?,?,?,?)""", (
                "act_legacy_budget_overflow", assertion_id,
                "https://sec.gov/budget/20", "https://sec.gov/budget/20",
                "unchecked", "2026-09-01T00:00:00+00:00"))
    calls = []
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: calls.append(url) or evidence_probe(url),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    assert decision.checks["resource_budget"]["status"] == "failed"
    assert calls == []


def test_excerpt_budget_skips_provider_and_stores_bounded_verification(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="excerpt-budget")
    content = "NVIDIA " + ("evidence " * 3000)
    calls = []
    evaluator = ConfiguredSemanticEvaluator(
        evaluator_id="independent", method="independent_model",
        evaluate=lambda request: calls.append(request) or [])
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url, text=content),
        semantic_evaluator=evaluator)
    assert decision.disposition == "candidate"
    assert decision.checks["resource_budget"]["status"] == "failed"
    assert calls == []
    with repo.connection() as con:
        stored_size = con.execute("""SELECT length(verification_json)
            FROM agent_assertions WHERE id=?""", (assertion_id,)).fetchone()[0]
    assert stored_size <= 256 * 1024


def test_fact_projection_omits_full_content_but_snapshot_keeps_local_source(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(repo, tmp_path, suffix="no-content-in-checks")
    decision = verify_agent_assertion(
        repo, "AI", assertion_id, fetch=lambda url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())
    evidence = decision.checks["fact_projection"]["evidence"][0]
    assert "content" not in evidence
    with repo.connection() as con:
        snapshot = con.execute("""SELECT content_text FROM document_snapshots WHERE id=(
            SELECT snapshot_id FROM evidence WHERE claim_id=?)""",
            (decision.claim_id,)).fetchone()[0]
    assert snapshot == "NVIDIA is an AI company."


def test_single_direct_party_requires_governed_subject_domain_match(tmp_path):
    repo = _verification_repo(tmp_path)
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="direct-party-subject-mismatch",
        assertion_type="event", citations=["https://nist.gov/news/acquisition"],
        atomic={"subject": "NVIDIA", "predicate": "event",
                "object": "acquired Example Corp", "time": "2026",
                "region": "US", "qualifiers": {}})
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, text="NVIDIA acquired Example Corp in 2026."),
        semantic_evaluator=_typed_evaluator("event"))
    assert decision.disposition == "candidate"
    assert decision.checks["corroboration"]["status"] == "failed"


def test_single_direct_party_metadata_cannot_replace_audited_binding(tmp_path):
    repo = _verification_repo(tmp_path)
    atomic = {"subject": "NIST", "predicate": "event",
              "object": "published the AI profile", "time": "2026",
              "region": "US", "qualifiers": {}}
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="direct-party-subject-match",
        assertion_type="event", citations=["https://nist.gov/news/ai-profile"],
        atomic=atomic)
    with repo.transaction() as con:
        subject_id = con.execute(
            "SELECT json_extract(record_json,'$.assertions[0].atomic.subject_id') "
            "FROM agent_results WHERE id=(SELECT result_id FROM agent_assertions WHERE id=?)",
            (assertion_id,)).fetchone()[0]
        metadata = json.loads(con.execute(
            "SELECT metadata_json FROM entities WHERE id=?", (subject_id,)).fetchone()[0])
        metadata["official_domains"] = ["nist.gov"]
        con.execute("UPDATE entities SET metadata_json=? WHERE id=?",
                    (json.dumps(metadata), subject_id))
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(
            url, text="NIST published the AI profile in 2026.",
            entity_ids=(subject_id,)),
        semantic_evaluator=_typed_evaluator("event"))
    assert decision.disposition == "candidate"
    assert decision.checks["corroboration"]["status"] == "failed"


def test_plain_source_metadata_cannot_forge_audited_direct_party_binding(tmp_path):
    repo = _verification_repo(tmp_path)
    url = "https://nist.gov/news/forged-binding"
    atomic = {"subject": "NVIDIA", "predicate": "event",
              "object": "acquired Example Corp", "time": "2026",
              "region": "US", "qualifiers": {}}
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="forged-direct-party-binding",
        assertion_type="event", citations=[url], atomic=atomic)
    with repo.connection() as con:
        subject_id = con.execute(
            "SELECT json_extract(record_json,'$.assertions[0].atomic.subject_id') "
            "FROM agent_results WHERE id=(SELECT result_id FROM agent_assertions WHERE id=?)",
            (assertion_id,)).fetchone()[0]
    repo.upsert_source("AI", "official", {
        "name": "forged ordinary source metadata", "url": url,
        "governed_entity_ids": [subject_id], "added_manually": True})
    with repo.transaction() as con:
        metadata = json.loads(con.execute(
            "SELECT metadata_json FROM entities WHERE id=?", (subject_id,)).fetchone()[0])
        metadata["official_domains"] = ["nist.gov"]
        con.execute("UPDATE entities SET metadata_json=? WHERE id=?",
                    (json.dumps(metadata), subject_id))
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda fetched_url: evidence_probe(
            fetched_url, text="NVIDIA acquired Example Corp in 2026."),
        semantic_evaluator=_typed_evaluator("event"))
    assert decision.disposition == "candidate"
    assert decision.checks["corroboration"]["status"] == "failed"


def test_financial_period_requires_full_normalized_token_match(tmp_path):
    repo = _verification_repo(tmp_path)
    url = "https://sec.gov/Archives/edgar/data/1/wrong-period-token"
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="financial-period-full-token",
        assertion_type="financial", atomic=NUMERIC_ATOMIC, citations=[url])
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda _url: evidence_probe(
            url, text="Example Corp FY20250 GAAP revenue was USD 100 million",
            entity_ids=("ent_6001f506ce1af727cac391e4",),
            numeric_observations=(MATCHING_OBSERVATION,)),
        semantic_evaluator=_typed_evaluator("financial"))
    assert decision.disposition == "candidate"
    assert decision.checks["corroboration"]["status"] == "failed"


def test_repository_import_rejects_schema_excess_citations(tmp_path):
    repo = _verification_repo(tmp_path)
    record = result_record("thousand-citations")
    record["assertions"][0]["citations"] = [
        f"https://example.com/evidence/{index}" for index in range(1000)]
    raw_path = write_artifact(tmp_path, "AI", record, "thousand-citations.json")
    with pytest.raises(ValueError, match="20 citations"):
        repo.index_agent_result("AI", record, str(raw_path))
    with repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM agent_results").fetchone()[0] == 0


def test_oversized_verification_is_compacted_before_persistence(tmp_path):
    repo = _verification_repo(tmp_path)
    huge_object = "x" * 300_000
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="bounded-verification-persistence",
        atomic={"subject": "NVIDIA", "predicate": "identity",
                "object": huge_object, "time": "2026", "region": "US",
                "qualifiers": {}})
    decision = verify_agent_assertion(
        repo, "AI", assertion_id,
        fetch=lambda url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())
    assert decision.disposition == "candidate"
    budget = decision.checks["resource_budget"]
    assert budget["status"] == "failed"
    assert budget["budget_truncation"]["original_bytes"] > 256 * 1024
    encoded_response = json.dumps(decision.checks, ensure_ascii=False).encode()
    assert len(encoded_response) <= 256 * 1024
    with repo.connection() as con:
        stored = con.execute(
            "SELECT verification_json FROM agent_assertions WHERE id=?",
            (assertion_id,)).fetchone()[0]
    assert len(stored.encode()) <= 256 * 1024


def test_public_repository_boundary_rejects_raw_accepted_checks(tmp_path):
    repo = _verification_repo(tmp_path)
    _, verified_id = submitted_assertion(
        repo, tmp_path, suffix="trusted-reference",
        generation_call_id="generation-call-1")
    verified = verify_agent_assertion(
        repo, "AI", verified_id, fetch=lambda url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())
    _, assertion_id = submitted_assertion(
        repo, tmp_path, suffix="raw-false-passed",
        generation_call_id="generation-call-1")
    # This is a structurally complete decision emitted by the real verifier, but
    # its evidence belongs to a different assertion. Raw replay must still fail.
    with pytest.raises(ValueError, match="trusted verifier orchestration"):
        repo.apply_assertion_verification(
            "AI", assertion_id, checks=verified.checks,
            disposition="accepted")


def test_evidence_snapshot_and_excerpt_advance_together_for_same_claim(tmp_path):
    repo = _verification_repo(tmp_path)
    url = "https://sec.gov/versioned-claim"
    _, first_id = submitted_assertion(
        repo, tmp_path, suffix="evidence-snapshot-first", citations=[url])
    first = verify_agent_assertion(
        repo, "AI", first_id,
        fetch=lambda _url: evidence_probe(url, text="NVIDIA is an AI company. v1"),
        semantic_evaluator=configured_evaluator())
    _, second_id = submitted_assertion(
        repo, tmp_path, suffix="evidence-snapshot-second", citations=[url])
    second_text = "NVIDIA is an AI company. v2"
    second = verify_agent_assertion(
        repo, "AI", second_id,
        fetch=lambda _url: evidence_probe(url, text=second_text),
        semantic_evaluator=configured_evaluator())
    assert second.claim_id == first.claim_id
    with repo.connection() as con:
        row = con.execute(
            "SELECT snapshot_id,excerpt FROM evidence WHERE claim_id=?",
            (first.claim_id,)).fetchone()
        snapshot = con.execute(
            "SELECT content_hash FROM document_snapshots WHERE id=?",
            (row["snapshot_id"],)).fetchone()
    assert row["excerpt"] == second_text
    assert snapshot["content_hash"] == sha256(second_text.encode()).hexdigest()


def test_candidate_observation_cannot_downgrade_verified_industry_document(tmp_path):
    repo = _verification_repo(tmp_path)
    url = "https://sec.gov/no-downgrade"
    _, accepted_id = submitted_assertion(
        repo, tmp_path, suffix="industry-doc-verified", citations=[url])
    verify_agent_assertion(
        repo, "AI", accepted_id, fetch=lambda _url: evidence_probe(url),
        semantic_evaluator=configured_evaluator())
    with repo.connection() as con:
        before_metadata = con.execute("""SELECT metadata_json FROM industry_documents
            WHERE document_id=(SELECT document_id FROM agent_citations WHERE assertion_id=?)""",
            (accepted_id,)).fetchone()[0]
    _, candidate_id = submitted_assertion(
        repo, tmp_path, suffix="industry-doc-candidate", citations=[url])
    verify_agent_assertion(
        repo, "AI", candidate_id, fetch=lambda _url: evidence_probe(url),
        semantic_evaluator=configured_evaluator("partial"))
    with repo.connection() as con:
        row = con.execute("""SELECT review_status,credibility,metadata_json FROM industry_documents
            WHERE document_id=(SELECT document_id FROM agent_citations WHERE assertion_id=?)""",
            (accepted_id,)).fetchone()
    assert (row["review_status"], row["credibility"]) == ("verified", "verified")
    assert row["metadata_json"] == before_metadata
