from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.industry_store import IndustryStore
from src.research_bootstrap import check_source_accessibility
from src import research_bootstrap as bootstrap
from src import report_generation as reports


DEEP_MARKDOWN = """# 产业链研究

本报告是研究初稿，未知数据为 N/A。[1]

## 原子事实索引

| claim | evidence_urls | as_of | confidence | status |
|---|---|---|---|---|
| 可核验事实 | [1] | 2026-08-29 | 0.9 | verified |

## references[]

- [1] [权威来源](https://example.com/source)；日期：2026-08-29。
"""


IMPACT_MARKDOWN = """# 算力供应受限：影响分析

## 1. 事件概述

**一句话概述：**算力供应受限将影响训练与推理。[1]

## 2. 受影响公司清单

### 2.1 公司甲

- **【事实】**公司甲受到供应约束。[1]

## 3. 供应链传导分析

1. **芯片制造**

   - **【事实】**先进芯片是上游约束。[1]

## 4. 相关技术与论文

| 技术方向 | 与事件的关系 | 关联论文 |
|---|---|---|
| 量化 | 降低推理需求 | Paper A [1] |

## 5. 相关政策脉络

### 中国

- **【事实】**政策支持算力互联。[1]

## 6. 影响等级评估

| 周期 | 等级 | 评估理由 |
|---|---|---|
| 短期：3个月 | **高** | 供给无法迅速扩张。[1] |

## 7. 投资与产业启示

- **【研判】**关注有效算力。[1]

## References

[1] [权威来源](https://example.com/source)，2026-08-29。
"""


class _FakeClient:
    def __init__(self, text: str):
        self.text = text

    def complete(self, _prompt):
        return types.SimpleNamespace(
            text=self.text,
            provider="codex_subscription",
            model="subscription_default",
        )


class _Response:
    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url

    def close(self):
        return None


class ReportGenerationContractTests(unittest.TestCase):
    def test_source_access_rejects_http_403_and_declared_paywall(self):
        sources = {
            "official": [
                {"name": "blocked", "url": "https://blocked.example/", "access": "open"},
                {"name": "paywall", "url": "https://paywall.example/",
                 "access": "partial_paywall"},
            ]
        }

        def head(url, **_kwargs):
            code = 403 if "blocked" in url else 200
            return _Response(code, url)

        with patch("requests.head", side_effect=head):
            checked = check_source_accessibility(sources, workers=1)

        blocked, paywall = checked["official"]
        self.assertFalse(blocked["access_check"]["reachable"])
        self.assertEqual(blocked["monitoring_status"], "recommended_manual")
        self.assertFalse(paywall["access_check"]["reachable"])
        self.assertEqual(paywall["monitoring_status"], "recommended_manual")

    def test_source_audit_reconciliation_reclassifies_stored_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI", "人工智能")
            store.save_sources({"official": [
                {"name": "open", "url": "https://open.example/", "access": "open",
                 "access_check": {"status_code": 200, "reachable": True}},
                {"name": "blocked", "url": "https://blocked.example/", "access": "open",
                 "access_check": {"status_code": 403, "reachable": True}},
                {"name": "paywall", "url": "https://paywall.example/",
                 "access": "partial_paywall",
                 "access_check": {"status_code": 200, "reachable": True}},
            ]})
            store._write_json(store.root / "bootstrap_status.json", {
                "state": "ready_for_review", "stages": {"sources": {"state": "passed"}}})

            result = bootstrap.reconcile_source_audit(store)

            sources = store.get_sources()["official"]
            by_name = {item["name"]: item for item in sources}
            self.assertTrue(by_name["open"]["access_check"]["reachable"])
            self.assertFalse(by_name["blocked"]["access_check"]["reachable"])
            self.assertFalse(by_name["paywall"]["access_check"]["reachable"])
            self.assertEqual(result["stages"]["sources"]["audit"]["live_reachable"], 1)

    def test_industry_report_metadata_persists_provider_and_model(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI", "人工智能")
            with patch("src.report_generation._client",
                       return_value=_FakeClient("# 趋势报告\n\n状态：draft；N/A。[1]\n\n"
                                                 "## references[]\n\n"
                                                 "[1] https://example.com/source")):
                result = reports.generate_industry_report({}, store, "trend_5y")

            metadata = json.loads(Path(result["visualization_file"]).read_text())
            self.assertEqual(metadata.get("provider"), "codex_subscription")
            self.assertEqual(metadata.get("model"), "subscription_default")
            self.assertEqual(metadata.get("status"), "partial")
            self.assertFalse(metadata["quality"]["passed"])
            self.assertTrue(Path(metadata["portable_file"]).is_file())

    def test_deep_report_writes_declared_claim_and_reference_sidecars(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI", "人工智能")
            with patch("src.report_generation._client",
                       return_value=_FakeClient(DEEP_MARKDOWN)):
                result = reports.generate_deep_report({}, store, "chain")

            deep = store.reports / "deep"
            self.assertTrue((deep / "chain.references.json").exists())
            self.assertTrue((deep / "chain.claims.json").exists())
            references = json.loads((deep / "chain.references.json").read_text())
            claims = json.loads((deep / "chain.claims.json").read_text())
            visualization = json.loads(Path(result["visualization_file"]).read_text())
            self.assertEqual(references["references"][0]["urls"],
                             ["https://example.com/source"])
            self.assertEqual(claims["claims"][0], {
                "claim": "可核验事实",
                "evidence_urls": ["[1]"],
                "as_of": "2026-08-29",
                "confidence": 0.9,
                "status": "verified",
            })
            self.assertEqual(visualization.get("provider"), "codex_subscription")

    def test_impact_report_merges_structured_result_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI", "人工智能")
            with patch("src.report_generation._client",
                       return_value=_FakeClient(IMPACT_MARKDOWN)):
                result = reports.generate_impact_report({}, store, {}, "算力供应受限")

            metadata = json.loads((store.one_time / "impact" / "算力供应受限" /
                                   "impact.json").read_text())
            required = {"summary", "companies", "supply_chain", "papers", "policies",
                        "impact_rating", "takeaways", "references"}
            self.assertTrue(required <= metadata.keys())
            self.assertEqual(metadata["summary"], "算力供应受限将影响训练与推理。[1]")
            self.assertEqual(metadata["companies"][0]["name"], "公司甲")
            self.assertEqual(metadata["papers"], [{
                "技术方向": "量化",
                "与事件的关系": "降低推理需求",
                "关联论文": "Paper A [1]",
            }])
            self.assertEqual(metadata["impact_rating"]["短期：3个月"]["rating"], "高")
            self.assertEqual(metadata.get("provider"), "codex_subscription")
            self.assertEqual(metadata.get("model"), "subscription_default")
            self.assertEqual(metadata.get("status"), "partial")
            self.assertFalse(metadata["quality"]["passed"])
            self.assertTrue(Path(metadata["portable_file"]).is_file())
            self.assertEqual(result["metadata"], str(store.one_time / "impact" /
                                                     "算力供应受限" / "impact.json"))

    def test_existing_step8_artifacts_can_be_reconciled_without_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            store = IndustryStore(temp, "AI", "人工智能")
            for report_id in ("trend_5y", "popular_2y", "tech_6m"):
                (store.reports / f"{report_id}.md").write_text(DEEP_MARKDOWN)
                store._write_json(store.reports / f"{report_id}.viz.json", {"type": "bar"})
            deep = store.reports / "deep"
            deep.mkdir(parents=True, exist_ok=True)
            (deep / "chain.md").write_text(DEEP_MARKDOWN)
            store._write_json(deep / "chain.viz.json", {"type": "bar"})
            impact = store.one_time / "impact" / "算力供应受限"
            impact.mkdir(parents=True, exist_ok=True)
            (impact / "analysis.md").write_text(IMPACT_MARKDOWN)
            store._write_json(impact / "impact.json", {"event": "算力供应受限"})

            self.assertTrue(hasattr(reports, "reconcile_existing_step8_artifacts"))
            result = reports.reconcile_existing_step8_artifacts(
                store, "codex_subscription", "subscription_default")

            self.assertEqual(result, {"industry_reports": 3, "deep_reports": 1,
                                      "impact_reports": 1})
            self.assertTrue((deep / "chain.references.json").exists())
            self.assertTrue((deep / "chain.claims.json").exists())
            self.assertEqual(json.loads((impact / "impact.json").read_text())["provider"],
                             "codex_subscription")


if __name__ == "__main__":
    unittest.main()
