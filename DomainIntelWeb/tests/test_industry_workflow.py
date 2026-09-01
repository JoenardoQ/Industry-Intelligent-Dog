from __future__ import annotations

import copy
import importlib

import pytest
from fastapi import HTTPException

from DomainIntelWeb.api import schemas
from intdog_core import IntDogService


def _load(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMAIN_INTEL_DATA_ROOT", str(tmp_path))
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    import DomainIntelWeb.api.main as module
    return importlib.reload(module), service


def _endpoint(router, suffix: str, method: str):
    return next(route.endpoint for route in router.routes
                if getattr(route, "path", "").endswith(suffix)
                and method in getattr(route, "methods", set()))


def test_overview_and_portable_industry_bundle_preserve_directed_knowledge(
        monkeypatch, tmp_path):
    module, service = _load(monkeypatch, tmp_path)
    service.add_source("AI", "official", {
        "name": "国家标准平台", "url": "https://std.example/ai",
    })
    document_id = service.repo.upsert_document("AI", "news", "2026-09-01", {
        "title": "模型进入推理部署", "url": "https://news.example/deployment",
    })
    upstream = service.repo.upsert_chain_node("AI", {
        "name": "基础模型", "order": 10, "description": "训练与模型供给",
    })
    downstream = service.repo.upsert_chain_node("AI", {
        "name": "推理部署", "order": 20, "description": "行业部署",
    })
    service.repo.upsert_chain_edge("AI", {
        "src_node_id": upstream, "dst_node_id": downstream,
        "relation": "enables", "status": "candidate",
    })
    service.repo.upsert_entity("AI", {
        "name": "示例研究组", "type": "research_group", "country": "CN",
        "chain": "基础模型", "role": "model_research",
        "references": [{"document_id": document_id, "relation": "supports"}],
    })

    overview = module.overview("AI")
    schemas.OverviewState.model_validate(overview)
    assert len(overview["chain_edges"]) == 1
    assert {key: overview["chain_edges"][0][key] for key in (
        "src_name", "dst_name", "relation", "evidence_count")} == {
            "src_name": "基础模型", "dst_name": "推理部署",
            "relation": "enables", "evidence_count": 0,
        }

    export = _endpoint(module.industries_router, "/export", "GET")
    bundle = export("AI")
    schemas.IndustryBundleState.model_validate(bundle)
    assert bundle["schema_version"] == 1
    assert len(bundle["checksum_sha256"]) == 64
    assert bundle["industry"]["name"] == "人工智能"
    assert bundle["chain_edges"][0]["relation"] == "enables"
    assert all("_file" not in str(item) for item in bundle["documents"])

    import_bundle = _endpoint(module.industries_router, "/industries/import", "POST")
    result = import_bundle(schemas.IndustryImportRequest(
        folder="AI_Copy", name="人工智能副本", bundle=bundle))
    schemas.IndustryImportState.model_validate(result)
    assert result["folder"] == "AI_Copy"
    copied = module.overview("AI_Copy")
    assert copied["stats"]["sources"] == 1
    assert copied["stats"]["documents"] == 1
    assert copied["stats"]["entities"] == 1
    assert copied["chain_edges"][0]["src_name"] == "基础模型"
    assert copied["chain_edges"][0]["dst_name"] == "推理部署"
    imported_entity = service.repo.list_compat_entities("AI_Copy")[0]
    assert imported_entity["status"] == "candidate"
    assert imported_entity["evidence_count"] == 0
    assert copied["chain_edges"][0]["status"] == "candidate"
    assert copied["chain_edges"][0]["evidence_count"] == 0

    with pytest.raises(HTTPException) as collision:
        import_bundle(schemas.IndustryImportRequest(
            folder="AI_Copy", name="重复", bundle=bundle))
    assert collision.value.status_code == 409


def test_import_rejects_checksum_tampering_before_any_shared_or_industry_write(
        monkeypatch, tmp_path):
    module, service = _load(monkeypatch, tmp_path)
    service.add_source("AI", "official", {
        "name": "Authority", "url": "https://authority.example/ai",
    })
    bundle = service.export_industry_bundle("AI")
    tampered = copy.deepcopy(bundle)
    tampered["sources"][0]["name"] = "Tampered"
    before_sources = service.repo.list_sources("AI")
    import_bundle = _endpoint(module.industries_router, "/industries/import", "POST")

    with pytest.raises(HTTPException) as error:
        import_bundle(schemas.IndustryImportRequest(
            folder="Tampered", name="Tampered", bundle=tampered))

    assert error.value.status_code == 409
    assert not (tmp_path / "Tampered").exists()
    assert service.repo.list_sources("AI") == before_sources
    with pytest.raises(FileNotFoundError):
        service.repo.industry_id("Tampered")


def test_import_failure_rolls_back_database_and_staged_folder(monkeypatch, tmp_path):
    _, service = _load(monkeypatch, tmp_path)
    bundle = service.export_industry_bundle("AI")
    def fail_merge(*_args, **_kwargs):
        raise RuntimeError("injected merge failure")

    monkeypatch.setattr(service, "_merge_staged_import", fail_merge)
    with pytest.raises(RuntimeError, match="injected merge failure"):
        service.import_industry_bundle("Broken", "Broken", bundle)

    assert not (tmp_path / "Broken").exists()
    with pytest.raises(FileNotFoundError):
        service.repo.industry_id("Broken")


def test_canonical_relation_admission_requires_current_industry_evidence(
        monkeypatch, tmp_path):
    _, service = _load(monkeypatch, tmp_path)
    document_id = service.repo.upsert_document("AI", "official", "2026-09-02", {
        "title": "Official relationship filing", "url": "https://filing.example/r1",
    })
    source_id = service.repo.upsert_entity("AI", {
        "name": "Source Co", "type": "company", "country": "CN"})
    target_id = service.repo.upsert_entity("AI", {
        "name": "Target Co", "type": "company", "country": "US"})

    candidate_id = service.repo.upsert_relation(
        "AI", source_id, "supplies", target_id,
        metadata={"references": [{"document_id": "foreign-document"}]})
    assert candidate_id.startswith("rlc_")
    assert service.repo.graph("AI")["edges"] == []
    assert any(item["id"] == candidate_id
               for item in service.repo.list_coverage_review_queue("AI")["relations"])

    relation_id = service.repo.upsert_relation(
        "AI", source_id, "supplies", target_id,
        references=[{"document_id": document_id}])
    assert relation_id.startswith("rel_")
    assert service.repo.graph("AI")["edges"][0]["id"] == relation_id
