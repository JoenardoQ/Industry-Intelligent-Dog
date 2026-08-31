from pathlib import Path

from src.evaluation import evaluate_file, evaluate_fixture


FIXTURES = Path(__file__).resolve().parents[1] / "evaluation" / "fixtures"


def test_versioned_ai_and_chips_fixtures_pass_quality_gates():
    for name in ("ai-v1.json", "chips-v1.json"):
        result = evaluate_file(FIXTURES / name)
        assert result["fixture_version"] == "1.0.0"
        assert result["passed"], result["failures"]


def test_gate_reports_metric_regression_instead_of_hiding_it():
    result = evaluate_fixture({
        "fixture_version": "test", "industry": "broken",
        "retrieval": [{"relevant": False}],
        "thresholds": {"retrieval_precision": 0.5},
    })
    assert not result["passed"]
    assert result["failures"]["retrieval_precision"] == {"score": 0.0, "minimum": 0.5}
