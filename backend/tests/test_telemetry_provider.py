"""Unit tests for TelemetryProvider interface, factory, and MockTelemetryProvider scenarios."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import boto3
from botocore.stub import Stubber

from app.services.correlator import correlate_signals  # noqa: E402
from app.services.mock_generator import MockTelemetryProvider  # noqa: E402
from app.services.telemetry_provider import (  # noqa: E402
    Boto3TelemetryProvider,
    TelemetryProvider,
    get_telemetry_provider,
)


def test_provider_factory_and_boto3_provider_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory switches between mock and aws providers, and boto3 collectors degrade cleanly."""
    monkeypatch.delenv("DATA_SOURCE", raising=False)
    default_provider = get_telemetry_provider()
    assert isinstance(default_provider, TelemetryProvider)
    assert isinstance(default_provider, MockTelemetryProvider)

    monkeypatch.setenv("DATA_SOURCE", "aws")
    aws_provider = get_telemetry_provider()
    assert isinstance(aws_provider, Boto3TelemetryProvider)

    session = boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    clients = {}
    stubbers = []
    for svc, ops in (
        ("ec2", ["describe_instances", "describe_volumes", "describe_instances"]),
        ("rds", ["describe_db_instances"]),
        ("s3", ["list_buckets"]),
        ("cloudwatch", ["list_metrics"]),
        ("cloudtrail", ["lookup_events"]),
        ("ce", ["get_cost_and_usage"]),
    ):
        client = session.client(svc, region_name="us-east-1")
        stubber = Stubber(client)
        for op in ops:
            stubber.add_client_error(op, service_error_code="AccessDeniedException")
        stubber.activate()
        clients[svc] = client
        stubbers.append(stubber)

    stubbed_aws = Boto3TelemetryProvider(region_name="us-east-1", session=session, clients=clients)
    assert stubbed_aws.get_resources() == []
    assert stubbed_aws.get_metrics() == []
    assert stubbed_aws.get_cloudtrail_events() == []
    assert stubbed_aws.get_traffic_logs() == []
    assert stubbed_aws.get_cost_usage() == []
    for stubber in stubbers:
        stubber.assert_no_pending_responses()

    with pytest.raises(ValueError):
        get_telemetry_provider("invalid_source")


def test_mock_provider_json_serializable_and_deterministic() -> None:
    """All five provider outputs are deterministic and valid JSON."""
    p1 = MockTelemetryProvider(seed=99)
    p2 = MockTelemetryProvider(seed=99)

    for method in (
        "get_resources",
        "get_metrics",
        "get_cloudtrail_events",
        "get_traffic_logs",
        "get_cost_usage",
    ):
        data1 = getattr(p1, method)()
        data2 = getattr(p2, method)()
        assert data1 == data2
        assert len(data1) > 0
        # Ensure pure JSON roundtrip succeeds with no non-serializable types.
        assert json.loads(json.dumps(data1)) == data1


def test_mock_scenarios_cover_waste_breach_and_bot_traffic() -> None:
    """Verify injected waste, backup gaps, 8-instance IAM breach, and 2.4M-scale bot traffic."""
    provider = MockTelemetryProvider(include_anomalies=True)

    resources = provider.get_resources()
    by_id = {item["resource_id"]: item for item in resources}

    # 1. Underutilized EC2 (~7% CPU), unattached EBS, and RDS missing backups.
    assert by_id["i-0a1b2c3d4e5f60001"]["utilization_pct"] < 10.0
    assert by_id["vol-09911223344556677"]["status"] == "available"
    assert by_id["vol-09911223344556677"]["metadata"]["attached"] is False
    assert by_id["db-prod-orders-01"]["backup_status"] == "missing"
    assert by_id["db-prod-orders-01"]["last_backup_at"] is None

    # 2. IAM breach launching 8 rogue EC2 instances + SG change + CPU/cost jump.
    events = provider.get_cloudtrail_events()
    run_instances = next(ev for ev in events if ev["event_name"] == "RunInstances")
    assert len(run_instances["resource_ids"]) == 8
    assert run_instances["region"] == "ap-southeast-1"
    for rogue_id in run_instances["resource_ids"]:
        assert rogue_id in by_id
        assert by_id[rogue_id]["utilization_pct"] > 90.0

    # 3. 2.4M-scale traffic volume & flagged bots.
    traffic = provider.get_traffic_logs()
    total_requests = sum(item["request_count"] for item in traffic)
    assert total_requests >= 2_400_000
    assert any(item["bot_flagged"] is True for item in traffic)

    # 4. 30-day metrics & cost spikes.
    metrics = provider.get_metrics(days=30)
    assert any(m["is_anomalous"] and m["cpu_utilization"] > 90.0 for m in metrics)
    assert len(provider.get_metrics(resource_id="i-0baseweb01", days=30)) == 30

    costs = provider.get_cost_usage(days=30)
    assert any(c["is_anomalous"] and c["delta_usd"] > 100.0 for c in costs)


def test_baseline_only_excludes_anomalies_and_anomalies_correlate() -> None:
    """Baseline mode omits anomalies, and anomaly mode feeds directly into correlator."""
    clean = MockTelemetryProvider(include_anomalies=False)
    assert not any(ev["is_anomalous"] for ev in clean.get_cloudtrail_events())
    assert not any(m["is_anomalous"] for m in clean.get_metrics())
    assert not any(t["bot_flagged"] for t in clean.get_traffic_logs())
    assert not any(c["is_anomalous"] for c in clean.get_cost_usage())

    provider = MockTelemetryProvider(include_anomalies=True)
    anomalous_metrics = []
    for m in provider.get_metrics():
        if not m["is_anomalous"]:
            continue
        anomalous_metrics.append(
            {
                "event_id": m["event_id"],
                "timestamp": m["timestamp"],
                "resource_id": m["resource_id"],
                "metric_name": "CPUUtilization",
                "value": m["cpu_utilization"],
                "baseline": m["baseline_cpu_pct"],
                "region": m["region"],
            }
        )
        if m["request_count"] >= 1_000_000:
            anomalous_metrics.append(
                {
                    "event_id": f"{m['event_id']}-req",
                    "timestamp": m["timestamp"],
                    "resource_id": m["resource_id"],
                    "metric_name": "RequestCount",
                    "value": m["request_count"],
                    "baseline": 148_500.0,
                    "region": m["region"],
                }
            )
    anomalous_costs = [c for c in provider.get_cost_usage() if c["is_anomalous"]]
    anomalous_ct = [ev for ev in provider.get_cloudtrail_events() if ev["is_anomalous"]]

    incidents = correlate_signals(
        cloudtrail_events=anomalous_ct,
        metric_spikes=anomalous_metrics,
        cost_deltas=anomalous_costs,
        time_window_minutes=60,
    )
    incident_types = {inc.incident_type for inc in incidents}
    assert {"iam_compute_surge", "bot_traffic_cost_spike"}.issubset(incident_types)


def test_cli_module_emits_valid_json() -> None:
    """Running python -m app.services.mock_generator outputs valid JSON across all 5 keys."""
    proc = subprocess.run(
        [sys.executable, "-m", "app.services.mock_generator", "--days", "7"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["source"] == "mock"
    assert {
        "resources",
        "metrics",
        "cloudtrail_events",
        "traffic_logs",
        "cost_usage",
    }.issubset(payload.keys())
