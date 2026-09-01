from __future__ import annotations

from types import SimpleNamespace

from intdog_core import IntDogService
from src.research_bootstrap import _persist_source_coverage
from src.source_discovery import build_discovery_task, merge_sources
from src.coverage_execution import Probe, execute_coverage


def test_discovery_contract_is_gap_led_not_quota_led():
    prompt = build_discovery_task("人工智能", "AI")["prompt"]
    assert "不要预设总量或 Top 10" in prompt
    assert "coverage_ledger" in prompt and "query_ledger" in prompt
    assert "总量目标 45" not in prompt
    merged = merge_sources({"official": []}, {
        "coverage_ledger": [{"dimensions": {"region": "china"}}],
        "query_ledger": [{"query": "AI 官方"}],
        "stopping_reason": "边际新增低",
    })
    assert merged["stopping_reason"] == "边际新增低"


def test_model_discovery_ledger_never_receives_verified_yield(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    store = SimpleNamespace(service=service, folder="AI")
    metrics = _persist_source_coverage(store, {
        "coverage_ledger": [{
            "dimensions": {"region": "china", "chain_stage": "算力"},
            "priority": 90, "status": "candidate",
        }],
        "query_ledger": [{
            "dimensions": {"region": "china", "chain_stage": "算力"},
            "query": "中国 AI 算力 官方",
            "discovered_urls": ["https://example.cn/lead"],
        }],
    })
    assert metrics == {"cells": 1, "planned_queries": 1,
                       "model_yield_credited": 0}
    cell = service.repo.list_coverage("AI")[0]
    attempt = service.repo.coverage_attempts(cell["id"])[0]
    assert cell["source_yield"] == 0 and cell["entity_yield"] == 0
    assert attempt["status"] == "planned"
    assert attempt["evidence"][0]["validation_status"] == "unverified_model_lead"


def test_coverage_executor_persists_only_candidates_and_query_results(tmp_path):
    service = IntDogService(tmp_path)
    service.create_industry("AI", "人工智能")
    cell_id = service.repo.upsert_coverage_cell("AI", {
        "region": "china", "subdomain": "算力", "chain_stage": "AI 芯片",
        "entity_type": "company", "source_type": "official",
        "event_type": "policy", "time_horizon": "12m",
    }, priority=90)
    payload = {"candidates": [
        {"cell_id": cell_id, "name": "权威来源", "url": "https://valid.example/a",
         "category": "official", "publisher_country": "中国",
         "entity": {"name": "示例芯片公司", "type": "company",
                    "country": "中国", "chain": "AI 芯片"}},
        {"cell_id": cell_id, "name": "失败来源", "url": "https://bad.example/a",
         "category": "news"},
    ], "stopping_reason": "测试预算已用完"}
    client = SimpleNamespace(complete=lambda _prompt: SimpleNamespace(
        text=__import__("json").dumps(payload, ensure_ascii=False)))
    store = SimpleNamespace(service=service, folder="AI", root=tmp_path / "AI")

    result = execute_coverage(
        {}, store, provider_client=client, probe=lambda url: (
            Probe(True, url, 200) if "valid" in url else
            Probe(False, url, 503, "HTTP 503")))

    assert result["source_yield"] == 0 and result["entity_yield"] == 0
    assert result["candidate_yield"] == 2
    assert result["rejected"] == 0
    assert service.repo.list_sources("AI") == []
    assert service.repo.list_compat_entities("AI") == []
    candidates = service.repo.list_source_candidates(result["campaign_id"])
    assert len(candidates) == 2
    assert {item["status"] for item in candidates} == {"candidate"}
    attempt = service.repo.coverage_attempts(cell_id)[0]
    assert attempt["status"] == "completed"
    assert attempt["source_yield"] == 0 and attempt["entity_yield"] == 0
    assert {item["status"] for item in attempt["evidence"]} == {
        "candidate_reachable", "candidate_unreachable"}
