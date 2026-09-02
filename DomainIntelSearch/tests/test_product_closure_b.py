from __future__ import annotations

import json

import pytest


def _public_batch(count: int = 6) -> dict:
    documents = []
    for index in range(count):
        documents.append({
            "title": f"Public document {index}",
            "url": f"https://publisher-{index % 3}.example/doc-{index}",
            "publisher": f"Publisher {index % 3}",
            "publisher_url": f"https://publisher-{index % 3}.example/",
            "publisher_category": "official" if index % 2 == 0 else "journal",
            "publisher_identity_verified": True,
            "reachable": True,
            "published_at": "2026-09-01T08:00:00+00:00",
            "collected_at": "2026-09-02T08:00:00+00:00",
            "content": f"independent public body {index}",
        })
    return {
        "mode": "public_credential_free", "provider_calls": 0,
        "documents": documents,
        "entities": [
            {"name": f"Entity {i}", "type": ("company", "research_group", "regulator")[i % 3],
             "document_urls": [documents[i % count]["url"]]} for i in range(5)
        ],
        "chain_nodes": [{"id": f"n{i}", "name": f"Stage {i}", "order": i} for i in range(3)],
        "chain_edges": [
            {"source": "n0", "target": "n1", "relation": "supplies",
             "document_urls": [documents[0]["url"]]},
            {"source": "n1", "target": "n2", "relation": "enables",
             "document_urls": [documents[1]["url"]]},
        ],
    }


def test_public_bootstrap_hashes_and_persists_only_observed_evidence(tmp_path):
    from src.public_bootstrap import collect_public_bootstrap

    class Adapter:
        def collect(self, industry: str) -> dict:
            assert industry == "AI"
            return _public_batch()

    result = collect_public_bootstrap(Adapter(), industry="AI", output_dir=tmp_path)
    assert result["status"] == "completed"
    assert result["oracle"]["passed"] is True
    record = json.loads((tmp_path / "nom01-record.json").read_text())
    assert all(len(item["content_sha256"]) == 64 for item in record["documents"])
    assert all(item["status"] == "candidate" for item in record["entities"])
    assert all(edge["evidence"] for edge in record["chain_edges"])
    assert record["provenance"]["seed_used"] is False
    assert record["provenance"]["taskpack_used"] is False


def test_public_bootstrap_never_completes_below_nom_threshold(tmp_path):
    from src.public_bootstrap import collect_public_bootstrap

    class Adapter:
        def collect(self, industry: str) -> dict:
            return _public_batch(2)

    result = collect_public_bootstrap(Adapter(), industry="AI", output_dir=tmp_path)
    assert result["status"] in {"partial", "paused"}
    assert result["oracle"]["passed"] is False


def test_artifact_gate_rejects_dangling_references_and_sidecar_data_refs(tmp_path):
    from src.artifact_quality import evaluate_artifact

    markdown = ("# Report\n\n## 2026-09-02 Finding\n\nA concrete claim [9] with enough detail "
                "and a source [document](https://example.org/d).\n")
    sidecar = tmp_path / "report.viz.json"
    sidecar.write_text(json.dumps({"schema_version": 1, "data_refs": ["document:missing"]}))
    result = evaluate_artifact(markdown, {
        "generated_at": "2026-09-02", "status": "accepted",
        "references": [{"id": 1, "url": "https://example.org/d", "document_id": "doc-1"}],
        "documents": [{"id": "doc-1", "url": "https://example.org/d"}],
        "evidence": [],
        "claims": [{"claim": "A concrete claim", "evidence": [{"document_id": "missing"}]}],
    }, sidecar_path=sidecar)
    codes = {item["code"] for item in result["failures"]}
    assert {"dangling_reference", "dangling_claim_evidence", "dangling_sidecar_data_ref"} <= codes


def test_report_graph_uses_only_persisted_evidence_edges():
    from src.report_generation import _directed_chain

    class Repo:
        def list_chain_nodes(self, folder):
            return [{"id": "a", "name": "A", "order": 0},
                    {"id": "b", "name": "B", "order": 1}]

        def list_chain_edges(self, folder):
            return []

    store = type("Store", (), {"folder": "AI", "service": type("S", (), {"repo": Repo()})()})()
    graph = _directed_chain(store)
    assert graph["edges"] == []
    assert graph["gap"] == "no_persisted_evidence_edges"


def test_email_delivery_is_not_part_of_the_runtime_interface():
    import inspect
    from src.orchestrator import Orchestrator
    from src.scheduler import PeriodicScheduler

    assert "send" not in inspect.signature(Orchestrator.run_daily).parameters
    assert "send" not in inspect.signature(Orchestrator.run_weekly).parameters
    assert not hasattr(PeriodicScheduler, "_send_digest")
