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


def test_research_chapters_are_not_news_items():
    text = GOOD + "\n## 研究方法\n\n本报告将企业披露、学术论文与产业链关系分开分析，来源数量不作为事实正确性的替代判断。\n"
    assert evaluate_artifact(text, {"status": "draft"})["passed"]
    briefing = evaluate_artifact(text, {"status": "draft", "artifact_type": "briefing"})
    assert {"key_item_missing_date", "key_item_missing_source"} <= {
        item["code"] for item in briefing["failures"]}


def test_task_bundle_reports_partial_and_skipped_outputs(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from src.services import task_executor

    texts = iter([GOOD, "TODO"])
    def complete(_prompt):
        return SimpleNamespace(text=next(texts), provider="test", model="test",
                               response_id="", usage={})
    monkeypatch.setattr(task_executor, "create_provider", lambda *_args: SimpleNamespace(complete=complete))
    bundle = tmp_path / "tasks.json"
    bundle.write_text(json.dumps([{"prompt": "research"}, {"prompt": "broken"}, {}]))
    result = task_executor.execute_bundle({}, SimpleNamespace(industry_root=tmp_path), bundle)
    assert [item["status"] for item in result["results"]] == ["draft", "partial", "skipped"]
    assert result["status"] == "partial"
    assert result["results"][1]["quality"]["passed"] is False
    assert json.loads(Path(result["manifest"]).read_text())["status"] == "partial"


def test_bundle_runs_keep_distinct_snapshots_with_the_same_clock_and_destination(tmp_path, monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace
    from src.services import task_executor

    class FixedClock:
        @staticmethod
        def now():
            return datetime(2026, 9, 11, 12, 0, 0)

    texts = iter([GOOD, GOOD + "\nAdditional findings.\n"])
    monkeypatch.setattr(task_executor, "datetime", FixedClock)
    monkeypatch.setattr(task_executor, "create_provider", lambda *_args: SimpleNamespace(
        complete=lambda _prompt: SimpleNamespace(text=next(texts), provider="test",
                                                 model="test", response_id="", usage={})))
    bundle = tmp_path / "tasks.json"
    bundle.write_text(json.dumps([{"prompt": "research", "output_file": "latest.md"}]))
    context = SimpleNamespace(industry_root=tmp_path)
    first = task_executor.execute_bundle({}, context, bundle)
    second = task_executor.execute_bundle({}, context, bundle)
    assert first["manifest"] != second["manifest"]
    assert Path(first["results"][0]["snapshot_file"]).read_text() == GOOD
    assert Path(second["results"][0]["snapshot_file"]).read_text() == GOOD + "\nAdditional findings.\n"
    assert (tmp_path / "latest.md").read_text() == GOOD + "\nAdditional findings.\n"


def test_bundle_checkpoints_before_call_and_preserves_failure_without_retry(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from src.services import task_executor

    calls = []
    def complete(prompt):
        manifests = list(tmp_path.glob("one_time/research/runs/*.json"))
        assert len(manifests) == 1
        state = json.loads(manifests[0].read_text())
        assert state["status"] == "running"
        assert state["results"][-1]["status"] == "running"
        calls.append(prompt)
        if prompt == "second":
            assert state["results"][0]["status"] == "draft"
            raise RuntimeError("synthetic secret must not enter manifest")
        return SimpleNamespace(text=GOOD, provider="test", model="test", response_id="", usage={})
    monkeypatch.setattr(task_executor, "create_provider", lambda *_args: SimpleNamespace(complete=complete))
    bundle = tmp_path / "tasks.json"
    bundle.write_text(json.dumps([{"prompt": item} for item in ("first", "second", "third")]))
    result = task_executor.execute_bundle({}, SimpleNamespace(industry_root=tmp_path), bundle)
    assert calls == ["first", "second"]
    assert [item["status"] for item in result["results"]] == ["draft", "failed", "not_started"]
    assert result["status"] == "partial"
    saved = Path(result["manifest"]).read_text()
    assert "synthetic secret" not in saved
    assert json.loads(saved)["results"][1]["error_type"] == "RuntimeError"
    assert Path(result["results"][0]["snapshot_file"]).read_text() == GOOD


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
