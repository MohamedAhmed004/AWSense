import json
from datetime import datetime, timezone
from statistics import median
from time import perf_counter

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from app.services.correlator import MetricSpike, correlate_signals
from app.services.ml_detector import MLDetector
from app.services.mock_generator import MockTelemetryProvider
from app.services.risk_scorer import score_risk


def evaluate_ml() -> dict:
    """Benchmark the detector and summarize incident correlation and scoring."""
    reference_time = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
    baseline = MockTelemetryProvider(
        seed=42, reference_time=reference_time, include_anomalies=False,
    )
    evaluation = MockTelemetryProvider(
        seed=43, reference_time=reference_time, include_anomalies=True,
    )
    baseline_rows = baseline.get_metrics()
    target_rows = evaluation.get_metrics()
    labels = [row["is_anomalous"] for row in target_rows]
    inputs = [
        {key: value for key, value in row.items() if key != "is_anomalous"}
        for row in target_rows
    ]

    detector = MLDetector(threshold=0.70, random_state=42).fit(baseline_rows)
    started = perf_counter()
    predictions = detector.predict(inputs)
    elapsed_ms = (perf_counter() - started) * 1000
    flags = predictions["is_anomaly_predicted"].tolist()
    scores = predictions["anomaly_score"].tolist()

    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, flags, average="binary", zero_division=0,
    )
    tn, fp, fn, tp = confusion_matrix(labels, flags, labels=[False, True]).ravel()
    normal_median = median(score for score, label in zip(scores, labels) if not label)
    anomaly_median = median(score for score, label in zip(scores, labels) if label)

    spikes = [
        MetricSpike(
            event_id=row["event_id"],
            timestamp=row["timestamp"],
            resource_id=row["resource_id"],
            region=row["region"],
            metric_name="cpu_utilization",
            value=row["cpu_utilization"],
            baseline=row["baseline_cpu_pct"],
            anomaly_score=score,
        )
        for row, flag, score in zip(inputs, flags, scores)
        if flag
    ]
    cloudtrail = evaluation.get_cloudtrail_events()
    costs = evaluation.get_cost_usage()
    incidents = correlate_signals(
        cloudtrail_events=[
            {key: value for key, value in row.items() if key != "is_anomalous"}
            for row in cloudtrail
        ],
        metric_spikes=spikes,
        cost_deltas=[row for row in costs if row["delta_pct"] >= 10],
    )
    anomaly_ids = {
        row["event_id"] for row in target_rows + cloudtrail + costs
        if row["is_anomalous"]
    }
    incident_reports = []
    for incident in incidents:
        factors = incident.signal_breakdown
        ml_score = max(
            (signal.raw["anomaly_score"] for signal in incident.signals
             if signal.signal_type == "metric_spike"),
            default=0.0,
        )
        risk = score_risk(
            ml_score=ml_score,
            iam_risk=factors.iam_risk,
            resource_impact=factors.resource_impact,
            cost_impact=factors.cost_impact,
            traffic_anomaly=factors.traffic_anomaly,
        )
        incident_reports.append({
            "incident_id": incident.incident_id,
            "event_ids": incident.correlated_event_ids,
            "matches_injected_anomaly": bool(
                anomaly_ids.intersection(incident.correlated_event_ids)
            ),
            **risk,
        })

    return {
        "training_rows": len(baseline_rows),
        "evaluation_rows": len(target_rows),
        "threshold": detector.threshold,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": float(fp / (fp + tn)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "normal_median": normal_median,
        "anomaly_median": anomaly_median,
        "score_separation": anomaly_median - normal_median,
        "inference_ms_total": elapsed_ms,
        "inference_ms_per_row": elapsed_ms / len(target_rows),
        "incidents": incident_reports,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate_ml(), indent=2))
