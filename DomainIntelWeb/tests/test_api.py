from __future__ import annotations

import asyncio
import importlib
import io
import json
import sqlite3
import tomllib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import serialize_response
from pydantic import ValidationError
from DomainIntelWeb.api import schemas
from DomainIntelWeb.api.routers import agent_bridge as agent_bridge_module
from DomainIntelWeb.api.schemas import (AgentResultImport, CustomAgentProfile,
                                        GenerateRequest)

from intdog_core import IntDogService
from src.agent_evidence import (
    AssertionVerifier,
    ConfiguredSemanticEvaluator,
    EvaluationEvidence,
    EvidenceProbe,
    SemanticEvaluation,
    SemanticEvaluationRequest,
)


def load_api(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMAIN_INTEL_DATA_ROOT", str(tmp_path))
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    import DomainIntelWeb.api.main as module
    module = importlib.reload(module)
    return module, service


def test_health_and_overview_use_temporary_canonical_store(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    service.add_source("AI", "official", {
        "name": "Authority", "url": "https://authority.example/",
    })
    service.import_daily("AI", "news", "2026-08-31", [{
        "title": "A verified title", "url": "https://authority.example/a",
        "source": "Authority", "published_at": "2026-08-31T08:00:00+08:00",
    }])

    assert module.health()["status"] == "ready"
    assert module.industries()[0]["folder"] == "AI"
    overview = module.overview("AI")
    assert overview["stats"]["sources"] == 1
    assert overview["stats"]["documents"] == 1
    assert module.DATA_ROOT == tmp_path.resolve()


def test_background_state_and_authoritative_job_contract(monkeypatch, tmp_path):
    state_path = tmp_path / "desktop-background-state.json"
    state_path.write_text(json.dumps({
        "installed": True, "enabled": True, "platform": "linux",
        "intervalMinutes": 15, "errorCategory": "",
    }), encoding="utf-8")
    monkeypatch.setenv("INTDOG_BACKGROUND_STATE_PATH", str(state_path))
    module, service = load_api(monkeypatch, tmp_path)
    service.repo.update_schedule(
        "AI", "daily", enabled=True, local_time="08:00",
        pipeline_mode="aggregate", provider="public_sources")
    wake_id = service.repo.begin_worker_wakeup(
        "background-worker:test", origin="background_worker")
    service.repo.finish_worker_wakeup(
        wake_id, status="completed",
        summary={"claimed": 1, "completed": 1, "paused": 0, "failed": 0,
                 "next_run_at": "2026-09-03T08:00:00+08:00"})
    service.repo.grant_background_authorization(
        "AI", provider="openai", operation="weekly", actor="tester")
    task = service.repo.create_task(
        folder="AI", operation="daily", input={"folder": "AI"},
        origin="background_worker", provider="public_sources", model="",
        time_window={"start": "2026-09-01T04:00:00+08:00",
                     "end": "2026-09-02T08:00:00+08:00",
                     "timezone": "Asia/Shanghai"})

    background = _router_endpoint(module.system_router, "/background", "GET")()
    assert background["service"] == {
        "installed": True, "enabled": True, "platform": "linux",
        "interval_minutes": 15, "error_category": ""}
    assert background["last_wakeup"]["summary"]["completed"] == 1
    assert background["permissions"][0]["provider"] == "openai"
    assert background["email_delivery"] is False

    jobs = _router_endpoint(module.operations_router, "/jobs", "GET")()
    row = next(item for item in jobs if item["run_id"] == task["id"])
    assert row["origin"] == "background_worker"
    assert row["provider"] == "public_sources"
    assert row["time_window"]["timezone"] == "Asia/Shanghai"
    assert row["recovery_actions"] == ["cancel"]
    schemas.JobState.model_validate(row)

    paths = module.app.openapi()["paths"]
    assert paths["/api/background"]["get"]["responses"]["200"][
        "content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/BackgroundState"}


def test_setup_contract_is_redaction_safe_and_exposes_bidirectional_agent_bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "must-not-leak")
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "deepseek-chat")
    module, _ = load_api(monkeypatch, tmp_path)
    with monkeypatch.context() as scoped:
        scoped.setattr("src.services.agent_registry.discover_agents", lambda **_: [])
        scoped.setattr("src.services.provider_readiness.provider_readiness",
                       lambda name, _root: {
                           "provider": name, "ready": name == "deepseek",
                           "authenticated": name == "deepseek",
                       })
        payload = module.setup()
    assert payload["runtime_ready"] and payload["taskpack_ready"]
    assert payload["mcp_command"][-1] == "mcp-serve"
    assert {item["id"] for item in payload["mcp_configs"]} == {
        "codex", "claude", "workbuddy", "generic"}
    configs = {item["id"]: item for item in payload["mcp_configs"]}
    assert "intdog" in tomllib.loads(configs["codex"]["value"])["mcp_servers"]
    assert configs["workbuddy"]["value"]["mcpServers"]["intdog"]["args"][-1] == "mcp-serve"
    assert configs["claude"]["value"]["mcpServers"]["intdog"]["command"]
    assert next(row for row in payload["api_providers"] if row["id"] == "deepseek")["ready"]
    assert "must-not-leak" not in str(payload)


def _bridge_endpoint(module, suffix: str, method: str):
    return next(route.endpoint for route in module.agent_bridge_router.routes
                if getattr(route, "path", "").endswith(suffix)
                and method in getattr(route, "methods", set()))


def _router_endpoint(router, suffix: str, method: str):
    return next(route.endpoint for route in router.routes
                if getattr(route, "path", "").endswith(suffix)
                and method in getattr(route, "methods", set()))


def test_source_campaign_and_entity_coverage_workbench_contract(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    create_campaign = _router_endpoint(
        module.sources_router, "/source-campaigns", "POST")
    campaign = create_campaign("AI", schemas.SourceCampaignCreate(
        targets=["official", "news"], budget=20))
    assert campaign["status"] == "planned" and campaign["targets"] == ["official", "news"]
    service.repo.transition_source_campaign(campaign["id"], "running")
    query = service.repo.record_source_query(
        campaign["id"], round_no=1, language="zh", family="authoritative_baseline",
        dimensions={"source_type": "official", "region": "china"},
        query="AI 官方来源", outcome={"status": "completed", "returned_count": 3})
    candidate_ids = []
    for index in range(3):
        candidate = service.repo.upsert_source_candidate(campaign["id"], {
            "name": f"Authority {index}", "url": f"https://authority{index}.example/feed",
            "category": "official", "score": 90 - index,
            "selection_reason": "补足官方来源缺口", "query_id": query["id"],
            "entity": ({"name": "Example AI Lab", "type": "research_group",
                        "country": "CN", "chain": "Models",
                        "external_ids": {"registration": "LAB-1"},
                        "official_url": "https://lab.example"} if index == 0 else None),
        })
        candidate_ids.append(candidate["id"])

    detail = _router_endpoint(
        module.sources_router, "/source-campaigns/{campaign_id}", "GET")(
            "AI", campaign["id"], limit=2, offset=0)
    assert detail["candidate_page"]["total"] == 3
    assert len(detail["candidate_page"]["items"]) == 2
    assert detail["candidate_page"]["next_offset"] == 2
    assert detail["query_ledger"][0]["query"] == "AI 官方来源"
    gaps = {item["category"]: item for item in detail["source_gaps"]}
    assert gaps["official"]["current"] == 0 and gaps["official"]["target"] == 8
    assert gaps["official"]["candidate_count"] == 3
    assert gaps["news"]["current"] == 0
    assert all(item["explanation"] and "query_count" in item for item in gaps.values())

    reviewed = _router_endpoint(
        module.sources_router, "/source-candidates/{candidate_id}/review", "POST")(
            "AI", candidate_ids[1], schemas.SourceCandidateReview(
                decision="reserve", actor="analyst", reason="same owner overlap"))
    assert reviewed["status"] == "reserve"
    assert reviewed["review"]["reason"] == "same owner overlap"

    service.add_source("AI", "news", {
        "name": "Manual News", "url": "https://manual.example/feed"})
    source_id = service.repo.list_sources("AI")[0]["id"]
    reassessed = _router_endpoint(
        module.sources_router, "/sources/{source_id}/reassess", "POST")(
            "AI", source_id, schemas.SourceReassessmentRequest(
                decision="manual", actor="analyst", reason="login wall"))
    assert reassessed["state"] == "manual"
    assert reassessed["review"]["reason"] == "login wall"

    service.repo.upsert_chain_node("AI", {
        "name": "Models", "applicable_entity_types": ["research_group"],
        "high_research_value": True})
    for index in range(2):
        document_id = service.repo.upsert_document("AI", "official", "2026-09-01", {
            "title": f"Model Lab {index} registry",
            "url": f"https://registry.example/lab-{index}",
        })
        service.repo.upsert_entity("AI", {
            "name": f"Model Lab {index}", "type": "research_group", "country": "CN",
            "chain": "Models", "status": "accepted",
            "references": [{"document_id": document_id, "relation": "supports"}]})
    matrix = _router_endpoint(
        module.intelligence_router, "/coverage-matrix", "GET")("AI")
    china_cell = next(cell for cell in matrix["cells"] if cell["region"] == "china")
    assert (china_cell["chain_stage"], china_cell["entity_type"],
            china_cell["current"], china_cell["target"], china_cell["gap"]) == (
                "Models", "research_group", 2, 8, 6)
    assert china_cell["explanation"] and "relation_evidence" in china_cell

    frontier = _router_endpoint(
        module.intelligence_router, "/coverage-expansions", "POST")(
            "AI", schemas.CoverageExpansionRequest())
    assert frontier["cells"] and frontier["entity_queries"] and frontier["relation_queries"]
    assert frontier["round_id"] and frontier["round_no"] == 1
    history = _router_endpoint(
        module.intelligence_router, "/coverage-expansions", "GET")("AI")
    assert history[0]["id"] == frontier["round_id"]
    assert {query["kind"] for query in history[0]["queries"]} == {"entity", "relation"}

    identity = _router_endpoint(
        module.intelligence_router,
        "/entity-candidates/{candidate_id}/review", "POST")(
            "AI", candidate_ids[0], schemas.EntityCandidateReview(
                decision="approve", actor="analyst", reason="registration verified"))
    assert identity["decision"] == "created" and identity["entity_id"]
    assert identity["review"]["reason"] == "registration verified"

    operations = module.app.openapi()["paths"]
    expected = {
        "/api/industries/{folder}/source-campaigns": "SourceCampaignPage",
        "/api/industries/{folder}/coverage-matrix": "EntityCoverageMatrixState",
        "/api/industries/{folder}/coverage-expansions": "CoverageFrontierState",
    }
    for path, schema_name in expected.items():
        operation = operations[path]["get" if path.endswith("source-campaigns") or
                                      path.endswith("coverage-matrix") else "post"]
        response = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert response == {"$ref": f"#/components/schemas/{schema_name}"}


def test_story_momentum_and_quality_drift_typed_api_contract(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    document_id = service.repo.upsert_document("AI", "news", "2026-01-01", {
        "title": "Frontier release", "url": "https://authority.example/frontier",
        "published_at": "2026-01-01T05:00:00+08:00"})
    story_id = service.repo.save_story_groups("AI", [{
        "title": "Frontier release", "status": "collected",
        "metadata": {"source_quality": .8},
        "documents": [{"document_id": document_id,
                       "publisher_cluster": "authority-owner",
                       "observed_at": "2026-01-01T05:00:00+08:00"}],
    }], "momentum-v1")[0]
    service.repo.record_story_observation("AI", story_id, {
        "observed_at": "2026-01-02T05:00:00+08:00", "rank": 1, "score": .9,
        "publisher_clusters": ["authority-owner", "independent-owner"],
        "evidence_strength": .9, "classification": "open",
        "algorithm_version": "momentum-v1"})
    for observed_at, numerator in (("2026-01-01T05:00:00+08:00", .9),
                                   ("2026-01-08T05:00:00+08:00", .6)):
        service.repo.record_quality_observation("AI", {
            "observed_at": observed_at, "metric": "fixed_eval_quality",
            "numerator": numerator, "denominator": 1,
            "algorithm_version": "quality-v1",
            "dimensions": {"eval_set_id": "ai-api-golden-v1"}})

    momentum = _router_endpoint(
        module.intelligence_router, "/stories/{story_id}/momentum", "GET")(
            "AI", story_id)
    assert momentum["story_id"] == story_id
    assert momentum["status"] == "heating"
    assert momentum["timeline"][-1]["deltas"]["independent_publishers"] == 1
    assert all(link.startswith("observation://story/")
               for link in momentum["raw_observation_links"])

    drift = _router_endpoint(
        module.intelligence_router, "/quality-drift", "GET")(
            "AI", as_of="2026-01-08")
    seven_day = next(row for row in drift["metrics"] if row["window_days"] == 7)
    assert seven_day["status"] == "degraded"
    assert seven_day["denominator"] == 1 and seven_day["baseline_denominator"] == 1
    assert seven_day["raw_observation_links"]
    assert drift["columnar_prototype"]["authority"] == "sqlite"
    assert drift["columnar_prototype"]["write_path"] == "sqlite_only"

    ignored = _router_endpoint(
        module.intelligence_router, "/stories/{story_id}/ignore", "POST")(
            "AI", story_id, schemas.StoryIgnoreRequest(reason="not relevant"))
    assert ignored["status"] == "ignored"
    assert not any(row["id"] == story_id for row in service.repo.list_stories("AI"))

    operations = module.app.openapi()["paths"]
    expected = {
        "/api/industries/{folder}/stories/{story_id}/momentum": "StoryMomentumState",
        "/api/industries/{folder}/quality-drift": "QualityDriftState",
        "/api/industries/{folder}/stories/{story_id}/ignore": "StoryDetailState",
    }
    for path, schema_name in expected.items():
        method = "post" if path.endswith("/ignore") else "get"
        response = operations[path][method]["responses"]["200"][
            "content"]["application/json"]["schema"]
        assert response == {"$ref": f"#/components/schemas/{schema_name}"}


def _research_task(service):
    agenda_id = service.repo.upsert_research_agenda("AI", [{
        "dimension": "chain", "target_key": "models", "title": "模型证据",
        "priority": 80, "rationale": "补齐模型证据", "queries": ["model evidence"],
        "acceptance": {"citations": 2},
    }])[0]
    return service.create_research_task("AI", agenda_id, 5)


def _api_evaluator(decision="supported", *, evaluator_id="independent-verifier",
                   call_id="verification-call-1"):
    def evaluate(request):
        raw_type = str(request.atomic.get("predicate") or "")
        assertion_type = {
            "financial_figure": "financial", "company_disclosure":
            "formal_company_disclosure", "technical": "technical_performance",
            "forecast_estimate": "forecast", "estimate": "forecast",
            "causality": "causal", "investment": "investment_judgment",
        }.get(raw_type, raw_type)
        return [SemanticEvaluation(
            evidence_id=item.evidence_id, decision=decision,
            reason=f"{decision} by configured API evaluator",
            content_hash=item.content_hash, locator=item.locator,
            evaluator_call_id=call_id, assertion_type=assertion_type,
        ) for item in request.evidence if item.role == "support"]
    return ConfiguredSemanticEvaluator(
        evaluator_id=evaluator_id, method="independent_model", evaluate=evaluate)


def _router_with_verifier(module, verifier):
    return agent_bridge_module.build_agent_bridge_router(
        data_root=module.DATA_ROOT, dataio=module.dataio,
        resolve_folder=module._folder, service=module.service, verifier=verifier)


def test_agent_result_import_is_review_gated_atomic_and_idempotent(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    endpoint = _bridge_endpoint(module, "/agent-bridge/results", "POST")
    before = service.repo.knowledge_stats("AI")
    payload = AgentResultImport(task_id=task["id"], agent_id="external-agent",
        summary="Evidence-backed result", assertions=[{
            "text": "A bounded claim", "citations": ["https://example.com/source"]}])
    first = endpoint("AI", payload)
    second = endpoint("AI", payload)
    assert first["status"] == "draft_review_required" and not first["duplicate"]
    assert second["duplicate"] and second["content_sha256"] == first["content_sha256"]
    review = _bridge_endpoint(module, "/review", "POST")
    reviewed = review("AI", first["result_id"], schemas.AgentReviewRequest(
        assertion_id=first["assertions"][0]["id"], decision="opinion",
        note="retain as analysis"))
    assert reviewed["status"] == "opinion"
    third = endpoint("AI", payload)
    assert third["duplicate"] and third["status"] == "opinion"
    listing = _bridge_endpoint(module, "/agent-bridge/results", "GET")
    page = listing("AI", limit=1, offset=0)
    assert page["total"] == 1 and page["items"][0]["status"] == "opinion"
    assert service.repo.knowledge_stats("AI") == before
    audits = service.repo.list_audits(limit=20)
    assert sum(row["action"] == "import_agent_result" for row in audits) == 1
    assert sum(row["action"] == "review_agent_assertion" for row in audits) == 1


def test_agent_bridge_openapi_has_ten_concrete_response_models(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    expected = {
        ("/api/agent-bridge/profiles", "GET"): "AgentProfilePage",
        ("/api/agent-bridge/profiles", "POST"): "CustomAgentProfile",
        ("/api/agent-bridge/profiles/{profile_id}", "DELETE"): "AgentProfileDeleteState",
        ("/api/industries/{folder}/agent-bridge/tasks", "GET"): "AgentTaskPage",
        ("/api/industries/{folder}/agent-bridge/tasks/{task_id}", "GET"): "AgentTaskExport",
        ("/api/industries/{folder}/agent-bridge/results", "GET"): "AgentResultPage",
        ("/api/industries/{folder}/agent-bridge/results/{result_id}", "GET"): "AgentResultState",
        ("/api/industries/{folder}/agent-bridge/results", "POST"): "AgentResultState",
        ("/api/industries/{folder}/agent-bridge/results/{result_id}/review", "POST"): "AgentResultState",
        ("/api/industries/{folder}/agent-bridge/results/{result_id}/verify", "POST"): "AgentVerificationState",
    }
    contract = module.app.openapi()
    for (path, method), model in expected.items():
        response = contract["paths"][path][method.lower()]["responses"]
        code = next(key for key in ("200", "201", "501") if key in response)
        schema = response[code]["content"]["application/json"]["schema"]
        assert schema == {"$ref": f"#/components/schemas/{model}"}


def test_agent_task_export_declares_atomic_assertion_and_generation_provenance(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    exported = _bridge_endpoint(
        module, "/agent-bridge/tasks/{task_id}", "GET")("AI", task["id"])

    contract = exported["result_contract"]
    assertion = contract["assertions"][0]
    assert contract["generation_call_id"] == "unique-generation-call-id"
    assert assertion["type"] == "identity|event|market_size|financial|technical_performance|causal|forecast|opinion"
    assert assertion["atomic"] == {
        "subject": "string", "subject_id": "canonical-entity-id",
        "predicate": "string", "object": "value",
        "time": "ISO-8601 or explicit period", "region": "string",
        "value": "number|null", "unit": "string|null",
        "currency": "ISO-4217|null", "period": "string|null",
        "statistical_definition": "string|null", "qualifiers": {},
    }
    assert assertion["citations"] == [{
        "url": "https://...", "role": "support|conversion_benchmark",
        "content_hash": "sha256-hex",
        "locator": {"type": "text_offset", "start": 0, "end": 1},
    }]


def test_agent_verification_checks_have_concrete_typed_schema():
    annotation = schemas.AgentVerificationDecisionState.model_fields["checks"].annotation
    assert annotation is schemas.AgentVerificationChecks
    semantic = schemas.AgentVerificationChecks.model_fields["semantic_support"].annotation
    assert semantic is schemas.AgentSemanticCheck
    assertion_schema = schemas.AgentAssertionState.model_json_schema()
    verification = assertion_schema["properties"]["verification"]
    assert any(item.get("$ref", "").endswith("/AgentVerificationChecks")
               for item in verification["anyOf"])
    assert "additionalProperties" not in verification


def test_agent_gate_check_forbids_unknown_details_and_types_every_known_detail():
    gate_schema = schemas.AgentGateCheck.model_json_schema()
    assert gate_schema["additionalProperties"] is False
    expected_details = {
        "atomic", "failures", "publishers", "publication_times", "entity_ids",
        "expected_entity_id", "generation_call_id", "generator_id",
        "independent_verifiers", "evaluator_mode", "errors", "retryable",
        "conversions", "declared_type", "inferred_type", "signals",
        "inconsistent_signals", "independent_assertion_types", "assertion_type",
        "high_risk_signals",
        "independent_clusters", "conflicting_claim_ids", "claim", "evidence",
    }
    assert expected_details.issubset(gate_schema["properties"])
    assert all(gate_schema["properties"][field]
               for field in expected_details)
    with pytest.raises(ValidationError):
        schemas.AgentGateCheck(
            status="passed", reason="typed", evidence_ids=[], locators=[],
            agent_controlled_payload={"passed": True})


def test_locator_contracts_are_discriminated_and_have_no_any_placeholders():
    citation_schema = schemas.AgentCitationInput.model_json_schema()
    locator = citation_schema["properties"]["locator"]
    discriminated = locator["anyOf"][0]
    assert discriminated["discriminator"]["propertyName"] == "type"
    assert set(discriminated["discriminator"]["mapping"]) == {
        "text_offset", "html_selector", "pdf_page", "api_field"}
    serialized = json.dumps(schemas.AgentGateCheck.model_json_schema(), sort_keys=True)
    assert "typing.Any" not in serialized
    assert "text_offset|html_selector" not in serialized
    assert "type-specific coordinates" not in serialized


def test_main_wires_production_verifier_from_explicit_local_configuration(
        monkeypatch, tmp_path):
    monkeypatch.delenv("INTDOG_VERIFIER_PROVIDER", raising=False)
    module, _ = load_api(monkeypatch, tmp_path)
    assert isinstance(module.agent_bridge_verifier, AssertionVerifier)
    assert module.agent_bridge_verifier.semantic_evaluator is None


def test_main_builds_configured_production_evaluator_from_provider_registry(
        monkeypatch, tmp_path):
    semantic_verifier = importlib.import_module("src.services.semantic_verifier")
    class Provider:
        def complete(self, _prompt):
            return type("Result", (), {
                "text": json.dumps([{"evidence_id": "citation-1",
                                     "semantic": "supported",
                                     "assertion_type": "identity",
                                     "reason": "excerpt directly states assertion",
                                     "entity_ids": [], "numeric_observations": [],
                                     "document_content_type": "official_record",
                                     "experimental_conditions": {},
                                     "locator": {"type": "text_offset", "start": 0,
                                                 "end": 6},
                                     "located_text": "NVIDIA is an AI company"}]),
                "response_id": "provider-response-1",
            })()
    monkeypatch.setattr(semantic_verifier, "create_provider",
                        lambda _config, _provider, _workspace: Provider())
    monkeypatch.setenv("INTDOG_VERIFIER_PROVIDER", "codex")
    module, _ = load_api(monkeypatch, tmp_path)
    evaluator = module.agent_bridge_verifier.semantic_evaluator
    assert evaluator is not None
    assert evaluator.evaluator_id == "codex"
    assert evaluator.method == "independent_model"
    results = evaluator.evaluate(SemanticEvaluationRequest(
        assertion_id="assertion-1", assertion_text="NVIDIA is an AI company",
        atomic={"subject": "NVIDIA", "predicate": "identity"},
        evidence=(EvaluationEvidence(
            evidence_id="citation-1", role="support", content_hash="a" * 64,
            locator={"type": "text_offset", "start": 0, "end": 6},
            excerpt="NVIDIA is an AI company"),)))
    assert results[0].decision == "supported"
    assert results[0].evaluator_call_id == "provider-response-1"


class _PublicFetchResponse:
    def __init__(self, url, text):
        self.url, self.text = url, text
        self.status_code, self.encoding = 200, "utf-8"
        self.headers = {"Last-Modified": "Mon, 31 Aug 2026 12:00:00 GMT"}
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def iter_content(self, _size):
        yield self.text.encode("utf-8")


def test_production_factory_main_router_accepts_complete_non_numeric_and_numeric_probes(
        monkeypatch, tmp_path):
    semantic_verifier = importlib.import_module("src.services.semantic_verifier")
    texts = {
        "https://sec.gov/identity": "NVIDIA is an AI company.",
            "https://sec.gov/Archives/edgar/data/1/filing":
            "Example Corp FY2025 GAAP revenue was 90 million EUR.",
        "https://sec.gov/rate":
            "EUR to USD multiply rate 1.1; million to million; FY2025; tolerance 0",
    }
    entity_ids = {}

    class Provider:
        def complete(self, prompt):
            payload = json.loads(prompt.splitlines()[-1])
            atomic = payload["atomic"]
            rows = []
            for item in payload["evidence"]:
                numeric = []
                if atomic.get("value") is not None and item["role"] == "support":
                    numeric = [{"kind": "assertion_value", "value": 90,
                        "unit": "million", "currency": "EUR",
                        "period": "FY2025", "statistical_definition": "GAAP revenue",
                        "conversion": {"original_value": 90, "target_value": 99,
                            "target_unit": "million", "target_currency": "USD",
                            "formula": "multiply", "rate": "1.1",
                            "benchmark_source": "https://sec.gov/rate"}}]
                elif item["role"] == "conversion_benchmark":
                    numeric = [{"kind": "conversion_rate", "rate": "1.1",
                        "formula": "multiply", "from_currency": "EUR",
                        "to_currency": "USD", "from_unit": "million",
                        "to_unit": "million", "period": "FY2025",
                        "tolerance": "0"}]
                rows.append({
                    "evidence_id": item["evidence_id"],
                    "semantic": "supported" if item["role"] == "support" else "unknown",
                    "assertion_type": ("financial" if
                                       atomic.get("predicate") == "financial" else "identity"),
                    "reason": "located excerpt supports the assertion",
                    "entity_ids": ([atomic["subject_id"]]
                                   if item["role"] == "support" else []),
                    "numeric_observations": numeric,
                    "document_content_type": ("regulatory_filing"
                                              if item["role"] == "support" else "official_record"),
                    "experimental_conditions": {},
                    "locator": item["locator"], "located_text": item["excerpt"],
                })
            return type("Result", (), {"text": json.dumps(rows),
                                        "response_id": "provider-rich-1"})()

    monkeypatch.setattr(semantic_verifier, "create_provider",
                        lambda _config, _provider, _workspace: Provider())
    def fetched_probe(url, *, locator, expected_hash):
        content = texts[url]
        assert expected_hash == __import__("hashlib").sha256(content.encode()).hexdigest()
        return EvidenceProbe(
            True, url, 200, published_at="2026-08-31T12:00:00+00:00",
            content=content, content_hash=expected_hash, locator=locator,
            located_text=content[locator["start"]:locator["end"]])
    monkeypatch.setattr(semantic_verifier, "probe_agent_evidence", fetched_probe)
    monkeypatch.setenv("INTDOG_VERIFIER_PROVIDER", "codex")
    module, _ = load_api(monkeypatch, tmp_path)
    task = _research_task(module.service)
    entity_ids["NVIDIA"] = module.service.repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US", "status": "accepted"})
    entity_ids["Example Corp"] = module.service.repo.upsert_entity("AI", {
        "name": "Example Corp", "type": "company", "country": "US",
        "status": "accepted"})
    imported = _bridge_endpoint(module, "/agent-bridge/results", "POST")(
        "AI", AgentResultImport(
            task_id=task["id"], agent_id="generator", generation_call_id="generation-1",
            summary="production structured verification", assertions=[
                {"text": "NVIDIA is an AI company", "type": "identity",
                 "atomic": {"subject": "NVIDIA", "subject_id": entity_ids["NVIDIA"],
                            "predicate": "identity", "object": "AI company",
                            "time": "2026", "region": "US"},
                 "citations": [{"url": "https://sec.gov/identity",
                    "content_hash": __import__("hashlib").sha256(
                        texts["https://sec.gov/identity"].encode()).hexdigest(),
                    "locator": {"type": "text_offset", "start": 0,
                                "end": len(texts["https://sec.gov/identity"])}}]},
                {"text": "Example Corp FY2025 GAAP revenue was USD 99 million",
                 "type": "financial",
                 "atomic": {"subject": "Example Corp",
                            "subject_id": entity_ids["Example Corp"],
                            "predicate": "financial", "object": "FY2025 revenue",
                            "time": "2025", "region": "US", "value": 99,
                            "unit": "million", "currency": "USD", "period": "FY2025",
                            "statistical_definition": "GAAP revenue"},
                 "citations": [
                     {"url": "https://sec.gov/Archives/edgar/data/1/filing",
                      "role": "support",
                      "content_hash": __import__("hashlib").sha256(
                          texts["https://sec.gov/Archives/edgar/data/1/filing"].encode()
                      ).hexdigest(),
                      "locator": {"type": "text_offset", "start": 0,
                                  "end": len(texts[
                                      "https://sec.gov/Archives/edgar/data/1/filing"])}},
                     {"url": "https://sec.gov/rate", "role": "conversion_benchmark",
                      "content_hash": __import__("hashlib").sha256(
                          texts["https://sec.gov/rate"].encode()).hexdigest(),
                      "locator": {"type": "text_offset", "start": 0,
                                  "end": len(texts["https://sec.gov/rate"])}}]},
            ]))
    review = _bridge_endpoint(module, "/review", "POST")
    for assertion in imported["assertions"]:
        review("AI", imported["result_id"], schemas.AgentReviewRequest(
            assertion_id=assertion["id"], decision="submitted_for_verification"))
    state = _bridge_endpoint(module, "/verify", "POST")("AI", imported["result_id"])
    assert state["status"] == "verified", state
    assert [item["disposition"] for item in state["decisions"]] == ["accepted", "accepted"]


def test_production_provider_missing_structured_probe_fields_stays_candidate(
        monkeypatch, tmp_path):
    semantic_verifier = importlib.import_module("src.services.semantic_verifier")
    class Provider:
        def complete(self, prompt):
            payload = json.loads(prompt.splitlines()[-1])
            row = payload["evidence"][0]
            return type("Result", (), {"text": json.dumps([{
                "evidence_id": row["evidence_id"], "semantic": "supported",
                "reason": "all structured fields except evaluator type",
                "entity_ids": [payload["atomic"]["subject_id"]],
                "numeric_observations": [], "document_content_type": "official_record",
                "experimental_conditions": {},
                "locator": row["locator"], "located_text": row["excerpt"]}]),
                "response_id": "provider-incomplete"})()
    monkeypatch.setattr(semantic_verifier, "create_provider",
                        lambda *_args: Provider())
    content = "NVIDIA is an AI company."
    content_hash = __import__("hashlib").sha256(content.encode()).hexdigest()
    monkeypatch.setattr(semantic_verifier, "probe_agent_evidence", lambda url, *,
        locator, expected_hash: EvidenceProbe(
            True, url, 200, published_at="2026-08-31T12:00:00+00:00",
            content=content, content_hash=expected_hash, locator=locator,
            located_text=content[locator["start"]:locator["end"]]))
    monkeypatch.setenv("INTDOG_VERIFIER_PROVIDER", "codex")
    module, _ = load_api(monkeypatch, tmp_path)
    task = _research_task(module.service)
    entity_id = module.service.repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US", "status": "accepted"})
    imported = _bridge_endpoint(module, "/agent-bridge/results", "POST")(
        "AI", AgentResultImport(
            task_id=task["id"], agent_id="generator", generation_call_id="generation-1",
            summary="incomplete production probe", assertions=[{
                "text": "NVIDIA is an AI company", "type": "identity",
                "atomic": {"subject": "NVIDIA", "subject_id": entity_id,
                           "predicate": "identity", "object": "AI company",
                           "time": "2026", "region": "US"},
                "citations": [{"url": "https://sec.gov/identity",
                    "content_hash": content_hash,
                    "locator": {"type": "text_offset", "start": 0,
                                "end": len(content)}}]}]))
    _bridge_endpoint(module, "/review", "POST")(
        "AI", imported["result_id"], schemas.AgentReviewRequest(
            assertion_id=imported["assertions"][0]["id"],
            decision="submitted_for_verification"))
    state = _bridge_endpoint(module, "/verify", "POST")("AI", imported["result_id"])
    assert state["decisions"][0]["disposition"] == "candidate"
    semantic = state["decisions"][0]["checks"]["semantic_support"]
    assert semantic["retryable"] is True
    assert "ValueError" in semantic["reason"]
    assert module.service.repo._get_agent_assertion(
        "AI", imported["assertions"][0]["id"])["status"] == \
        "submitted_for_verification"


def test_production_provider_receives_only_locator_excerpt_not_full_pdf_page(
        monkeypatch, tmp_path):
    semantic_verifier = importlib.import_module("src.services.semantic_verifier")
    prompts = []

    class Provider:
        def complete(self, prompt):
            prompts.append(prompt)
            payload = json.loads(prompt.splitlines()[-1])
            item = payload["evidence"][0]
            return type("Result", (), {"text": json.dumps([{
                "evidence_id": item["evidence_id"], "semantic": "supported",
                "assertion_type": "identity", "reason": "excerpt supports identity",
                "entity_ids": [], "numeric_observations": [],
                "document_content_type": "official_record",
                "experimental_conditions": {}, "locator": item["locator"],
                "located_text": item["excerpt"],
            }]), "response_id": "minimal-prompt"})()

    monkeypatch.setattr(semantic_verifier, "create_provider", lambda *_args: Provider())
    verifier = semantic_verifier.build_production_assertion_verifier(
        tmp_path, {"INTDOG_VERIFIER_PROVIDER": "codex"})
    evaluator = verifier.semantic_evaluator
    evaluator.evaluate(SemanticEvaluationRequest(
        assertion_id="assertion-minimal", assertion_text="NVIDIA is a company",
        atomic={"subject": "NVIDIA", "predicate": "identity"},
        evidence=(EvaluationEvidence(
            evidence_id="citation-minimal", role="support", content_hash="a" * 64,
            locator={"type": "pdf_page", "page": 2, "start": 0, "end": 8},
            excerpt="evidence", page_texts=("SECRET FULL PAGE MUST NOT LEAVE DEVICE",)),)))
    assert "SECRET FULL PAGE MUST NOT LEAVE DEVICE" not in prompts[0]
    assert '"excerpt": "evidence"' in prompts[0]
    assert '"page_texts"' not in prompts[0]


@pytest.mark.parametrize(("provider_batch", "expected"), [
    ("1", "accepted"),
    ("2", "candidate"),
])
def test_production_factory_reproduces_academic_conditions_per_field(
        monkeypatch, tmp_path, provider_batch, expected):
    semantic_verifier = importlib.import_module("src.services.semantic_verifier")
    url = "https://nature.com/articles/ai-benchmark"
    content = "NVIDIA benchmark result; batch=1; precision=FP16."

    class Provider:
        def complete(self, prompt):
            payload = json.loads(prompt.splitlines()[-1])
            item = payload["evidence"][0]
            return type("Result", (), {"text": json.dumps([{
                "evidence_id": item["evidence_id"], "semantic": "supported",
                "assertion_type": "technical_performance",
                "reason": "conditioned academic result supports the assertion",
                "entity_ids": [payload["atomic"]["subject_id"]],
                "numeric_observations": [],
                "document_content_type": "academic_result",
                "experimental_conditions": {
                    "batch": provider_batch, "precision": "FP16"},
                "locator": item["locator"], "located_text": item["excerpt"],
            }]), "response_id": f"academic-{provider_batch}"})()

    monkeypatch.setattr(semantic_verifier, "create_provider", lambda *_args: Provider())
    content_hash = __import__("hashlib").sha256(content.encode()).hexdigest()
    monkeypatch.setattr(semantic_verifier, "probe_agent_evidence", lambda fetched_url, *,
        locator, expected_hash, **_kwargs: EvidenceProbe(
            True, fetched_url, 200, published_at="2026-08-31T12:00:00+00:00",
            content=content, content_hash=expected_hash, locator=locator,
            located_text=content[locator["start"]:locator["end"]]))
    monkeypatch.setenv("INTDOG_VERIFIER_PROVIDER", "codex")
    module, _ = load_api(monkeypatch, tmp_path)
    task = _research_task(module.service)
    entity_id = module.service.repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US", "status": "accepted"})
    imported = _bridge_endpoint(module, "/agent-bridge/results", "POST")(
        "AI", AgentResultImport(
            task_id=task["id"], agent_id="generator",
            generation_call_id="academic-generation", summary="academic probe",
            assertions=[{"text": "NVIDIA benchmark result",
                "type": "technical_performance",
                "atomic": {"subject": "NVIDIA", "subject_id": entity_id,
                    "predicate": "technical_performance", "object": "benchmark result",
                    "time": "2026", "region": "US"},
                "citations": [{"url": url, "content_hash": content_hash,
                    "locator": {"type": "text_offset", "start": 0,
                                "end": len(content)}}]}]))
    assertion_id = imported["assertions"][0]["id"]
    _bridge_endpoint(module, "/review", "POST")(
        "AI", imported["result_id"], schemas.AgentReviewRequest(
            assertion_id=assertion_id, decision="submitted_for_verification"))
    state = _bridge_endpoint(module, "/verify", "POST")("AI", imported["result_id"])
    decision = state["decisions"][0]
    assert decision["disposition"] == expected
    assert decision["checks"]["semantic_support"]["retryable"] is False
    assert decision["checks"]["corroboration"]["status"] == (
        "passed" if expected == "accepted" else "failed")


def test_agent_import_schema_enforces_runtime_assertion_and_citation_budgets():
    assertion = {"text": "bounded", "citations": ["https://sec.gov/evidence"]}
    with pytest.raises(ValidationError):
        AgentResultImport(
            task_id="task", agent_id="agent", summary="too many assertions",
            assertions=[assertion for _ in range(101)])
    with pytest.raises(ValidationError):
        schemas.AgentAssertion(
            text="too many citations",
            citations=[f"https://sec.gov/{index}" for index in range(21)])


def test_main_starts_with_retryable_verifier_when_provider_factory_fails(
        monkeypatch, tmp_path):
    semantic_verifier = importlib.import_module("src.services.semantic_verifier")
    monkeypatch.setattr(
        semantic_verifier, "create_provider",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("secret sk-must-not-leak")))
    monkeypatch.setenv("INTDOG_VERIFIER_PROVIDER", "codex")
    module, _ = load_api(monkeypatch, tmp_path)
    assert module.agent_bridge_verifier.semantic_evaluator is None
    diagnostic = module.agent_bridge_verifier.configuration_diagnostic
    assert "provider" in diagnostic.casefold()
    assert "sk-must-not-leak" not in diagnostic


def test_invalid_locator_candidate_serializes_through_real_fastapi_response_model(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    entity_id = service.repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US", "status": "accepted"})
    content = "NVIDIA is an AI company."
    invalid_probe = EvidenceProbe(
        reachable=True, final_url="https://sec.gov/invalid-locator", status_code=200,
        published_at="2026-08-31T12:00:00+00:00", content=content,
        content_hash=__import__("hashlib").sha256(content.encode()).hexdigest(),
        locator={}, located_text=content, entity_ids=(entity_id,),
        publisher_kind="official_record")
    router = _router_with_verifier(module, AssertionVerifier(
        fetch=lambda _url: invalid_probe, semantic_evaluator=_api_evaluator()))
    import_result = next(route.endpoint for route in router.routes
                         if route.path.endswith("/agent-bridge/results")
                         and "POST" in route.methods)
    imported = import_result("AI", AgentResultImport(
        task_id=task["id"], agent_id="generator",
        generation_call_id="generation-call-1", summary="invalid locator response",
        assertions=[{
            "text": content, "type": "identity",
            "atomic": {"subject": "NVIDIA", "subject_id": entity_id,
                       "predicate": "identity", "object": "AI company",
                       "time": "2026", "region": "US"},
            "citations": ["https://sec.gov/invalid-locator"],
        }]))
    review = next(route.endpoint for route in router.routes
                  if route.path.endswith("/review") and "POST" in route.methods)
    review("AI", imported["result_id"], schemas.AgentReviewRequest(
        assertion_id=imported["assertions"][0]["id"],
        decision="submitted_for_verification"))
    verify_route = next(route for route in router.routes
                        if route.path.endswith("/verify") and "POST" in route.methods)
    endpoint_state = verify_route.endpoint("AI", imported["result_id"])
    response_state = asyncio.run(serialize_response(
        field=verify_route.response_field, response_content=endpoint_state,
        by_alias=True, exclude_unset=False, exclude_defaults=False,
        exclude_none=False, is_coroutine=True))

    decision = response_state["decisions"][0]
    assert decision["disposition"] == "candidate"
    locator_check = decision["checks"]["locator_integrity"]
    assert locator_check["locators"] == []
    assert locator_check["failures"] == [{
        "evidence_id": imported["assertions"][0]["citations"][0]["id"],
        "reason": "a reproducible locator type is required",
        "status_code": None,
        "failure_code": "invalid_locator",
        "invalid_locator_type": None,
        "content_hash_present": True,
    }]


def test_oversized_verification_response_is_serialized_as_bounded_summary(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    entity_id = service.repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US", "status": "accepted"})
    content = "NVIDIA is an AI company."
    probe = EvidenceProbe(
        True, "https://sec.gov/bounded-response", 200,
        published_at="2026-08-31T12:00:00+00:00", content=content,
        content_hash=__import__("hashlib").sha256(content.encode()).hexdigest(),
        locator={"type": "text_offset", "start": 0, "end": len(content)},
        located_text=content, entity_ids=(entity_id,))
    router = _router_with_verifier(module, AssertionVerifier(
        fetch=lambda _url: probe, semantic_evaluator=_api_evaluator()))
    import_result = next(route.endpoint for route in router.routes
                         if route.path.endswith("/agent-bridge/results")
                         and "POST" in route.methods)
    imported = import_result("AI", AgentResultImport(
        task_id=task["id"], agent_id="generator", generation_call_id="bounded-call",
        summary="bounded response", assertions=[{
            "text": "NVIDIA is an AI company", "type": "identity",
            "atomic": {"subject": "NVIDIA", "subject_id": entity_id,
                       "predicate": "identity", "object": "x" * 300_000,
                       "time": "2026", "region": "US"},
            "citations": ["https://sec.gov/bounded-response"],
        }]))
    review = next(route.endpoint for route in router.routes
                  if route.path.endswith("/review") and "POST" in route.methods)
    review("AI", imported["result_id"], schemas.AgentReviewRequest(
        assertion_id=imported["assertions"][0]["id"],
        decision="submitted_for_verification"))
    verify_route = next(route for route in router.routes
                        if route.path.endswith("/verify") and "POST" in route.methods)
    response_state = asyncio.run(serialize_response(
        field=verify_route.response_field,
        response_content=verify_route.endpoint("AI", imported["result_id"]),
        by_alias=True, exclude_unset=False, exclude_defaults=False,
        exclude_none=False, is_coroutine=True))
    encoded = json.dumps(response_state, ensure_ascii=False).encode()
    assert len(encoded) <= 256 * 1024
    truncation = response_state["decisions"][0]["checks"][
        "resource_budget"]["budget_truncation"]
    assert truncation["original_bytes"] > 256 * 1024
    with service.repo.connection() as con:
        stored = con.execute(
            "SELECT verification_json FROM agent_assertions WHERE id=?",
            (imported["assertions"][0]["id"],)).fetchone()[0]
    assert len(stored.encode()) <= 256 * 1024


def test_verify_aggregate_paginates_thirty_assertions_with_bounded_responses(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    entity_id = service.repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US", "status": "accepted"})
    content = "NVIDIA is an AI company."
    probe = EvidenceProbe(
        True, "https://sec.gov/paged-verification", 200,
        published_at="2026-08-31T12:00:00+00:00", content=content,
        content_hash=__import__("hashlib").sha256(content.encode()).hexdigest(),
        locator={"type": "text_offset", "start": 0, "end": len(content)},
        located_text=content, entity_ids=(entity_id,))
    router = _router_with_verifier(module, AssertionVerifier(
        fetch=lambda _url: probe, semantic_evaluator=_api_evaluator()))
    import_result = next(route.endpoint for route in router.routes
                         if route.path.endswith("/agent-bridge/results")
                         and "POST" in route.methods)
    assertions = [{
        "text": f"NVIDIA is an AI company assertion {index}", "type": "identity",
        "atomic": {"subject": "NVIDIA", "subject_id": entity_id,
                   "predicate": "identity", "object": "x" * 4_000,
                   "time": "2026", "region": "US"},
        "citations": ["https://sec.gov/paged-verification"],
    } for index in range(30)]
    imported = import_result("AI", AgentResultImport(
        task_id=task["id"], agent_id="generator", generation_call_id="paged-call",
        summary="thirty bounded assertions", assertions=assertions))
    review = next(route.endpoint for route in router.routes
                  if route.path.endswith("/review") and "POST" in route.methods)
    for assertion in imported["assertions"]:
        review("AI", imported["result_id"], schemas.AgentReviewRequest(
            assertion_id=assertion["id"], decision="submitted_for_verification"))
    verify_route = next(route for route in router.routes
                        if route.path.endswith("/verify") and "POST" in route.methods)
    pages, seen = [], []
    for offset in (0, 10, 20):
        response_state = asyncio.run(serialize_response(
            field=verify_route.response_field,
            response_content=verify_route.endpoint(
                "AI", imported["result_id"], limit=10, offset=offset),
            by_alias=True, exclude_unset=False, exclude_defaults=False,
            exclude_none=False, is_coroutine=True))
        encoded = json.dumps(response_state, ensure_ascii=False).encode()
        assert len(encoded) <= 256 * 1024
        assert response_state["total"] == 30
        assert response_state["offset"] == offset
        assert response_state["limit"] == 10
        pages.append(response_state["next_offset"])
        seen.extend(item["assertion_id"] for item in response_state["decisions"])
    assert pages == [10, 20, None]
    assert len(seen) == len(set(seen)) == 30


def test_verify_pagination_is_typed_in_openapi(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    operation = module.app.openapi()["paths"][
        "/api/industries/{folder}/agent-bridge/results/{result_id}/verify"]["post"]
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert parameters["limit"]["schema"]["default"] == 10
    assert parameters["limit"]["schema"]["maximum"] == 10
    assert parameters["offset"]["schema"]["minimum"] == 0
    state_schema = module.app.openapi()["components"]["schemas"][
        "AgentVerificationState"]
    assert {"total", "offset", "limit", "next_offset"}.issubset(
        state_schema["properties"])


def test_agent_result_listing_and_detail_use_schema_14_repository(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    imported = _bridge_endpoint(module, "/agent-bridge/results", "POST")(
        "AI", AgentResultImport(task_id=task["id"], agent_id="agent",
        summary="repository authority", assertions=[{
            "text": "claim", "citations": ["https://example.com/evidence"]}]))
    artifact = Path(imported["original_file"])
    artifact.write_text("{corrupt", encoding="utf-8")

    detail = _bridge_endpoint(module, "/agent-bridge/results/{result_id}", "GET")(
        "AI", imported["result_id"])
    page = _bridge_endpoint(module, "/agent-bridge/results", "GET")(
        "AI", limit=100, offset=0)

    assert detail["summary"] == "repository authority"
    assert page["total"] == 1
    assert page["items"][0]["result_id"] == imported["result_id"]


def test_agent_result_legacy_id_resolves_and_returns_internal_state(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    legacy_id = "a" * 64
    artifact = (tmp_path / "AI" / "one_time" / "agent_results" /
                task["id"] / f"{legacy_id}.json")
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({
        "task_id": task["id"], "agent_id": "agent", "summary": "legacy lookup",
        "assertions": [{"text": "claim", "type": "unspecified",
                        "citations": ["https://example.com/evidence"]}],
        "industry": "AI", "status": "draft_review_required",
        "content_sha256": legacy_id, "result_id": legacy_id,
        "created_at": "2026-09-01T00:00:00+00:00",
    }, indent=2, sort_keys=True), encoding="utf-8")
    original_read_text = Path.read_text
    def reject_unbounded_artifact_read(path, *args, **kwargs):
        if path.resolve() == artifact.resolve():
            raise AssertionError("legacy artifact must not be read with read_text")
        return original_read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", reject_unbounded_artifact_read)
    detail = _bridge_endpoint(module, "/agent-bridge/results/{result_id}", "GET")
    indexed = detail("AI", legacy_id)
    assert indexed["result_id"].startswith("agr_")

    review = _bridge_endpoint(module, "/review", "POST")
    reviewed = review("AI", legacy_id, schemas.AgentReviewRequest(
        assertion_id=indexed["assertions"][0]["id"], decision="opinion"))
    assert reviewed["result_id"] == indexed["result_id"]
    assert reviewed["status"] == "opinion"

    verify = _bridge_endpoint(module, "/verify", "POST")
    assert verify("AI", legacy_id)["result_id"] == indexed["result_id"]


def test_agent_result_legacy_id_rejects_missing_and_ambiguous_artifacts(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    imported = _bridge_endpoint(module, "/agent-bridge/results", "POST")(
        "AI", AgentResultImport(task_id=task["id"], agent_id="agent",
        summary="ambiguous lookup", assertions=[{
            "text": "claim", "citations": ["https://example.com/evidence"]}]))
    legacy_id = Path(imported["original_file"]).stem
    duplicate_path = (tmp_path / "AI" / "one_time" / "agent_results" /
                      "duplicate" / f"{legacy_id}.json")
    duplicate_path.parent.mkdir(parents=True)
    duplicate_path.write_bytes(Path(imported["original_file"]).read_bytes())
    detail = _bridge_endpoint(module, "/agent-bridge/results/{result_id}", "GET")
    with pytest.raises(HTTPException) as ambiguous:
        detail("AI", legacy_id)
    assert ambiguous.value.status_code == 409
    with pytest.raises(HTTPException) as missing:
        detail("AI", "f" * 64)
    assert missing.value.status_code == 404


def test_agent_bridge_legacy_corrupt_and_oversized_files_fail_deterministically(
        monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    base = tmp_path / "AI" / "one_time" / "agent_results" / "legacy"
    base.mkdir(parents=True)
    (base / ("a" * 64 + ".json")).write_text("{broken", encoding="utf-8")
    listing = _bridge_endpoint(module, "/agent-bridge/results", "GET")
    with pytest.raises(HTTPException) as corrupt:
        listing("AI", limit=50, offset=0)
    assert corrupt.value.status_code == 409

    (base / ("a" * 64 + ".json")).unlink()
    (base / ("b" * 64 + ".json")).write_bytes(b"x" * (512_000 + 1))
    with pytest.raises(HTTPException) as oversized:
        listing("AI", limit=50, offset=0)
    assert oversized.value.status_code == 413


def test_agent_profile_count_size_and_corruption_bounds(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    path = tmp_path / "_settings" / "agent_profiles.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    profiles = _bridge_endpoint(module, "/agent-bridge/profiles", "GET")
    with pytest.raises(HTTPException) as corrupt:
        profiles()
    assert corrupt.value.status_code == 409

    path.write_bytes(b" " * (256 * 1024 + 1))
    with pytest.raises(HTTPException) as oversized:
        profiles()
    assert oversized.value.status_code == 413

    path.write_text(json.dumps([
        {"id": f"p{index}", "name": f"Profile {index}", "command": "agent", "args": []}
        for index in range(100)
    ]), encoding="utf-8")
    save = _bridge_endpoint(module, "/agent-bridge/profiles", "POST")
    with pytest.raises(HTTPException) as full:
        save(CustomAgentProfile(id="overflow", name="Overflow", command="agent"))
    assert full.value.status_code == 409


def test_agent_bridge_path_and_pagination_attacks_have_deterministic_statuses(
        monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    listing = _bridge_endpoint(module, "/agent-bridge/results", "GET")
    with pytest.raises(HTTPException) as folder_attack:
        listing("..", limit=50, offset=0)
    assert folder_attack.value.status_code == 400
    detail = _bridge_endpoint(module, "/agent-bridge/results/{result_id}", "GET")
    with pytest.raises(HTTPException) as result_attack:
        detail("AI", "../secret")
    assert result_attack.value.status_code == 422

    operation = module.app.openapi()["paths"][
        "/api/industries/{folder}/agent-bridge/results"]["get"]
    parameters = {item["name"]: item["schema"] for item in operation["parameters"]}
    assert parameters["limit"]["minimum"] == 1
    assert parameters["limit"]["maximum"] == 100
    assert parameters["offset"]["minimum"] == 0


def test_agent_verify_runs_submitted_assertions_and_returns_typed_gate_details(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    entity_id = module.service.repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US",
        "status": "accepted"})
    imported = _bridge_endpoint(module, "/agent-bridge/results", "POST")(
        "AI", AgentResultImport(task_id=task["id"], agent_id="agent",
        generation_call_id="generation-call-1",
        summary="ready for verification", assertions=[{
            "text": "NVIDIA is an AI company.", "type": "identity",
            "atomic": {"subject": "NVIDIA", "subject_id": entity_id,
                       "predicate": "identity",
                       "object": "AI company", "time": "2026-09-01",
                       "region": "US"},
            "citations": ["https://sec.gov/evidence"]}]))
    review = _bridge_endpoint(module, "/review", "POST")
    review("AI", imported["result_id"], schemas.AgentReviewRequest(
        assertion_id=imported["assertions"][0]["id"],
        decision="submitted_for_verification", note="verify"))
    content = "NVIDIA is an AI company."
    probe = EvidenceProbe(
        reachable=True, final_url="https://sec.gov/evidence", status_code=200,
        published_at="2026-08-31T12:00:00+00:00", content=content,
        content_hash=__import__("hashlib").sha256(content.encode()).hexdigest(),
        locator={"type": "text_offset", "start": 0, "end": len(content)},
        located_text=content, entity_ids=(entity_id,), publisher_kind="official_record")
    router = _router_with_verifier(module, AssertionVerifier(
        fetch=lambda _url: probe, semantic_evaluator=_api_evaluator()))
    verify = next(route.endpoint for route in router.routes
                  if route.path.endswith("/verify") and "POST" in route.methods)
    state = verify("AI", imported["result_id"])
    assert state["result_id"] == imported["result_id"]
    assert state["status"] == "verified", state
    assert state["decisions"][0]["disposition"] == "accepted"
    assert state["decisions"][0]["checks"]["semantic_support"]["status"] == "passed"
    assert service.repo.knowledge_stats("AI")["claims"] == 1


def test_agent_verify_without_semantic_evaluator_is_actionable_and_never_fetches_network(
        monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    task = _research_task(module.service)
    entity_id = module.service.repo.upsert_entity("AI", {
        "name": "NVIDIA", "type": "company", "country": "US",
        "status": "accepted"})
    content = "NVIDIA is an AI company."
    probe = EvidenceProbe(
        True, "https://sec.gov/evidence", 200,
        published_at="2026-08-31T12:00:00+00:00", content=content,
        content_hash=__import__("hashlib").sha256(content.encode()).hexdigest(),
        locator={"type": "text_offset", "start": 0, "end": len(content)},
        located_text=content, entity_ids=(entity_id,), publisher_kind="official_record")
    router = _router_with_verifier(
        module, AssertionVerifier(fetch=lambda _url: probe, semantic_evaluator=None))
    import_result = next(route.endpoint for route in router.routes
                         if route.path.endswith("/agent-bridge/results")
                         and "POST" in route.methods)
    imported = import_result("AI", AgentResultImport(
        task_id=task["id"], agent_id="agent", generation_call_id="generation-call-1",
        summary="needs configured verifier", assertions=[{
            "text": content, "type": "identity",
            "atomic": {"subject": "NVIDIA", "subject_id": entity_id,
                       "predicate": "identity", "object": "AI company",
                       "time": "2026", "region": "US"},
            "citations": ["https://sec.gov/evidence"],
        }]))
    review = next(route.endpoint for route in router.routes
                  if route.path.endswith("/review") and "POST" in route.methods)
    review("AI", imported["result_id"], schemas.AgentReviewRequest(
        assertion_id=imported["assertions"][0]["id"],
        decision="submitted_for_verification"))
    verify = next(route.endpoint for route in router.routes
                  if route.path.endswith("/verify") and "POST" in route.methods)

    state = verify("AI", imported["result_id"])

    assert state["status"] == "retryable"
    assert state["decisions"][0]["disposition"] == "candidate"
    reason = state["decisions"][0]["checks"]["semantic_support"]["reason"]
    assert "configure" in reason.casefold()
    assert module.service.repo._get_agent_assertion(
        "AI", imported["assertions"][0]["id"])["status"] == \
        "submitted_for_verification"
    assert module.service.repo.knowledge_stats("AI")["claims"] == 0


def test_agent_result_import_rejects_unknown_task_and_uncited_assertion(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    endpoint = _bridge_endpoint(module, "/agent-bridge/results", "POST")
    payload = AgentResultImport(task_id="missing", agent_id="agent", summary="result",
        assertions=[{"text": "claim", "citations": ["https://example.com"]}])
    with pytest.raises(HTTPException) as missing:
        endpoint("AI", payload)
    assert missing.value.status_code == 404
    with pytest.raises(Exception):
        AgentResultImport(task_id="missing", agent_id="agent", summary="result",
                          assertions=[{"text": "claim", "citations": []}])


def test_agent_result_import_rejects_oversized_payload(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    endpoint = _bridge_endpoint(module, "/agent-bridge/results", "POST")
    payload = AgentResultImport(task_id=task["id"], agent_id="agent", summary="result",
        assertions=[{"text": "x" * 20_000,
                     "citations": ["https://example.com/source"]} for _ in range(30)])
    with pytest.raises(HTTPException) as oversized:
        endpoint("AI", payload)
    assert oversized.value.status_code == 413
    assert not (tmp_path / "AI/one_time/agent_results").exists()


def test_agent_result_size_limit_uses_exact_enriched_pretty_printed_bytes(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    endpoint = _bridge_endpoint(module, "/agent-bridge/results", "POST")
    payload = AgentResultImport(task_id=task["id"], agent_id="agent", summary="result",
        assertions=[{"text": "x" * 5_040,
                     "citations": ["https://example.com/source"]}
                    for _ in range(100)])
    assert len(payload.model_dump_json().encode("utf-8")) < 512_000

    with pytest.raises(HTTPException) as oversized:
        endpoint("AI", payload)

    assert oversized.value.status_code == 413
    assert not (tmp_path / "AI/one_time/agent_results").exists()


def test_agent_result_import_removes_new_artifact_on_index_failure_and_retries_cleanly(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    endpoint = _bridge_endpoint(module, "/agent-bridge/results", "POST")
    payload = AgentResultImport(task_id=task["id"], agent_id="agent", summary="rollback",
        assertions=[{"text": "claim", "citations": ["https://example.com/source"]}])
    with service.repo.connection() as con:
        con.execute("""CREATE TRIGGER fail_agent_import_audit_api
            BEFORE INSERT ON audit_log
            WHEN NEW.action='import_agent_result'
            BEGIN SELECT RAISE(ABORT, 'forced API audit failure'); END""")

    with pytest.raises(sqlite3.IntegrityError, match="forced API audit failure"):
        endpoint("AI", payload)
    assert list((tmp_path / "AI" / "one_time" / "agent_results").glob("*/*.json")) == []

    with service.repo.connection() as con:
        con.execute("DROP TRIGGER fail_agent_import_audit_api")
    retried = endpoint("AI", payload)
    assert retried["duplicate"] is False
    with service.repo.connection() as con:
        assert con.execute("""SELECT COUNT(*) FROM audit_log
            WHERE action='import_agent_result'""").fetchone()[0] == 1


def test_agent_result_import_never_deletes_preexisting_duplicate_on_index_failure(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    endpoint = _bridge_endpoint(module, "/agent-bridge/results", "POST")
    payload = AgentResultImport(task_id=task["id"], agent_id="agent", summary="duplicate",
        assertions=[{"text": "claim", "citations": ["https://example.com/source"]}])
    first = endpoint("AI", payload)
    artifact = Path(first["original_file"])
    original = artifact.read_bytes()
    with service.repo.transaction() as con:
        con.execute("DELETE FROM agent_results WHERE id=?", (first["result_id"],))
        con.execute("DELETE FROM audit_log WHERE action='import_agent_result'")
        con.execute("""CREATE TRIGGER fail_duplicate_import_audit
            BEFORE INSERT ON audit_log
            WHEN NEW.action='import_agent_result'
            BEGIN SELECT RAISE(ABORT, 'forced duplicate audit failure'); END""")

    with pytest.raises(sqlite3.IntegrityError, match="forced duplicate audit failure"):
        endpoint("AI", payload)
    assert artifact.read_bytes() == original

    with service.repo.connection() as con:
        con.execute("DROP TRIGGER fail_duplicate_import_audit")
    retried = endpoint("AI", payload)
    assert retried["duplicate"] is True
    assert artifact.read_bytes() == original


def test_concurrent_same_result_failure_never_unlinks_successful_artifact(
        monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    task = _research_task(service)
    endpoint = _bridge_endpoint(module, "/agent-bridge/results", "POST")
    payload = AgentResultImport(task_id=task["id"], agent_id="agent", summary="race",
        assertions=[{"text": "claim", "citations": ["https://example.com/source"]}])
    original_atomic = agent_bridge_module._atomic_json
    writes = threading.Barrier(2)

    def synchronized_atomic(path, value):
        try:
            writes.wait(timeout=0.2)
        except threading.BrokenBarrierError:
            pass
        return original_atomic(path, value)

    original_index = module.service.repo.index_agent_result
    call_lock = threading.Lock()
    first_committed = threading.Event()
    calls = 0

    def one_success_one_failure(*args, **kwargs):
        nonlocal calls
        with call_lock:
            calls += 1
            ordinal = calls
        if ordinal == 1:
            result = original_index(*args, **kwargs)
            first_committed.set()
            return result
        assert first_committed.wait(timeout=2)
        raise sqlite3.OperationalError("injected concurrent index failure")

    monkeypatch.setattr(agent_bridge_module, "_atomic_json", synchronized_atomic)
    monkeypatch.setattr(module.service.repo, "index_agent_result", one_success_one_failure)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(endpoint, "AI", payload) for _ in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except sqlite3.OperationalError:
                outcomes.append(None)

    successful = [item for item in outcomes if item is not None]
    assert len(successful) == 1
    artifact = Path(successful[0]["original_file"])
    assert artifact.is_file()
    assert service.repo.list_agent_results("AI", limit=10, offset=0)["total"] == 1


def test_agent_profile_concurrent_saves_retain_updates_and_enforce_cap(
        monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    save = _bridge_endpoint(module, "/agent-bridge/profiles", "POST")
    profiles = _bridge_endpoint(module, "/agent-bridge/profiles", "GET")
    original_read = agent_bridge_module._read_profiles

    barrier = threading.Barrier(2)
    def synchronized_read(path):
        rows = original_read(path)
        try:
            barrier.wait(timeout=0.2)
        except threading.BrokenBarrierError:
            pass
        return rows

    monkeypatch.setattr(agent_bridge_module, "_read_profiles", synchronized_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(save, [
            CustomAgentProfile(id="left", name="Left", command="agent"),
            CustomAgentProfile(id="right", name="Right", command="agent"),
        ]))
    assert {item["id"] for item in profiles()["items"]} == {"left", "right"}

    profile_path = tmp_path / "_settings" / "agent_profiles.json"
    profile_path.write_text(json.dumps([
        {"id": f"p{index}", "name": f"Profile {index}", "command": "agent", "args": []}
        for index in range(99)
    ]), encoding="utf-8")
    barrier = threading.Barrier(2)
    def attempt(profile):
        try:
            save(profile)
            return 201
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attempt, [
            CustomAgentProfile(id="p99", name="P99", command="agent"),
            CustomAgentProfile(id="p100", name="P100", command="agent"),
        ]))
    assert sorted(statuses) == [201, 409]
    assert profiles()["total"] == 100


def test_bounded_json_reader_reads_at_most_limit_plus_one(monkeypatch, tmp_path):
    requested = []
    class GrowingFile(io.BytesIO):
        def read(self, size=-1):
            requested.append(size)
            return super().read(size)

    stream = GrowingFile(b"x" * 12)
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: stream)
    with pytest.raises(HTTPException) as oversized:
        agent_bridge_module._read_json_bounded(Path("result.json"), 10,
                                                "result exceeds limit")
    assert oversized.value.status_code == 413
    assert requested == [11]


def test_agent_result_response_statuses_are_finite_literals():
    expected = ["draft_review_required", "rejected", "opinion",
                "submitted_for_verification", "candidate", "disputed", "accepted"]
    assertion_schema = schemas.AgentAssertionState.model_json_schema()
    result_schema = schemas.AgentResultState.model_json_schema()
    assert assertion_schema["properties"]["status"]["enum"] == expected
    assert result_schema["properties"]["status"]["enum"] == expected


def test_custom_agent_profile_rejects_paths_and_shell_syntax(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    endpoint = _bridge_endpoint(module, "/agent-bridge/profiles", "POST")
    with pytest.raises(HTTPException) as path_error:
        endpoint(CustomAgentProfile(id="bad", name="Bad", command="/bin/sh", args=[]))
    assert path_error.value.status_code == 422
    with pytest.raises(HTTPException):
        endpoint(CustomAgentProfile(id="bad", name="Bad", command="agent",
                                    args=["run;touch"]))


def test_custom_agent_profile_persists_only_public_argv(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    save = _bridge_endpoint(module, "/agent-bridge/profiles", "POST")
    list_profiles = _bridge_endpoint(module, "/agent-bridge/profiles", "GET")
    saved = save(CustomAgentProfile(id="local", name="Local Agent", command="agent",
                                    args=["run", "{task_file}", "{result_file}"]))
    assert saved["command"] == "agent"
    assert list_profiles()["items"] == [saved]
    assert "key" not in str(saved).lower()
    delete = _bridge_endpoint(module, "/agent-bridge/profiles/{profile_id}", "DELETE")
    assert delete("local") == {"removed": True}
    assert list_profiles()["items"] == []


def test_agent_capability_discovery_and_diagnosis_routes_are_typed(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    expected = {
        ("/api/agent-bridge/capabilities", "GET"): "AgentCapabilityPage",
        ("/api/agent-bridge/discover", "POST"): "AgentDiscoveryPage",
        ("/api/agent-bridge/profiles/{profile_id}/diagnose", "POST"):
            "AgentDiagnosticState",
    }
    operations = module.app.openapi()["paths"]
    for (path, method), schema_name in expected.items():
        schema = operations[path][method.lower()]["responses"]["200"]["content"][
            "application/json"]["schema"]
        assert schema == {"$ref": f"#/components/schemas/{schema_name}"}


def test_daily_portable_export_is_offline_and_typed(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    service.import_daily("AI", "news", "2026-09-02", [{
        "title": "模型正式发布", "url": "https://official.example/release",
        "source": "官方公告", "display_source": "官方公告",
        "abstract": "官方披露了模型能力、部署边界与发布日期，内容可沿证据链接复核。",
        "published_at": "2026-09-02T08:00:00+08:00",
    }])
    export = _router_endpoint(module.content_router, "/portable/daily", "POST")
    result = export("AI")
    document = Path(result["path"]).read_text(encoding="utf-8")
    assert result["status"] in {"draft_review_required", "partial"}
    assert "fetch(" not in document and "<script src=" not in document
    assert "localStorage" in document and "window.print" in document
    schema = module.app.openapi()["paths"]["/api/industries/{folder}/portable/daily"][
        "post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/PortableExportState"}


def test_agent_diagnosis_api_uses_saved_public_profile_and_never_returns_secret(
        monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    save = _bridge_endpoint(module, "/agent-bridge/profiles", "POST")
    save(CustomAgentProfile(id="codex-local", name="Codex", command="codex"))
    seen = []

    def diagnose(profile, *, timeout_seconds):
        seen.append((profile, timeout_seconds))
        return {
            "id": "codex", "connection": "native_cli",
            "execution_level": "direct", "installed": True,
            "version_verified": True, "authenticated": True, "ready": True,
            "status": "ready", "failure_code": None,
            "executable": "/tools/codex", "version": "codex-cli 1.2.3",
            "detail": "Authenticated native CLI is ready",
        }

    monkeypatch.setattr(agent_bridge_module, "diagnose_agent", diagnose)
    endpoint = _bridge_endpoint(
        module, "/agent-bridge/profiles/{profile_id}/diagnose", "POST")
    result = endpoint("codex-local", timeout_seconds=3)
    assert seen == [({"id": "codex-local", "name": "Codex", "command": "codex",
                      "args": [], "executable_path": None,
                      "capability_id": None}, 3)]
    assert result["ready"] is True
    assert "secret" not in str(result).casefold()


def test_setup_does_not_offer_catalog_only_api_as_direct_provider(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    payload = module.setup()
    provider_ids = {item["id"] for item in payload["api_providers"]}
    assert "anthropic" not in provider_ids
    assert "compatible_api" in provider_ids
    capabilities = _bridge_endpoint(module, "/agent-bridge/capabilities", "GET")()
    anthropic = next(item for item in capabilities["items"]
                     if item["id"] == "anthropic")
    assert anthropic["execution_level"] == "import_only"


def test_agent_discovery_request_bounds_each_user_selected_path():
    with pytest.raises(ValidationError):
        schemas.AgentDiscoveryRequest(selected_executables=["x" * 4097])


def test_agent_diagnostic_busy_state_is_typed():
    state = schemas.AgentDiagnosticState.model_validate({
        "id": "codex", "connection": "native_cli", "execution_level": "direct",
        "installed": False, "version_verified": False, "authenticated": None,
        "ready": False, "status": "busy", "failure_code": "diagnosis_busy",
        "executable": "", "version": "", "detail": "retry later",
    })
    assert state.status == "busy"


def test_setup_derives_direct_adapters_and_readiness_from_manifest(
        monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    from src.services import agent_registry, capability_manifest, provider_readiness

    synthetic_cli = capability_manifest.AgentCapability(
        "future_cli", "Future CLI", "agent", "international", "native_cli", "direct",
        "https://example.test/cli", "synthetic adapter", ("future-cli",),
        version_pattern=r"Future CLI 1\\.0", auth_args=("auth", "status"),
        auth="subscription",
    )
    synthetic_api = capability_manifest.AgentCapability(
        "future_api", "Future API", "api", "international", "api", "direct",
        "https://example.test/api", "synthetic adapter", auth="bearer",
        key_env="FUTURE_API_KEY", default_model="future-default",
        default_api_base="https://api.example.test/v1",
    )
    manifest = (*capability_manifest.CAPABILITY_MANIFEST, synthetic_cli, synthetic_api)
    monkeypatch.setattr(capability_manifest, "CAPABILITY_MANIFEST", manifest)
    monkeypatch.setattr(agent_registry, "discover_agents", lambda **_: [{
        **synthetic_cli.public(), "installed": True, "authenticated": None,
        "ready": False, "executable": "/tools/future-cli", "detail": "detected",
    }])
    calls = []

    def readiness(name, _root):
        calls.append(name)
        ready = name in {"future_cli", "future_api"}
        return {"provider": name, "installed": True, "authenticated": ready,
                "ready": ready, "detail": "manifest diagnostic"}

    monkeypatch.setattr(provider_readiness, "provider_readiness", readiness)
    payload = module.setup()
    direct = {item.id for item in manifest if item.execution_level == "direct"
              and item.connection in {"native_cli", "api"}}
    assert set(calls) == direct
    assert next(item for item in payload["agents"]
                if item["id"] == "future_cli")["ready"] is True
    api = next(item for item in payload["api_providers"]
               if item["id"] == "future_api")
    assert api["ready"] is True
    assert api["configured"] is True
    assert api["default_model"] == "future-default"
    assert api["auth_type"] == "bearer"


def test_setup_exposes_selected_generic_auth_type_without_secret(
        monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "compatible_api")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "custom-model")
    monkeypatch.setenv("INTDOG_LLM_API_BASE", "https://models.example/v1")
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "must-not-leak")
    monkeypatch.setenv("INTDOG_LLM_AUTH_TYPE", "api_key_header")
    module, _ = load_api(monkeypatch, tmp_path)
    from src.services import agent_registry, provider_readiness
    monkeypatch.setattr(agent_registry, "discover_agents", lambda **_: [])
    monkeypatch.setattr(provider_readiness, "provider_readiness", lambda name, _root: {
        "provider": name, "installed": True,
        "authenticated": name == "compatible_api",
        "ready": name == "compatible_api", "detail": "checked",
    })
    payload = module.setup()
    generic = next(item for item in payload["api_providers"]
                   if item["id"] == "compatible_api")
    assert generic["ready"] is True
    assert generic["auth_type"] == "api_key_header"
    assert generic["auth_configurable"] is True
    assert "must-not-leak" not in str(payload)


def test_unready_direct_provider_is_rejected_before_job_queue(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    generate = next(route.endpoint for route in module.operations_router.routes
                    if route.path.endswith('/generate'))
    before = len(module.jobs.store.list())
    monkeypatch.setattr('src.services.provider_readiness.provider_readiness',
                        lambda *_args: {'ready': False, 'detail': '未登录'})
    with pytest.raises(HTTPException) as caught:
        generate('AI', GenerateRequest(action='report', kind='industry_overview',
                                       provider='claude', execution_mode='direct'))
    assert caught.value.status_code == 409
    assert len(module.jobs.store.list()) == before


def test_generation_requires_explicit_execution_mode_and_direct_provider():
    with pytest.raises(ValidationError):
        GenerateRequest(action="report", kind="trend_5y")
    with pytest.raises(ValidationError):
        GenerateRequest(action="report", kind="trend_5y", execution_mode="direct")
    taskpack = GenerateRequest(action="report", kind="trend_5y",
                               execution_mode="taskpack")
    assert taskpack.provider == ""
    direct = GenerateRequest(action="report", kind="trend_5y",
                             execution_mode="direct", provider="claude")
    assert direct.provider == "claude"


def test_daily_default_sort_and_category_aware_source_names(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    for category, item in (
        ("github", {"title": "Zulu", "url": "https://github.com/openai/repo"}),
        ("papers", {"title": "Alpha", "url": "https://paper.example/a",
                    "authors": ["Ada", "Lin"]}),
    ):
        service.import_daily("AI", category, "2026-08-31", [item])

    payload = module.daily("AI", sort="title", query="")
    assert [item["title"] for item in payload["items"]] == ["Alpha", "Zulu"]
    assert payload["items"][0]["display_source"] == "Ada, Lin"
    assert payload["items"][1]["display_source"] == "openai"


def test_artifact_route_rejects_paths_outside_data_root(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as caught:
        module.artifact("/etc/passwd")
    assert caught.value.status_code == 403


def test_static_fallback_never_masks_unknown_api_route(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as caught:
        module.web_app("api/industries//overview")
    assert caught.value.status_code == 404


def test_daily_pagination_is_bounded_and_cursor_continues(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    service.import_daily("AI", "news", "2026-08-31", [
        {
            "title": f"Item {index:03d}",
            "url": f"https://news.example/{index}",
            "source": "Example News",
        }
        for index in range(125)
    ])

    first = module.daily("AI", sort="title", query="", limit=50)
    second = module.daily(
        "AI", sort="title", query="", limit=50,
        cursor=first["next_cursor"])

    assert first["total"] == 125
    assert len(first["items"]) == 50
    assert first["selection_scope"] == "current_page"
    assert first["items"][-1]["title"] < second["items"][0]["title"]
    assert second["next_cursor"]


def test_daily_rejects_invalid_cursor(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    service.import_daily("AI", "news", "2026-08-31", [{
        "title": "Cursor fixture",
        "url": "https://news.example/cursor",
    }])
    with pytest.raises(HTTPException) as caught:
        module.daily("AI", cursor="not-a-cursor")
    assert caught.value.status_code == 400


def test_source_sort_remains_global_across_pages(monkeypatch, tmp_path):
    module, service = load_api(monkeypatch, tmp_path)
    service.import_daily("AI", "github", "2026-08-31", [
        {"title": f"Repository {index:03d}",
         "url": f"https://github.com/{owner}/repo-{index}", "owner": owner}
        for index, owner in enumerate(
            ["zeta"] * 60 + ["alpha"] * 60 + ["middle"] * 5)
    ])
    first = module.daily("AI", sort="source", limit=50)
    second = module.daily(
        "AI", sort="source", limit=50, cursor=first["next_cursor"])
    combined = [item["display_source"] for item in first["items"] + second["items"]]
    assert combined == sorted(combined, key=str.casefold)


def test_history_status_exposes_all_horizons_without_creating_manifest(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    payload = module.history("AI")

    assert [item["horizon"] for item in payload["items"]] == [
        "weekly", "monthly", "quarterly", "semiannual", "biennial", "fiveyear"]
    assert payload["items"][-1]["target"] == 8000
    assert all(item["status"] == "not_started" for item in payload["items"])
    assert not (tmp_path / "AI/one_time/research/history").exists()
