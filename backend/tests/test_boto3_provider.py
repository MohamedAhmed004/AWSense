"""Offline botocore.stub.Stubber unit tests for Boto3TelemetryProvider."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.stub import ANY, Stubber

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.auditor import audit_resources  # noqa: E402
from app.services.correlator import correlate_signals  # noqa: E402
from app.services.telemetry_provider import Boto3TelemetryProvider  # noqa: E402

_FIXED_NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def _dummy_session() -> boto3.Session:
    return boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )


def _make_provider(
    service_names: tuple[str, ...],
) -> tuple[Boto3TelemetryProvider, dict[str, Stubber]]:
    session = _dummy_session()
    clients: dict[str, Any] = {}
    stubbers: dict[str, Stubber] = {}
    for svc in service_names:
        client = session.client(svc, region_name="us-east-1")
        stubber = Stubber(client)
        stubber.activate()
        clients[svc] = client
        stubbers[svc] = stubber
    provider = Boto3TelemetryProvider(
        region_name="us-east-1",
        session=session,
        clients=clients,
        clock=lambda: _FIXED_NOW,
    )
    return provider, stubbers


def test_get_resources_collects_ec2_ebs_rds_and_s3() -> None:
    """Verify EC2, EBS, RDS backup status checks, and S3 bucket collection offline."""
    provider, stubbers = _make_provider(("ec2", "rds", "s3"))

    stubbers["ec2"].add_response(
        "describe_instances",
        {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-0111222333",
                            "InstanceType": "m5.xlarge",
                            "State": {"Name": "running"},
                            "Placement": {"AvailabilityZone": "us-east-1a"},
                            "LaunchTime": _FIXED_NOW - timedelta(days=10),
                            "Tags": [{"Key": "Name", "Value": "batch-worker"}],
                        }
                    ]
                }
            ]
        },
        {},
    )
    stubbers["ec2"].add_response(
        "describe_volumes",
        {
            "Volumes": [
                {
                    "VolumeId": "vol-0999888777",
                    "VolumeType": "gp3",
                    "Size": 500,
                    "State": "available",
                    "AvailabilityZone": "us-east-1b",
                    "SnapshotId": "",
                    "Encrypted": True,
                    "Attachments": [],
                    "Tags": [{"Key": "Name", "Value": "orphan-vol"}],
                }
            ]
        },
        {},
    )
    stubbers["rds"].add_response(
        "describe_db_instances",
        {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "db-no-backup",
                    "DBInstanceStatus": "available",
                    "Engine": "postgres",
                    "DBInstanceClass": "db.r6g.large",
                    "MultiAZ": True,
                    "AvailabilityZone": "us-east-1a",
                    "BackupRetentionPeriod": 0,
                    "StorageEncrypted": True,
                },
                {
                    "DBInstanceIdentifier": "db-stale-backup",
                    "DBInstanceStatus": "available",
                    "Engine": "postgres",
                    "DBInstanceClass": "db.t3.medium",
                    "MultiAZ": False,
                    "AvailabilityZone": "us-east-1a",
                    "BackupRetentionPeriod": 7,
                    "LatestRestorableTime": _FIXED_NOW - timedelta(days=10),
                    "StorageEncrypted": True,
                },
                {
                    "DBInstanceIdentifier": "db-healthy",
                    "DBInstanceStatus": "available",
                    "Engine": "mysql",
                    "DBInstanceClass": "db.t3.medium",
                    "MultiAZ": False,
                    "AvailabilityZone": "us-east-1c",
                    "BackupRetentionPeriod": 14,
                    "LatestRestorableTime": _FIXED_NOW - timedelta(hours=2),
                    "StorageEncrypted": True,
                },
            ]
        },
        {},
    )
    stubbers["s3"].add_response(
        "list_buckets",
        {
            "Buckets": [
                {
                    "Name": "awsense-audit-bucket",
                    "CreationDate": _FIXED_NOW - timedelta(days=90),
                }
            ]
        },
        {},
    )

    resources = provider.get_resources()
    assert json.loads(json.dumps(resources)) == resources
    by_id = {item["resource_id"]: item for item in resources}

    assert by_id["i-0111222333"]["resource_type"] == "ec2"
    assert by_id["i-0111222333"]["monthly_cost_usd"] == 140.16
    assert by_id["vol-0999888777"]["resource_type"] == "ebs"
    assert by_id["vol-0999888777"]["backup_status"] == "missing"
    assert by_id["vol-0999888777"]["metadata"]["attached"] is False
    assert by_id["vol-0999888777"]["monthly_cost_usd"] == 40.0

    assert by_id["db-no-backup"]["backup_status"] == "missing"
    assert by_id["db-no-backup"]["last_backup_at"] is None
    assert by_id["db-stale-backup"]["backup_status"] == "outdated"
    assert by_id["db-healthy"]["backup_status"] == "protected"
    assert by_id["db-healthy"]["last_backup_at"] is not None

    assert by_id["awsense-audit-bucket"]["resource_type"] == "s3"
    assert by_id["awsense-audit-bucket"]["backup_status"] == "not_applicable"

    for stubber in stubbers.values():
        stubber.assert_no_pending_responses()


def test_get_metrics_queries_cloudwatch_and_flags_anomalies() -> None:
    """Verify CloudWatch GetMetricData for explicit resource_id and EC2 discovery."""
    provider, stubbers = _make_provider(("ec2", "cloudwatch"))

    stubbers["ec2"].add_response(
        "describe_instances",
        {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-web-01",
                            "InstanceType": "c6i.xlarge",
                            "State": {"Name": "running"},
                            "Placement": {"AvailabilityZone": "us-east-1a"},
                        }
                    ]
                }
            ]
        },
        {},
    )

    t1 = _FIXED_NOW - timedelta(days=2)
    t2 = _FIXED_NOW - timedelta(days=1)
    t3 = _FIXED_NOW
    stubbers["cloudwatch"].add_response(
        "get_metric_data",
        {
            "MetricDataResults": [
                {"Id": "cpu_0", "Timestamps": [t1, t2, t3], "Values": [22.0, 24.0, 94.5]},
                {
                    "Id": "netin_0",
                    "Timestamps": [t1, t2, t3],
                    "Values": [1000.0, 1200.0, 25000.0],
                },
                {
                    "Id": "netout_0",
                    "Timestamps": [t1, t2, t3],
                    "Values": [2000.0, 2100.0, 95000.0],
                },
            ]
        },
        {"MetricDataQueries": ANY, "StartTime": ANY, "EndTime": ANY},
    )

    metrics = provider.get_metrics(days=7)
    assert len(metrics) == 3
    assert metrics[0]["cpu_utilization"] == 22.0
    assert metrics[0]["is_anomalous"] is False
    assert metrics[2]["cpu_utilization"] == 94.5
    assert metrics[2]["network_out_bytes"] == 95000.0
    assert metrics[2]["is_anomalous"] is True

    # Explicit resource_id skips ec2.describe_instances.
    stubbers["cloudwatch"].add_response(
        "get_metric_data",
        {
            "MetricDataResults": [
                {"Id": "cpu_0", "Timestamps": [t3], "Values": [15.0]},
                {"Id": "netin_0", "Timestamps": [t3], "Values": [500.0]},
                {"Id": "netout_0", "Timestamps": [t3], "Values": [700.0]},
            ]
        },
        {"MetricDataQueries": ANY, "StartTime": ANY, "EndTime": ANY},
    )
    single = provider.get_metrics(resource_id="i-explicit", days=2)
    assert len(single) == 1
    assert single[0]["resource_id"] == "i-explicit"

    with pytest.raises(ValueError):
        provider.get_metrics(days=0)

    for stubber in stubbers.values():
        stubber.assert_no_pending_responses()


def test_get_cloudtrail_events_flags_sensitive_and_off_hours() -> None:
    """Verify CloudTrail lookup_events parses CloudTrailEvent JSON and flags risks."""
    provider, stubbers = _make_provider(("cloudtrail",))

    routine_time = datetime(2026, 11, 24, 11, 0, tzinfo=timezone.utc)
    offhours_time = datetime(2026, 11, 24, 3, 15, tzinfo=timezone.utc)
    launch_time = datetime(2026, 11, 24, 3, 20, tzinfo=timezone.utc)

    stubbers["cloudtrail"].add_response(
        "lookup_events",
        {
            "Events": [
                {
                    "EventId": "ct-routine",
                    "EventName": "DescribeInstances",
                    "EventTime": routine_time,
                    "Username": "monitoring-ro",
                    "Resources": [],
                    "CloudTrailEvent": json.dumps(
                        {
                            "awsRegion": "us-east-1",
                            "sourceIPAddress": "10.0.0.5",
                            "eventSource": "ec2.amazonaws.com",
                        }
                    ),
                },
                {
                    "EventId": "ct-login-nomfa",
                    "EventName": "ConsoleLogin",
                    "EventTime": offhours_time,
                    "Username": "ci-deploy-temp",
                    "Resources": [],
                    "CloudTrailEvent": json.dumps(
                        {
                            "awsRegion": "ap-southeast-1",
                            "sourceIPAddress": "185.220.101.42",
                            "additionalEventData": {"MFAUsed": "No"},
                        }
                    ),
                },
                {
                    "EventId": "ct-run",
                    "EventName": "RunInstances",
                    "EventTime": launch_time,
                    "Username": "ci-deploy-temp",
                    "Resources": [
                        {"ResourceType": "AWS::EC2::Instance", "ResourceName": "i-rogue-1"}
                    ],
                    "CloudTrailEvent": json.dumps(
                        {
                            "awsRegion": "ap-southeast-1",
                            "sourceIPAddress": "185.220.101.42",
                        }
                    ),
                },
            ]
        },
        {"StartTime": ANY, "EndTime": ANY, "MaxResults": 50},
    )

    events = provider.get_cloudtrail_events()
    assert len(events) == 3
    by_id = {ev["event_id"]: ev for ev in events}

    assert by_id["ct-routine"]["is_anomalous"] is False
    assert by_id["ct-routine"]["risk_hint"] < 0.3
    assert by_id["ct-login-nomfa"]["is_anomalous"] is True
    assert by_id["ct-login-nomfa"]["risk_hint"] >= 0.9
    assert by_id["ct-login-nomfa"]["region"] == "ap-southeast-1"
    assert by_id["ct-run"]["is_anomalous"] is True
    assert by_id["ct-run"]["resource_id"] == "i-rogue-1"

    stubbers["cloudtrail"].assert_no_pending_responses()


def test_get_cost_usage_groups_daily_by_service_and_detects_spike() -> None:
    """Verify Cost Explorer DAILY SERVICE grouping, median baseline, and anomaly detection."""
    provider, stubbers = _make_provider(("ce",))

    stubbers["ce"].add_response(
        "get_cost_and_usage",
        {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-11-22", "End": "2026-11-23"},
                    "Groups": [
                        {
                            "Keys": ["AmazonEC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "20.00", "Unit": "USD"}},
                        }
                    ],
                },
                {
                    "TimePeriod": {"Start": "2026-11-23", "End": "2026-11-24"},
                    "Groups": [
                        {
                            "Keys": ["AmazonEC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "22.00", "Unit": "USD"}},
                        }
                    ],
                },
                {
                    "TimePeriod": {"Start": "2026-11-24", "End": "2026-11-25"},
                    "Groups": [
                        {
                            "Keys": ["AmazonEC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "182.00", "Unit": "USD"}},
                        }
                    ],
                },
            ]
        },
        {
            "TimePeriod": ANY,
            "Granularity": "DAILY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        },
    )

    records = provider.get_cost_usage(days=3)
    assert len(records) == 3
    assert records[0]["baseline_usd"] == 22.0
    assert records[0]["is_anomalous"] is False
    assert records[2]["cost_usd"] == 182.0
    assert records[2]["delta_usd"] == 160.0
    assert records[2]["is_anomalous"] is True

    with pytest.raises(ValueError):
        provider.get_cost_usage(days=0)

    stubbers["ce"].assert_no_pending_responses()


def test_get_traffic_logs_alb_waf_and_empty_fallback() -> None:
    """Verify ALB traffic collection, WAFv2 fallback, and empty [] when neither exists."""
    # 1. ALB metrics present.
    alb_provider, alb_stubbers = _make_provider(("cloudwatch",))
    alb_stubbers["cloudwatch"].add_response(
        "list_metrics",
        {
            "Metrics": [
                {
                    "Namespace": "AWS/ApplicationELB",
                    "MetricName": "RequestCount",
                    "Dimensions": [{"Name": "LoadBalancer", "Value": "app/prod-web/1234"}],
                }
            ]
        },
        {"Namespace": "AWS/ApplicationELB", "MetricName": "RequestCount"},
    )
    t1 = _FIXED_NOW - timedelta(hours=2)
    t2 = _FIXED_NOW - timedelta(hours=1)
    t3 = _FIXED_NOW
    alb_stubbers["cloudwatch"].add_response(
        "get_metric_data",
        {
            "MetricDataResults": [
                {"Id": "req_0", "Timestamps": [t1, t2, t3], "Values": [5000.0, 5200.0, 480000.0]},
                {
                    "Id": "bytes_0",
                    "Timestamps": [t1, t2, t3],
                    "Values": [1e9, 1.1e9, 100.0 * (1024**3)],
                },
            ]
        },
        {"MetricDataQueries": ANY, "StartTime": ANY, "EndTime": ANY},
    )
    alb_logs = alb_provider.get_traffic_logs()
    assert len(alb_logs) == 3
    assert alb_logs[0]["bot_flagged"] is False
    assert alb_logs[2]["bot_flagged"] is True
    assert alb_logs[2]["network_out_gb"] == 100.0
    alb_stubbers["cloudwatch"].assert_no_pending_responses()

    # 2. ALB absent, WAFv2 present.
    waf_provider, waf_stubbers = _make_provider(("cloudwatch",))
    waf_stubbers["cloudwatch"].add_response(
        "list_metrics",
        {"Metrics": []},
        {"Namespace": "AWS/ApplicationELB", "MetricName": "RequestCount"},
    )
    waf_stubbers["cloudwatch"].add_response(
        "list_metrics",
        {
            "Metrics": [
                {
                    "Namespace": "AWS/WAFV2",
                    "MetricName": "AllowedRequests",
                    "Dimensions": [{"Name": "WebACL", "Value": "prod-acl"}],
                }
            ]
        },
        {"Namespace": "AWS/WAFV2", "MetricName": "AllowedRequests"},
    )
    waf_stubbers["cloudwatch"].add_response(
        "get_metric_data",
        {
            "MetricDataResults": [
                {"Id": "allowed_0", "Timestamps": [t3], "Values": [10000.0]},
                {"Id": "blocked_0", "Timestamps": [t3], "Values": [40000.0]},
            ]
        },
        {"MetricDataQueries": ANY, "StartTime": ANY, "EndTime": ANY},
    )
    waf_logs = waf_provider.get_traffic_logs()
    assert len(waf_logs) == 1
    assert waf_logs[0]["request_count"] == 50000
    assert waf_logs[0]["bot_requests"] == 40000
    assert waf_logs[0]["bot_share_pct"] == 80.0
    assert waf_logs[0]["bot_flagged"] is True
    waf_stubbers["cloudwatch"].assert_no_pending_responses()

    # 3. Neither ALB nor WAFv2 exists -> [].
    empty_provider, empty_stubbers = _make_provider(("cloudwatch",))
    empty_stubbers["cloudwatch"].add_response(
        "list_metrics",
        {"Metrics": []},
        {"Namespace": "AWS/ApplicationELB", "MetricName": "RequestCount"},
    )
    empty_stubbers["cloudwatch"].add_response(
        "list_metrics",
        {"Metrics": []},
        {"Namespace": "AWS/WAFV2", "MetricName": "AllowedRequests"},
    )
    assert empty_provider.get_traffic_logs() == []
    empty_stubbers["cloudwatch"].assert_no_pending_responses()


def test_client_error_graceful_handling() -> None:
    """Verify partial and full AWS ClientError failures degrade cleanly to safe lists."""
    provider, stubbers = _make_provider(("ec2", "rds", "s3", "cloudwatch", "cloudtrail", "ce"))

    # Partial failure in get_resources: EC2/EBS/S3 succeed while RDS raises AccessDenied.
    stubbers["ec2"].add_response("describe_instances", {"Reservations": []}, {})
    stubbers["ec2"].add_response("describe_volumes", {"Volumes": []}, {})
    stubbers["rds"].add_client_error("describe_db_instances", service_error_code="AccessDenied")
    stubbers["s3"].add_response(
        "list_buckets",
        {"Buckets": [{"Name": "surviving-bucket", "CreationDate": _FIXED_NOW}]},
        {},
    )
    resources = provider.get_resources()
    assert len(resources) == 1
    assert resources[0]["resource_id"] == "surviving-bucket"

    stubbers["cloudwatch"].add_client_error(
        "get_metric_data", service_error_code="ThrottlingException"
    )
    assert provider.get_metrics(resource_id="i-123", days=7) == []

    stubbers["cloudtrail"].add_client_error("lookup_events", service_error_code="AccessDeniedException")
    assert provider.get_cloudtrail_events() == []

    stubbers["ce"].add_client_error("get_cost_and_usage", service_error_code="AccessDeniedException")
    assert provider.get_cost_usage(days=7) == []

    stubbers["cloudwatch"].add_client_error("list_metrics", service_error_code="AccessDeniedException")
    assert provider.get_traffic_logs() == []

    for stubber in stubbers.values():
        stubber.assert_no_pending_responses()


def test_boto3_provider_compatible_with_auditor_and_correlator() -> None:
    """Stubbed Boto3TelemetryProvider payloads work with audit_resources and correlate_signals."""
    provider, stubbers = _make_provider(("ec2", "rds", "s3", "cloudwatch", "cloudtrail", "ce"))

    stubbers["ec2"].add_response("describe_instances", {"Reservations": []}, {})
    stubbers["ec2"].add_response(
        "describe_volumes",
        {
            "Volumes": [
                {
                    "VolumeId": "vol-unattached",
                    "VolumeType": "gp3",
                    "Size": 100,
                    "State": "available",
                    "AvailabilityZone": "us-east-1a",
                    "SnapshotId": "",
                    "Attachments": [],
                }
            ]
        },
        {},
    )
    stubbers["rds"].add_response("describe_db_instances", {"DBInstances": []}, {})
    stubbers["s3"].add_response("list_buckets", {"Buckets": []}, {})
    resources = provider.get_resources()
    findings = audit_resources(resources, [])
    assert any(f["issue"] == "unattached_ebs" for f in findings)

    t_login = _FIXED_NOW.replace(hour=2, minute=10)
    t_spike = _FIXED_NOW.replace(hour=2, minute=25)
    t_cost = _FIXED_NOW.replace(hour=2, minute=40)

    stubbers["cloudtrail"].add_response(
        "lookup_events",
        {
            "Events": [
                {
                    "EventId": "ct-1",
                    "EventName": "RunInstances",
                    "EventTime": t_login,
                    "Username": "attacker",
                    "Resources": [{"ResourceType": "AWS::EC2::Instance", "ResourceName": "i-rogue"}],
                    "CloudTrailEvent": json.dumps({"awsRegion": "us-east-1"}),
                }
            ]
        },
        {"StartTime": ANY, "EndTime": ANY, "MaxResults": 50},
    )
    stubbers["cloudwatch"].add_response(
        "get_metric_data",
        {
            "MetricDataResults": [
                {"Id": "cpu_0", "Timestamps": [t_spike], "Values": [96.0]},
                {"Id": "netin_0", "Timestamps": [t_spike], "Values": [1000.0]},
                {"Id": "netout_0", "Timestamps": [t_spike], "Values": [9000.0]},
            ]
        },
        {"MetricDataQueries": ANY, "StartTime": ANY, "EndTime": ANY},
    )
    stubbers["ce"].add_response(
        "get_cost_and_usage",
        {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-11-23", "End": "2026-11-24"},
                    "Groups": [
                        {
                            "Keys": ["AmazonEC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "20.0", "Unit": "USD"}},
                        }
                    ],
                },
                {
                    "TimePeriod": {"Start": "2026-11-24", "End": "2026-11-25"},
                    "Groups": [
                        {
                            "Keys": ["AmazonEC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "200.0", "Unit": "USD"}},
                        }
                    ],
                },
            ]
        },
        {
            "TimePeriod": ANY,
            "Granularity": "DAILY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        },
    )

    ct_events = provider.get_cloudtrail_events()
    metric_spikes = [
        {
            "event_id": m["event_id"],
            "timestamp": m["timestamp"],
            "resource_id": m["resource_id"],
            "metric_name": "CPUUtilization",
            "value": m["cpu_utilization"],
            "baseline": m["baseline_cpu_pct"],
            "region": m["region"],
        }
        for m in provider.get_metrics(resource_id="i-rogue", days=2)
        if m["is_anomalous"]
    ]
    costs = [
        {**c, "timestamp": t_cost.strftime("%Y-%m-%dT%H:%M:%SZ")}
        for c in provider.get_cost_usage(days=2)
        if c["is_anomalous"]
    ]
    incidents = correlate_signals(
        cloudtrail_events=ct_events,
        metric_spikes=metric_spikes,
        cost_deltas=costs,
    )
    assert len(incidents) == 1
    assert incidents[0].incident_type == "iam_compute_surge"

    for stubber in stubbers.values():
        stubber.assert_no_pending_responses()
