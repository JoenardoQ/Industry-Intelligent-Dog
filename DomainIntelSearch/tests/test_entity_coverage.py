from __future__ import annotations

import pytest

from intdog_core import IntDogService


EXPECTED_OBJECT_CATEGORIES = {
    "company", "research_group", "government_institution", "association",
    "investment_institution", "person", "product", "technology", "standard",
    "policy",
}


def _coverage_api():
    from src.entity_coverage import (
        OBJECT_CATEGORIES, build_coverage_matrix, plan_entity_frontier,
        resolve_entity_candidate,
    )
    return OBJECT_CATEGORIES, build_coverage_matrix, plan_entity_frontier, \
        resolve_entity_candidate


def _service(tmp_path) -> IntDogService:
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    return service


def _qualified(service, *, stage: str, kind: str, region: str, count: int) -> None:
    country = "CN" if region == "china" else "US"
    for index in range(count):
        document_id = service.repo.upsert_document("AI", "official", "2026-09-01", {
            "title": f"Evidence {stage}-{kind}-{region}-{index}",
            "url": f"https://evidence.example/{stage}/{kind}/{region}/{index}"})
        service.repo.upsert_entity("AI", {
            "name": f"{stage}-{kind}-{region}-{index}", "type": kind,
            "country": country, "chain": stage, "status": "accepted",
            "references": [{"document_id": document_id, "relation": "supports"}],
        })


def test_matrix_contains_ten_categories_only_for_applicable_stages_and_both_regions(
        tmp_path):
    categories, build_matrix, _, _ = _coverage_api()
    service = _service(tmp_path)
    service.repo.upsert_chain_node("AI", {
        "name": "Foundation", "order": 1,
        "applicable_entity_types": sorted(EXPECTED_OBJECT_CATEGORIES),
    })
    service.repo.upsert_chain_node("AI", {
        "name": "Applications", "order": 2,
        "applicable_entity_types": ["company", "product"],
    })

    matrix = build_matrix(service.repo, "AI")

    assert set(categories) == EXPECTED_OBJECT_CATEGORIES
    assert len(matrix["cells"]) == 24
    assert all(cell["status"] == "empty" for cell in matrix["cells"])
    assert {(cell["chain_stage"], cell["entity_type"], cell["region"])
            for cell in matrix["cells"]} == {
        *(('Foundation', kind, region) for kind in EXPECTED_OBJECT_CATEGORIES
          for region in ("china", "foreign")),
        *(('Applications', kind, region) for kind in ("company", "product")
          for region in ("china", "foreign")),
    }
    assert matrix["completeness_proven"] is False


def test_matrix_enforces_2_3_8_10_breadth_and_high_value_depth_boundaries(tmp_path):
    _, build_matrix, _, _ = _coverage_api()
    service = _service(tmp_path)
    stages = [
        ("At2", False, "china", 2), ("At3", False, "china", 3),
        ("At8", True, "china", 8), ("At10", True, "foreign", 10),
    ]
    for stage, high_value, region, count in stages:
        service.repo.upsert_chain_node("AI", {
            "name": stage, "applicable_entity_types": ["company"],
            "high_centrality": high_value,
        })
        _qualified(service, stage=stage, kind="company", region=region, count=count)

    cells = {(cell["chain_stage"], cell["region"]): cell
             for cell in build_matrix(service.repo, "AI")["cells"]}

    assert (cells[("At2", "china")]["qualified_count"],
            cells[("At2", "china")]["target"],
            cells[("At2", "china")]["status"]) == (2, 3, "gap")
    assert cells[("At3", "china")]["status"] == "covered"
    assert (cells[("At8", "china")]["target"],
            cells[("At8", "china")]["status"]) == (8, "covered")
    assert cells[("At10", "foreign")]["status"] == "saturated"


def test_frontier_prioritizes_high_centrality_gaps_and_requires_two_zero_gain_rounds():
    _, _, plan_frontier, _ = _coverage_api()
    gap_matrix = {
        "cells": [
            {"id": "ordinary", "chain_stage": "Apps", "entity_type": "company",
             "region": "foreign", "status": "gap", "qualified_count": 2,
             "target": 3, "priority": 50, "high_value": False},
            {"id": "central", "chain_stage": "Compute", "entity_type": "technology",
             "region": "china", "status": "gap", "qualified_count": 3,
             "target": 8, "priority": 95, "high_value": True},
        ],
        "round_history": [
            {"entities": 0, "nodes": 0, "relationships": 0, "coverage_units": 0},
            {"entities": 0, "nodes": 0, "relationships": 0, "coverage_units": 0},
        ],
    }
    frontier = plan_frontier(gap_matrix, round_no=3)
    assert [cell["id"] for cell in frontier.cells] == ["central", "ordinary"]
    assert frontier.entity_queries[0]["language"] == "zh"
    assert frontier.relation_queries
    assert frontier.stopping_reason == "coverage_gaps_retained"

    complete = {**gap_matrix, "cells": [
        {**cell, "status": "covered", "qualified_count": cell["target"]}
        for cell in gap_matrix["cells"]]}
    assert plan_frontier(complete, round_no=3).stopping_reason == \
        "converged_two_zero_marginal_rounds"
    complete["round_history"] = complete["round_history"][-1:]
    assert plan_frontier(complete, round_no=2).stopping_reason is None


def test_entity_resolution_merges_verified_alias_and_rename_but_not_identity_conflicts(
        tmp_path):
    _, _, _, resolve = _coverage_api()
    service = _service(tmp_path)
    existing_id = service.repo.upsert_entity("AI", {
        "name": "Old National Lab", "type": "government_institution", "country": "US",
        "external_ids": {"registration": "LAB-1"},
        "official_url": "https://lab.example/about", "status": "accepted",
    })
    renamed = resolve(service.repo, "AI", {
        "name": "National AI Laboratory", "aliases": ["Old National Lab"],
        "type": "government_institution", "country": "US",
        "external_ids": {"registration": "LAB-1"},
        "official_url": "https://lab.example/research", "status": "accepted",
    })
    assert renamed["decision"] == "merged" and renamed["entity_id"] == existing_id
    with service.repo.connection() as con:
        aliases = {row[0] for row in con.execute(
            "SELECT alias FROM entity_aliases WHERE entity_id=?", (existing_id,))}
        entity_count = con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    assert "National AI Laboratory" in aliases

    for conflicting in (
        {"external_ids": {"registration": "LAB-2"},
         "official_url": "https://lab.example/about"},
        {"external_ids": {"registration": "LAB-1"},
         "official_url": "https://impostor.example/about"},
    ):
        result = resolve(service.repo, "AI", {
            "name": "Old National Lab", "type": "government_institution",
            "country": "US", **conflicting})
        assert result["decision"] == "manual_review"
        assert result["reason"] in {"registration_identifier_conflict",
                                    "official_website_conflict"}
    with service.repo.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == entity_count

    distinct = resolve(service.repo, "AI", {
        "name": "Old National Lab", "type": "government_institution", "country": "CN",
        "external_ids": {"registration": "CN-LAB-1"},
        "official_url": "https://cn-lab.example/about"})
    assert distinct["decision"] == "created" and distinct["entity_id"] != existing_id


def test_acquisition_keeps_one_identity_and_time_bounded_roles(tmp_path):
    _, _, _, resolve = _coverage_api()
    service = _service(tmp_path)
    before = resolve(service.repo, "AI", {
        "name": "Target Robotics", "type": "company", "country": "US",
        "external_ids": {"registration": "TARGET-1"},
        "official_url": "https://target.example", "chain": "Robotics",
        "owner": "Owner A", "valid_from": "2020-01-01", "valid_to": "2025-06-30",
        "status": "accepted", "references": [{"document_id": "before"}],
    })
    after = resolve(service.repo, "AI", {
        "name": "Target Robotics, an Acquirer subsidiary", "type": "company",
        "country": "US", "external_ids": {"registration": "TARGET-1"},
        "official_url": "https://target.example", "chain": "Robotics",
        "owner": "Owner B", "valid_from": "2025-07-01", "status": "accepted",
        "references": [{"document_id": "after"}],
    })
    assert before["entity_id"] == after["entity_id"]
    assert after["decision"] == "merged"
    with service.repo.connection() as con:
        roles = [tuple(row) for row in con.execute("""SELECT valid_from,valid_to
            FROM entity_chain_roles WHERE entity_id=? ORDER BY valid_from""",
            (before["entity_id"],))]
    assert roles == [("2020-01-01", "2025-06-30"), ("2025-07-01", None)]


def test_chain_relationship_cannot_be_accepted_without_document_or_assertion(tmp_path):
    service = _service(tmp_path)
    upstream = service.repo.upsert_chain_node("AI", {"name": "Upstream"})
    downstream = service.repo.upsert_chain_node("AI", {"name": "Downstream"})
    edge_id = service.repo.upsert_chain_edge("AI", {
        "src_node_id": upstream, "dst_node_id": downstream,
        "relation": "supplies", "status": "accepted"})
    assert service.repo.list_chain_edges("AI")[0]["status"] == "candidate"
    with pytest.raises(ValueError, match="Document or Assertion"):
        service.repo.add_chain_edge_evidence(
            edge_id, "supports", url="https://description-only.example")

    document_id = service.repo.upsert_document("AI", "news", "2026-09-01", {
        "title": "Supply agreement", "url": "https://evidence.example/agreement"})
    service.repo.add_chain_edge_evidence(
        edge_id, "supports", document_id=document_id, excerpt="supplies")
    edge = service.repo.list_chain_edges("AI")[0]
    assert edge["status"] == "collected" and edge["evidence_count"] == 1


def test_entity_role_status_and_evidence_count_are_server_derived_and_industry_scoped(
        tmp_path):
    service = _service(tmp_path)
    service.create_industry("Chips", "芯片")
    foreign_document = service.repo.upsert_document("Chips", "official", "2026-09-01", {
        "title": "Other industry", "url": "https://other.example/evidence"})
    untrusted = service.repo.upsert_entity("AI", {
        "name": "Caller Accepted Lab", "type": "research_group", "country": "CN",
        "chain": "Models", "status": "accepted",
        "references": [{"document_id": "synthetic", "relation": "supports"},
                       {"document_id": foreign_document, "relation": "supports"}],
    })
    records = {row["entity_id"]: row
               for row in service.repo.list_entity_coverage_records("AI")}
    assert records[untrusted]["status"] == "candidate"
    assert records[untrusted]["evidence_count"] == 0

    document_id = service.repo.upsert_document("AI", "official", "2026-09-01", {
        "title": "Lab registry", "url": "https://registry.example/lab"})
    service.repo.upsert_entity("AI", {
        "name": "Caller Accepted Lab", "type": "research_group", "country": "CN",
        "chain": "Models", "status": "candidate",
        "references": [{"document_id": document_id, "relation": "supports"}],
    })
    derived = {row["entity_id"]: row
               for row in service.repo.list_entity_coverage_records("AI")}[untrusted]
    assert derived["status"] == "accepted"
    assert derived["evidence_count"] == 1


def test_chain_evidence_rejects_cross_industry_document_and_unaccepted_claim(tmp_path):
    service = _service(tmp_path)
    service.create_industry("Chips", "芯片")
    upstream = service.repo.upsert_chain_node("AI", {"name": "Upstream"})
    downstream = service.repo.upsert_chain_node("AI", {"name": "Downstream"})
    edge_id = service.repo.upsert_chain_edge("AI", {
        "src_node_id": upstream, "dst_node_id": downstream, "relation": "supplies"})
    foreign_document = service.repo.upsert_document("Chips", "official", "2026-09-01", {
        "title": "Foreign evidence", "url": "https://chips.example/evidence"})
    with pytest.raises(ValueError, match="current industry"):
        service.repo.add_chain_edge_evidence(
            edge_id, "supports", document_id=foreign_document)
    claim_id = service.repo.upsert_claim("AI", "supports_chain", {"edge": edge_id},
                                         status="candidate")
    with pytest.raises(ValueError, match="accepted"):
        service.repo.add_chain_edge_evidence(edge_id, "supports", claim_id=claim_id)
