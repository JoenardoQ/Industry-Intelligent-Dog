from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src import main as cli_main
from src.industry_store import IndustryStore
from src.knowledge_model import KnowledgeModel
from src.research_bootstrap import check_source_accessibility, run_bootstrap
from src.source_discovery import seed_sources


def _sources():
    payload = seed_sources("人工智能", "Artificial Intelligence", {"id": "ai"})
    payload["official"].append({"name": "Additional authority",
                                "url": "https://authority-extra.example/ai",
                                "tier": "primary", "origin": "international"})
    for values in payload.values():
        if isinstance(values, list):
            for item in values:
                item["access_check"] = {"reachable": True, "status_code": 200}
    return payload


def _chains():
    names = ["研究", "基础设施", "模型", "平台", "应用"]
    chains = [{"name": name, "order": index, "description": name,
               "inputs": [], "outputs": [], "upstream": names[index - 2:index - 1],
               "downstream": names[index:index + 1],
               "references": [{"title": f"{name} evidence",
                                "url": f"https://evidence.example/{index}"}]}
              for index, name in enumerate(names, 1)]
    edges = [{"source": names[index], "target": names[index + 1],
              "relation": "supplies", "effect": "positive",
              "references": [{"title": "edge evidence",
                               "url": f"https://evidence.example/edge-{index}"}]}
             for index in range(len(names) - 1)]
    return {"chains": chains, "edges": edges}


def _entities():
    rows = []
    for stage in ["研究", "基础设施", "模型", "平台", "应用"]:
        rows.extend([
            {"name": f"{stage}中国企业", "type": "company", "chain": stage,
             "country": "中国", "is_china": True,
             "references": [{"title": "CN", "url": "https://cn.example/e"}]},
            {"name": f"{stage}海外企业", "type": "company", "chain": stage,
             "country": "美国", "is_china": False,
             "references": [{"title": "Global", "url": "https://global.example/e"}]},
            {"name": f"{stage}研究组", "type": "research_group", "chain": stage,
             "country": "中国", "is_china": True,
             "references": [{"title": "Lab", "url": "https://lab.example/e"}]},
        ])
    return {"entities": rows}


class FakeProvider:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.prompts = []

    def probe(self, required_web_search=False):
        return {"ready": True, "web_search": required_web_search}

    def complete(self, prompt):
        self.prompts.append(prompt)
        value = self.payloads.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=json.dumps(value, ensure_ascii=False))


def _store(tmp_path):
    return IndustryStore(tmp_path, "AI", "人工智能")


def _trusted_source_checker(payload):
    for values in payload.values():
        if isinstance(values, list):
            for item in values:
                item["access_check"] = {"reachable": True, "status_code": 200}
    return payload


def test_cli_progress_streams_are_line_buffered_and_written_through():
    class Stream:
        def __init__(self):
            self.options = {}

        def reconfigure(self, **options):
            self.options = options

    configure = getattr(cli_main, "_configure_stdio", None)
    assert callable(configure), "CLI must expose deterministic stdio configuration"
    stdout, stderr = Stream(), Stream()

    configure(stdout, stderr)

    for stream in (stdout, stderr):
        assert stream.options["line_buffering"] is True
        assert stream.options["write_through"] is True


def test_bw04_direct_bootstrap_runs_three_gated_stages_once(monkeypatch, tmp_path):
    provider = FakeProvider(_sources(), _chains(), _entities())
    monkeypatch.setattr("src.research_bootstrap.create_provider", lambda *_: provider)

    status = run_bootstrap({}, _store(tmp_path), "Artificial Intelligence",
                           provider="openai", access_checker=_trusted_source_checker)

    assert len(provider.prompts) == 3
    assert status["state"] == "ready_for_review"
    campaign = _store(tmp_path).service.repo.list_source_campaigns("AI")[0]
    assert campaign["status"] == "paused"
    assert campaign["stopping_reason"] == "awaiting_manual_review"
    assert status["coverage"]["cells"] > 0
    assert status["coverage"]["candidate_total"] > 0
    assert status["coverage"]["reviewed_evidence_total"] == 0
    assert status["coverage"]["next_actions"] == ["sources", "knowledge", "research"]
    assert [status["stages"][key]["state"]
            for key in ("sources", "value_chain", "entities")] == [
                "passed", "passed", "passed"]
    tree = KnowledgeModel(tmp_path / "AI" / "one_time" / "knowledge").tree()
    assert len(tree["chains"]) == 5
    assert sum(len(row["entities"]) for row in tree["chains"]) == 15


def test_bw05_source_gate_stops_chain_and_entity_calls(monkeypatch, tmp_path):
    weak = {"official": [{"name": "Only", "url": "https://only.example"}]}
    provider = FakeProvider(weak, _chains(), _entities())
    monkeypatch.setattr("src.research_bootstrap.create_provider", lambda *_: provider)

    status = run_bootstrap({}, _store(tmp_path), provider="openai",
                           access_checker=_trusted_source_checker)

    assert len(provider.prompts) == 1
    assert status["state"] == "partial"
    assert status["stages"]["sources"]["state"] == "partial"
    assert status["stages"]["value_chain"]["state"] == "skipped"


def test_bw05_chain_gate_stops_entity_call(monkeypatch, tmp_path):
    provider = FakeProvider(_sources(), {"chains": [{"name": "thin"}], "edges": []},
                            _entities())
    monkeypatch.setattr("src.research_bootstrap.create_provider", lambda *_: provider)

    status = run_bootstrap({}, _store(tmp_path), provider="openai",
                           access_checker=_trusted_source_checker)

    assert len(provider.prompts) == 2
    assert status["state"] == "partial"
    assert status["stages"]["value_chain"]["state"] == "partial"
    assert status["stages"]["entities"]["state"] == "skipped"


def test_bw06_provider_failure_before_source_response_creates_no_campaign(
        monkeypatch, tmp_path):
    provider = FakeProvider(RuntimeError("provider unavailable"))
    monkeypatch.setattr("src.research_bootstrap.create_provider", lambda *_: provider)
    store = _store(tmp_path)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        run_bootstrap({}, store, provider="openai",
                      access_checker=_trusted_source_checker)

    assert store.service.repo.list_source_campaigns("AI") == []
    raw = tmp_path / "AI" / "one_time" / "research" / "bootstrap"
    assert not list(raw.glob("*_sources_candidate.json"))


def test_bw07_retry_reuses_passed_source_checkpoint_and_campaign(
        monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_TASK_RUN_ID", "task-original")
    first = FakeProvider(_sources(), {"chains": [{"name": "thin"}], "edges": []})
    monkeypatch.setattr("src.research_bootstrap.create_provider", lambda *_: first)
    store = _store(tmp_path)
    assert run_bootstrap({}, store, provider="openai",
                         access_checker=_trusted_source_checker)["state"] == "partial"
    assert len(store.service.repo.list_source_campaigns("AI")) == 1

    monkeypatch.setenv("INTDOG_TASK_RUN_ID", "task-retry")
    retried = FakeProvider(_chains(), _entities())
    monkeypatch.setattr("src.research_bootstrap.create_provider", lambda *_: retried)
    status = run_bootstrap({}, store, provider="openai",
                           resume_task_id="task-original",
                           access_checker=_trusted_source_checker)

    assert len(retried.prompts) == 2
    assert status["state"] == "ready_for_review"
    assert status["resume_decision"] == "reused_valid_checkpoint"
    assert len(store.service.repo.list_source_campaigns("AI")) == 1


def test_provider_supplied_access_claim_cannot_bypass_live_check(monkeypatch, tmp_path):
    supplied = _sources()
    checked = {"called": False}

    def checker(payload):
        checked["called"] = True
        for values in payload.values():
            if isinstance(values, list):
                for item in values:
                    item["access_check"] = {"reachable": False, "status_code": 503}
        return payload

    provider = FakeProvider(supplied, _chains(), _entities())
    monkeypatch.setattr("src.research_bootstrap.create_provider", lambda *_: provider)

    status = run_bootstrap({}, _store(tmp_path), provider="openai",
                           access_checker=checker)

    assert checked["called"] is True
    assert status["state"] == "partial"
    assert status["stages"]["value_chain"]["state"] == "skipped"


def test_live_source_check_rejects_loopback_without_requesting_it():
    payload = {"official": [{"name": "private target",
                              "url": "http://127.0.0.1/latest/meta-data"}]}

    checked = check_source_accessibility(payload, workers=1)

    result = checked["official"][0]["access_check"]
    assert result["reachable"] is False
    assert result["error"] == "blocked_non_public_address"
