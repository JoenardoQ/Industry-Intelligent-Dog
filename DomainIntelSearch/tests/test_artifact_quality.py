import json
from pathlib import Path

from src.artifact_quality import evaluate_artifact
from src.portable_briefing import build_manifest, write_portable_html


GOOD = """# AI 周报

## 2026-09-02 模型进展

官方于 2026-09-02 发布新模型，性能与部署边界均有明确说明 [官方公告](https://example.org/release)。

## 产业链变化

算力供应商于 2026-09-02 扩大交付能力，产业链状态仍需持续复核 [企业披露](https://example.org/filing)。
"""


def test_quality_gate_is_deterministic_and_independent_of_fact_state(tmp_path):
    sidecar = tmp_path / "report.viz.json"
    sidecar.write_text(json.dumps({"directed_graph": {"nodes": [], "edges": []}}))
    result = evaluate_artifact(GOOD, {
        "generated_at": "2026-09-02", "status": "accepted",
        "references": [{"title": "官方公告", "url": "https://example.org/release"}],
        "claims": [{"claim": "新模型已发布", "evidence_urls": ["https://example.org/release"]}],
    }, sidecar_path=sidecar)
    assert result["passed"] is True
    assert result["fact_state"] == "accepted"
    assert result["artifact_status"] == "accepted"


def test_quality_gate_reports_machine_readable_failures_and_partial():
    broken = "# 报告\n\nTODO 待补充。\n\n重复结论。\n\n重复结论。\n\n[坏锚点](#missing) [危险](javascript:alert(1)) [未闭合](https://example.org"
    result = evaluate_artifact(broken, {"status": "accepted", "claims": [{"claim": "无证据"}]})
    codes = {item["code"] for item in result["failures"]}
    assert {"artifact_too_short", "placeholder_text", "duplicate_paragraph",
            "invalid_link", "missing_internal_anchor", "malformed_markdown_link",
            "claim_without_evidence"} <= codes
    assert result["fact_state"] == "accepted"
    assert result["artifact_status"] == "partial"


def test_portable_html_is_single_file_offline_and_escapes_embedded_payload(tmp_path):
    manifest = build_manifest(GOOD + "\n</script><script>boom()</script>", {
        "title": "AI 周报", "status": "partial", "generated_at": "2026-09-02",
        "chain_stage": "模型", "references": [{"title": "官方", "url": "https://example.org"}],
    })
    target = write_portable_html(tmp_path / "brief.html", manifest)
    text = target.read_text(encoding="utf-8")
    assert "fetch(" not in text and "http-equiv=\"refresh\"" not in text
    assert "<script src=" not in text and "<link rel=" not in text
    assert "</script><script>boom()" not in text
    for feature in ("localStorage", "window.print", "data-filter-source", "data-filter-status", "data-filter-chain"):
        assert feature in text
    assert manifest["content_sha256"] in text
