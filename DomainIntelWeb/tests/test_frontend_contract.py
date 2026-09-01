from __future__ import annotations

from pathlib import Path
import re

from DomainIntelWeb.scripts.generate_contract import ts_type


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
    source = (WEB_ROOT / "src" / "api/runtime.ts").read_text(encoding="utf-8")
    public_api = (WEB_ROOT / "src" / "api.ts").read_text(encoding="utf-8")
    client = (WEB_ROOT / "src" / "api/client.ts").read_text(encoding="utf-8")
    for suffix in ("/overview", "/daily", "/products", "/sources", "/research", "/history"):
        assert f"route.endsWith('{suffix}')" in source
    assert "API contract mismatch" in source
    assert "ApiPath" in client and "../generated/openapi" in client
    assert "export type HealthPayload = HealthState" in public_api


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


def test_agent_review_typography_has_no_eleven_pixel_text():
    css = (WEB_ROOT / "src/styles.css").read_text(encoding="utf-8")
    review_css = css[css.index(".agent-review-panel"):css.index("@media(max-width:1100px)")]
    assert "font-size:11px" not in review_css
    assert ".agent-result-summary dd" in review_css and "font-size:14px" in review_css
    assert ".verification-gate>header strong{font-size:14px}" in review_css


def test_generated_contract_preserves_literal_and_discriminated_union_types():
    assert ts_type({"const": "submitted_for_verification", "type": "string"}) == (
        '"submitted_for_verification"')
    assert ts_type({"enum": ["rejected", "opinion"], "type": "string"}) == (
        '"rejected" | "opinion"')
    assert ts_type({"oneOf": [
        {"$ref": "#/components/schemas/TextOffsetLocator"},
        {"$ref": "#/components/schemas/PdfPageLocator"},
    ]}) == "TextOffsetLocator | PdfPageLocator"


def test_generated_openapi_is_the_only_frontend_response_contract():
    api_source = (WEB_ROOT / "src/api.ts").read_text(encoding="utf-8")
    client = (WEB_ROOT / "src/api/client.ts").read_text(encoding="utf-8")
    runtime = (WEB_ROOT / "src/api/runtime.ts").read_text(encoding="utf-8")
    generated = (WEB_ROOT / "src/generated/openapi.ts").read_text(encoding="utf-8")

    response_names = (
        "Industry", "DailyItem", "DailyPage", "ChainNode", "Entity",
        "KnowledgeEntityPage", "KnowledgeEntityDetail", "OverviewPayload",
        "ProductItem", "ProductsPayload", "SourceItem", "SourcesPayload",
        "ResearchPayload", "Job", "StorySummary", "StoryDocument",
        "StoryDetail", "CoveragePayload", "HistoryCoveragePayload", "Schedule",
        "AutomationPayload", "BackgroundPayload", "TrashItem",
    )
    for name in response_names:
        assert not re.search(rf"export type {name}\s*=\s*\{{", api_source), name
    assert "export { api, apiText } from './api/client'" in api_source
    assert "TPath extends ClientPath" in client
    assert "AbortSignal" in client and "X-IntDog-Session" in client
    assert "validateResponse" in runtime
    assert "export type ApiPath" in generated


def test_artifact_markdown_uses_the_session_client_instead_of_raw_fetch():
    shared = (WEB_ROOT / "src/features/shared.tsx").read_text(encoding="utf-8")
    assert "apiText(" in shared
    assert "fetch(artifactUrl(" not in shared
