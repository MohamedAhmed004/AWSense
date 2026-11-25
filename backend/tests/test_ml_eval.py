import pytest

from app.services.ml_eval import evaluate_ml


@pytest.fixture(scope="module")
def report():
    return evaluate_ml()


def test_detection_precision_recall_and_score_separation(report):
    assert report["precision"] >= 0.95
    assert report["recall"] >= 0.95
    assert report["score_separation"] > 0
    assert report["inference_ms_per_row"] > 0


def test_correlation_and_weighted_risk(report):
    incidents = report["incidents"]
    assert any(incident["matches_injected_anomaly"] for incident in incidents)
    assert all(
        0 <= incident["risk_score"] <= 100
        and incident["severity"] in {"low", "medium", "high", "critical"}
        for incident in incidents
    )
