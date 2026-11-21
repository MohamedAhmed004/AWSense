"""Unit tests for the multi-signal event correlation engine."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Allow running directly from repo root or backend/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.entities import AlertSeverity  # noqa: E402
from app.services.correlator import (  # noqa: E402
    CloudTrailEvent,
    CostDelta,
    MetricSpike,
    correlate_signals,
    normalize_signals,
    parse_timestamp,
    signals_are_related,
)


def test_correlate_iam_breach_compute_and_cost_surge() -> None:
    """IAM breach events, EC2 CPU spike, and cost delta within window merge into one incident."""
    incidents = correlate_signals(
        cloudtrail_events=[
            CloudTrailEvent(
                event_id="ct-1",
                timestamp="2026-11-21T02:10:00Z",
                event_name="ConsoleLogin",
                region="ap-southeast-1",
                principal="deploy-bot",
                source_ip="198.51.100.77",
                is_anomalous=True,
                risk_hint=0.90,
            ),
            CloudTrailEvent(
                event_id="ct-2",
                timestamp="2026-11-21T02:15:00Z",
                event_name="AuthorizeSecurityGroupIngress",
                region="ap-southeast-1",
                principal="deploy-bot",
                resource_id="sg-1234",
                is_anomalous=True,
                risk_hint=0.85,
            ),
            CloudTrailEvent(
                event_id="ct-3",
                timestamp="2026-11-21T02:20:00Z",
                event_name="RunInstances",
                region="ap-southeast-1",
                principal="deploy-bot",
                resource_id="i-rogue01",
                is_anomalous=True,
                risk_hint=0.95,
            ),
        ],
        metric_spikes=[
            MetricSpike(
                event_id="cw-1",
                timestamp="2026-11-21T02:35:00Z",
                resource_id="i-rogue01",
                metric_name="CPUUtilization",
                value=95.0,
                baseline=15.0,
                region="ap-southeast-1",
                anomaly_score=0.92,
            )
        ],
        cost_deltas=[
            CostDelta(
                event_id="ce-1",
                timestamp="2026-11-21T02:50:00Z",
                service="AmazonEC2",
                delta_usd=480.0,
                baseline_usd=50.0,
                delta_pct=960.0,
                resource_id="i-rogue01",
                region="ap-southeast-1",
            )
        ],
        time_window_minutes=60,
    )

    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.incident_id == "inc_0001"
    assert inc.incident_type == "iam_compute_surge"
    assert inc.severity in {AlertSeverity.HIGH, AlertSeverity.CRITICAL}
    assert inc.risk_score >= 65.0
    assert set(inc.correlated_event_ids) == {"ct-1", "ct-2", "ct-3", "cw-1", "ce-1"}
    assert inc.signal_breakdown.cloudtrail_count == 3
    assert inc.signal_breakdown.metric_spike_count == 1
    assert inc.signal_breakdown.cost_delta_count == 1
    assert inc.signal_breakdown.iam_risk > 0
    assert inc.signal_breakdown.cost_impact > 0
    assert inc.signal_breakdown.total_cost_delta_usd == 480.0
    assert "i-rogue01" in inc.resource_ids
    assert "deploy-bot" in inc.principals


def test_correlate_bot_traffic_and_cost_spike() -> None:
    """High-volume traffic spikes and cost deltas without IAM events classify as bot traffic."""
    incidents = correlate_signals(
        metric_spikes=[
            {
                "event_id": "cw-req-1",
                "timestamp": "2026-11-20T19:00:00Z",
                "resource_id": "i-web-01",
                "metric_name": "RequestCount",
                "value": 2400000,
                "baseline": 140000,
                "region": "us-east-1",
                "anomaly_score": 0.88,
            },
            {
                "event_id": "cw-cpu-1",
                "timestamp": "2026-11-20T19:12:00Z",
                "resource_id": "i-web-01",
                "metric_name": "CPUUtilization",
                "value": 91.0,
                "baseline": 30.0,
                "region": "us-east-1",
                "anomaly_score": 0.82,
            },
        ],
        cost_deltas=[
            {
                "event_id": "ce-egress-1",
                "timestamp": "2026-11-20T19:30:00Z",
                "service": "AWSDataTransfer",
                "delta_usd": 145.0,
                "baseline_usd": 25.0,
                "delta_pct": 580.0,
                "resource_id": "i-web-01",
                "region": "us-east-1",
            }
        ],
    )

    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.incident_type == "bot_traffic_cost_spike"
    assert inc.severity in {AlertSeverity.HIGH, AlertSeverity.CRITICAL}
    assert inc.signal_breakdown.traffic_anomaly > 0
    assert inc.signal_breakdown.cost_delta_count == 1
    assert set(inc.correlated_event_ids) == {"cw-req-1", "cw-cpu-1", "ce-egress-1"}


def test_time_window_boundaries() -> None:
    """Signals at 60m correlate together; signals separated by 61m remain independent."""
    base = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)

    # Exactly 60 minutes apart -> correlates.
    correlated = correlate_signals(
        metric_spikes=[
            MetricSpike(
                event_id="cw-a",
                timestamp=base,
                resource_id="i-111",
                metric_name="CPUUtilization",
                value=88.0,
                baseline=20.0,
                region="us-east-1",
            )
        ],
        cost_deltas=[
            CostDelta(
                event_id="ce-a",
                timestamp=base + timedelta(minutes=60),
                service="AmazonEC2",
                delta_usd=90.0,
                baseline_usd=20.0,
                resource_id="i-111",
                region="us-east-1",
            )
        ],
        time_window_minutes=60,
        min_signals=2,
    )
    assert len(correlated) == 1
    assert correlated[0].correlated_event_ids == ["cw-a", "ce-a"]

    # 61 minutes apart -> exceeds window -> no 2-signal incident.
    separated = correlate_signals(
        metric_spikes=[
            MetricSpike(
                event_id="cw-b",
                timestamp=base,
                resource_id="i-111",
                metric_name="CPUUtilization",
                value=88.0,
                baseline=20.0,
                region="us-east-1",
            )
        ],
        cost_deltas=[
            CostDelta(
                event_id="ce-b",
                timestamp=base + timedelta(minutes=61),
                service="AmazonEC2",
                delta_usd=90.0,
                baseline_usd=20.0,
                resource_id="i-111",
                region="us-east-1",
            )
        ],
        time_window_minutes=60,
        min_signals=2,
    )
    assert separated == []


def test_isolation_unrelated_resources_and_noise_filtering() -> None:
    """Unrelated resources in the same region do not merge and singletons are filtered."""
    ts = "2026-11-21T12:00:00Z"

    # Disjoint resource_ids in the same region must NOT merge even via a region-level cost delta.
    incidents = correlate_signals(
        metric_spikes=[
            MetricSpike(
                event_id="cw-res-1",
                timestamp=ts,
                resource_id="i-alpha",
                metric_name="CPUUtilization",
                value=85.0,
                baseline=20.0,
                region="us-east-1",
            ),
            MetricSpike(
                event_id="cw-res-2",
                timestamp="2026-11-21T12:05:00Z",
                resource_id="i-beta",
                metric_name="CPUUtilization",
                value=82.0,
                baseline=25.0,
                region="us-east-1",
            ),
        ],
        cost_deltas=[
            CostDelta(
                event_id="ce-region-only",
                timestamp="2026-11-21T12:10:00Z",
                service="AmazonEC2",
                delta_usd=60.0,
                baseline_usd=20.0,
                region="us-east-1",
            )
        ],
        min_signals=2,
    )

    # At most one resource cluster picks up the region-only cost delta; i-alpha and i-beta never merge.
    assert len(incidents) == 1
    assert not ({"i-alpha", "i-beta"}.issubset(set(incidents[0].resource_ids)))

    # Isolated single event with min_signals=2 produces no incidents.
    single_only = correlate_signals(
        cloudtrail_events=[
            CloudTrailEvent(
                event_id="ct-solo",
                timestamp=ts,
                event_name="ConsoleLogin",
                region="us-west-2",
                principal="alice",
            )
        ],
        min_signals=2,
    )
    assert single_only == []

    # Same-source-only cluster is excluded when require_multi_source=True.
    same_source_filtered = correlate_signals(
        metric_spikes=[
            MetricSpike(
                event_id="cw-1",
                timestamp=ts,
                resource_id="i-alpha",
                metric_name="CPUUtilization",
                value=85.0,
                baseline=20.0,
                region="us-east-1",
            ),
            MetricSpike(
                event_id="cw-2",
                timestamp="2026-11-21T12:10:00Z",
                resource_id="i-alpha",
                metric_name="NetworkOut",
                value=5000000.0,
                baseline=100000.0,
                region="us-east-1",
            ),
        ],
        min_signals=2,
        require_multi_source=True,
    )
    assert same_source_filtered == []


def test_signals_are_related_helper() -> None:
    """Verify pairwise signal relation logic directly."""
    signals = normalize_signals(
        cloudtrail_events=[
            CloudTrailEvent(
                event_id="ct-login",
                timestamp="2026-11-21T08:00:00Z",
                event_name="ConsoleLogin",
                region="us-east-1",
                principal="bob",
            ),
            CloudTrailEvent(
                event_id="ct-run",
                timestamp="2026-11-21T08:10:00Z",
                event_name="RunInstances",
                region="us-east-1",
                principal="bob",
                resource_id="i-1",
            ),
        ],
        metric_spikes=[
            MetricSpike(
                event_id="cw-i1",
                timestamp="2026-11-21T08:15:00Z",
                resource_id="i-1",
                metric_name="CPUUtilization",
                value=90.0,
                region="us-east-1",
            ),
            MetricSpike(
                event_id="cw-i2",
                timestamp="2026-11-21T08:15:00Z",
                resource_id="i-2",
                metric_name="CPUUtilization",
                value=90.0,
                region="us-east-1",
            ),
        ],
    )
    by_id = {sig.event_id: sig for sig in signals}
    gap = timedelta(minutes=60)

    assert signals_are_related(by_id["ct-login"], by_id["ct-run"], gap) is True
    assert signals_are_related(by_id["ct-run"], by_id["cw-i1"], gap) is True
    # Disjoint specific resources in the same region do NOT relate directly.
    assert signals_are_related(by_id["cw-i1"], by_id["cw-i2"], gap) is False
    # Tight gap excludes events further apart.
    assert signals_are_related(by_id["ct-login"], by_id["ct-run"], timedelta(minutes=5)) is False


def test_correlator_edge_cases_and_validation() -> None:
    """Empty inputs, out-of-order mixed timestamps, and invalid parameters behave properly."""
    assert correlate_signals() == []

    naive_dt = datetime(2026, 11, 21, 14, 30)
    aware_plus_2 = datetime(2026, 11, 21, 16, 45, tzinfo=timezone(timedelta(hours=2)))
    assert parse_timestamp("2026-11-21T14:30:00Z") == datetime(2026, 11, 21, 14, 30, tzinfo=timezone.utc)
    assert parse_timestamp(naive_dt).tzinfo == timezone.utc
    assert parse_timestamp(aware_plus_2) == datetime(2026, 11, 21, 14, 45, tzinfo=timezone.utc)

    # Supply events intentionally out of chronological order with mixed timestamp types.
    incidents = correlate_signals(
        cost_deltas=[
            CostDelta(
                event_id="ce-late",
                timestamp=aware_plus_2,
                service="AmazonEC2",
                delta_usd=120.0,
                resource_id="i-mixed",
                region="eu-west-1",
            )
        ],
        metric_spikes=[
            MetricSpike(
                event_id="cw-early",
                timestamp=naive_dt,
                resource_id="i-mixed",
                metric_name="CPUUtilization",
                value=92.0,
                baseline=20.0,
                region="eu-west-1",
            )
        ],
    )
    assert len(incidents) == 1
    assert incidents[0].window_start <= incidents[0].window_end
    assert incidents[0].correlated_event_ids == ["cw-early", "ce-late"]

    with pytest.raises(ValueError):
        correlate_signals(time_window_minutes=0)

    with pytest.raises(ValueError):
        correlate_signals(min_signals=0)
