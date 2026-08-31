from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException

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
