from __future__ import annotations

from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1]
FEATURES = {
    "overview": "OverviewPage.tsx",
    "daily": "DailyPage.tsx",
    "products": "ProductsPage.tsx",
    "sources": "SourcesPage.tsx",
    "research": "ResearchPage.tsx",
    "jobs": "JobsPage.tsx",
    "system": "SystemPage.tsx",
}


def test_all_destinations_are_lazy_feature_slices():
    app = (WEB_ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
    for filename in FEATURES.values():
        stem = filename.removesuffix(".tsx")
        assert f"lazy(() => import('./features/{stem}'))" in app
        source = (WEB_ROOT / "src" / "features" / filename).read_text(encoding="utf-8")
        assert "export default function" in source
    assert "<Suspense" in app


def test_data_destinations_own_error_and_loading_or_empty_states():
    for key in ("overview", "daily", "products", "sources", "research", "jobs"):
        source = (WEB_ROOT / "src" / "features" / FEATURES[key]).read_text(
            encoding="utf-8")
        assert "error" in source, key
        assert "<Empty" in source, key
    shared = (WEB_ROOT / "src" / "features" / "shared.tsx").read_text(
        encoding="utf-8")
    assert "function Loading" in shared
    assert "function Empty" in shared


def test_api_boundary_runtime_validates_feature_payloads():
    source = (WEB_ROOT / "src" / "api.ts").read_text(encoding="utf-8")
    for suffix in ("/overview", "/daily", "/products", "/sources", "/research", "/history"):
        assert f"route.endsWith('{suffix}')" in source
    assert "API contract mismatch" in source
    assert "ApiPath" in source and "./generated/openapi" in source
    assert "export type HealthPayload = HealthState" in source


def test_round_two_workflows_are_reachable_and_forms_have_labels():
    daily = (WEB_ROOT / "src/features/DailyPage.tsx").read_text(encoding="utf-8")
    research = (WEB_ROOT / "src/features/ResearchPage.tsx").read_text(encoding="utf-8")
    system = (WEB_ROOT / "src/features/SystemPage.tsx").read_text(encoding="utf-8")
    sources = (WEB_ROOT / "src/features/SourcesPage.tsx").read_text(encoding="utf-8")
    assert "事件与证据" in daily and "/stories/" in daily
    assert "开放世界覆盖地图" in research and "coverage/plan" in research
    for action in ("bootstrap", "history", "report", "deep_report", "impact", "lab"):
        assert f'value="{action}"' in research
    assert "自动化计划" in system and "/automation/" in system
    assert "回收站" in system and "/trash/" in system
    assert "不会自动发送邮件" in research
    assert "{label:'影响分析',rows:data.impacts}" in (
        WEB_ROOT / "src/features/ProductsPage.tsx").read_text(encoding="utf-8")
    assert "<label" in daily and "<label" in research
    assert "<label" in system and "<label" in sources


def test_zoom_responsive_contract_has_no_page_wide_dense_table_requirement():
    css = (WEB_ROOT / "src/styles.css").read_text(encoding="utf-8")
    assert "@media (max-width:520px)" in css
    assert ".daily-table { overflow-x:auto; }" in css
    assert ".story-layout { grid-template-columns:1fr; }" in css
    assert ".schedule-grid,.studio-form,.coverage-stats,.history-grid { grid-template-columns:1fr; }" in css
