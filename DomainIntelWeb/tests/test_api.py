from __future__ import annotations

import importlib
import tomllib

import pytest
from fastapi import HTTPException
from DomainIntelWeb.api.schemas import (AgentResultImport, AgentResultReview,
                                        CustomAgentProfile, GenerateRequest)

from intdog_core import IntDogService


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


def test_setup_contract_is_redaction_safe_and_exposes_bidirectional_agent_bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "must-not-leak")
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "deepseek-chat")
    module, _ = load_api(monkeypatch, tmp_path)
    with monkeypatch.context() as scoped:
        scoped.setattr("src.services.agent_registry.discover_agents", lambda **_: [])
        scoped.setattr("src.services.provider_readiness.provider_readiness",
                       lambda name, _root: {"provider": name, "ready": False})
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


def _research_task(service):
    agenda_id = service.repo.upsert_research_agenda("AI", [{
        "dimension": "chain", "target_key": "models", "title": "模型证据",
        "priority": 80, "rationale": "补齐模型证据", "queries": ["model evidence"],
        "acceptance": {"citations": 2},
    }])[0]
    return service.create_research_task("AI", agenda_id, 5)


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
    reviewed = review("AI", first["result_id"],
                      AgentResultReview(decision="reviewed", note="citations checked"))
    assert reviewed["status"] == "reviewed"
    third = endpoint("AI", payload)
    assert third["duplicate"] and third["status"] == "reviewed"
    listing = _bridge_endpoint(module, "/agent-bridge/results", "GET")
    page = listing("AI", limit=1, offset=0)
    assert page["total"] == 1 and page["items"][0]["status"] == "reviewed"
    assert service.repo.knowledge_stats("AI") == before
    audits = service.repo.list_audits(limit=20)
    assert sum(row["action"] == "import_agent_result" for row in audits) == 1
    assert sum(row["action"] == "review_agent_result" for row in audits) == 1


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


def test_unready_direct_provider_is_rejected_before_job_queue(monkeypatch, tmp_path):
    module, _ = load_api(monkeypatch, tmp_path)
    generate = next(route.endpoint for route in module.operations_router.routes
                    if route.path.endswith('/generate'))
    before = len(module.jobs.store.list())
    monkeypatch.setattr('src.services.provider_readiness.provider_readiness',
                        lambda *_args: {'ready': False, 'detail': '未登录'})
    with pytest.raises(HTTPException) as caught:
        generate('AI', GenerateRequest(action='report', kind='industry_overview',
                                       provider='claude'))
    assert caught.value.status_code == 409
    assert len(module.jobs.store.list()) == before


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
    assert payload["items"][-1]["target"] == 7200
    assert all(item["status"] == "not_started" for item in payload["items"])
    assert not (tmp_path / "AI/one_time/research/history").exists()
