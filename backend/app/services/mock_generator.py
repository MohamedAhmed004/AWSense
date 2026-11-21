"""Synthetic AWS telemetry generator for baseline, waste, breach, and bot scenarios."""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.telemetry_provider import TelemetryProvider

_DEFAULT_ANCHOR = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
_ROGUE_INSTANCE_IDS = tuple(f"i-0rogue{idx:04d}" for idx in range(1, 9))


def _iso(dt: datetime) -> str:
    """Format a UTC datetime as an ISO-8601 Z string."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MockTelemetryGenerator:
    """Deterministic generator producing AWS-shaped resources, metrics, logs, and billing."""

    def __init__(
        self,
        *,
        seed: int = 42,
        reference_time: datetime | None = None,
        include_anomalies: bool = True,
    ) -> None:
        self.seed = seed
        self.reference_time = (reference_time or _DEFAULT_ANCHOR).astimezone(timezone.utc)
        self.include_anomalies = include_anomalies

    def generate_resources(self) -> list[dict[str, Any]]:
        """Generate monitored EC2, EBS, RDS, and S3 inventory including waste/backup gaps."""
        anchor = self.reference_time
        resources: list[dict[str, Any]] = [
            {
                "resource_id": "i-0baseweb01",
                "name": "prod-api-web-01",
                "resource_type": "ec2",
                "region": "us-east-1",
                "status": "running",
                "utilization_pct": 34.5,
                "backup_status": "protected",
                "last_backup_at": _iso(anchor - timedelta(hours=8)),
                "monthly_cost_usd": 145.00,
                "metadata": {"instance_type": "t3.large", "env": "production"},
            },
            {
                "resource_id": "i-0a1b2c3d4e5f60001",
                "name": "legacy-batch-worker",
                "resource_type": "ec2",
                "region": "us-east-1",
                "status": "running",
                "utilization_pct": 7.1,
                "backup_status": "protected",
                "last_backup_at": _iso(anchor - timedelta(hours=9)),
                "monthly_cost_usd": 168.00,
                "metadata": {
                    "instance_type": "m5.xlarge",
                    "env": "production",
                    "waste_reason": "sustained_low_cpu",
                },
            },
            {
                "resource_id": "i-0a1b2c3d4e5f60002",
                "name": "public-catalog-web",
                "resource_type": "ec2",
                "region": "us-east-1",
                "status": "running",
                "utilization_pct": 91.4 if self.include_anomalies else 31.2,
                "backup_status": "protected",
                "last_backup_at": _iso(anchor - timedelta(hours=8)),
                "monthly_cost_usd": 295.50 if self.include_anomalies else 155.00,
                "metadata": {"instance_type": "c6i.xlarge", "env": "production"},
            },
            {
                "resource_id": "vol-09911223344556677",
                "name": "orphan-analytics-ebs",
                "resource_type": "ebs",
                "region": "us-east-1",
                "status": "available",
                "utilization_pct": 0.0,
                "backup_status": "missing",
                "last_backup_at": None,
                "monthly_cost_usd": 48.00,
                "metadata": {"volume_type": "gp3", "size_gb": 600, "attached": False},
            },
            {
                "resource_id": "db-prod-orders-01",
                "name": "orders-primary-rds",
                "resource_type": "rds",
                "region": "us-east-1",
                "status": "available",
                "utilization_pct": 54.3,
                "backup_status": "missing",
                "last_backup_at": None,
                "monthly_cost_usd": 412.25,
                "metadata": {
                    "engine": "postgres",
                    "instance_class": "db.r6g.large",
                    "multi_az": True,
                    "backup_retention_days": 0,
                },
            },
            {
                "resource_id": "s3-awsense-audit-logs",
                "name": "central-audit-archive",
                "resource_type": "s3",
                "region": "us-east-1",
                "status": "active",
                "utilization_pct": 62.0,
                "backup_status": "protected",
                "last_backup_at": _iso(anchor - timedelta(hours=12)),
                "monthly_cost_usd": 177.00,
                "metadata": {"versioning": True, "encryption": "aws:kms"},
            },
        ]

        if self.include_anomalies:
            rng = random.Random(self.seed + 101)
            for idx, instance_id in enumerate(_ROGUE_INSTANCE_IDS, start=1):
                resources.append(
                    {
                        "resource_id": instance_id,
                        "name": f"unrecognized-compute-{idx:02d}",
                        "resource_type": "ec2",
                        "region": "ap-southeast-1",
                        "status": "running",
                        "utilization_pct": round(rng.uniform(91.5, 97.8), 1),
                        "backup_status": "missing",
                        "last_backup_at": None,
                        "monthly_cost_usd": 240.00,
                        "metadata": {
                            "instance_type": "c6i.2xlarge",
                            "launched_by": "ci-deploy-temp",
                            "security_group": "sg-0f8899aabbccdd",
                        },
                    }
                )

        return resources

    def generate_metrics(
        self,
        resource_id: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Generate multi-day CloudWatch-style metrics with optional anomaly injections."""
        if days < 1:
            raise ValueError("days must be at least 1")

        rng = random.Random(self.seed)
        metrics: list[dict[str, Any]] = []
        end_day = self.reference_time.replace(minute=0, second=0, microsecond=0)

        baseline_profiles: list[dict[str, Any]] = [
            {
                "resource_id": "i-0baseweb01",
                "region": "us-east-1",
                "cpu_base": 34.0,
                "cpu_amp": 5.0,
                "net_in_base": 4_200_000.0,
                "net_out_base": 6_800_000.0,
                "req_base": 120_000,
            },
            {
                "resource_id": "i-0a1b2c3d4e5f60001",
                "region": "us-east-1",
                "cpu_base": 7.0,
                "cpu_amp": 1.2,
                "net_in_base": 350_000.0,
                "net_out_base": 410_000.0,
                "req_base": 3_400,
            },
            {
                "resource_id": "i-0a1b2c3d4e5f60002",
                "region": "us-east-1",
                "cpu_base": 31.0,
                "cpu_amp": 4.5,
                "net_in_base": 5_100_000.0,
                "net_out_base": 9_400_000.0,
                "req_base": 148_500,
            },
            {
                "resource_id": "db-prod-orders-01",
                "region": "us-east-1",
                "cpu_base": 53.0,
                "cpu_amp": 6.0,
                "net_in_base": 2_800_000.0,
                "net_out_base": 3_100_000.0,
                "req_base": 45_000,
            },
        ]

        counter = 1
        for profile in baseline_profiles:
            rid = profile["resource_id"]
            if resource_id is not None and rid != resource_id:
                continue

            for offset in range(days - 1, -1, -1):
                ts = end_day - timedelta(days=offset)
                wave = math.sin((days - offset) * 0.45)
                cpu = max(1.0, min(99.0, profile["cpu_base"] + profile["cpu_amp"] * wave + rng.uniform(-1.5, 1.5)))
                net_in = max(1000.0, profile["net_in_base"] * (1.0 + 0.08 * wave + rng.uniform(-0.05, 0.05)))
                net_out = max(1000.0, profile["net_out_base"] * (1.0 + 0.08 * wave + rng.uniform(-0.05, 0.05)))
                reqs = max(0, int(profile["req_base"] * (1.0 + 0.07 * wave + rng.uniform(-0.04, 0.04))))

                is_anomalous = False
                # Inject bot traffic surge on public-catalog-web in the most recent day.
                if self.include_anomalies and rid == "i-0a1b2c3d4e5f60002" and offset == 0:
                    ts = self.reference_time - timedelta(minutes=45)
                    cpu = 91.4
                    net_in = 38_500_000.0
                    net_out = 354_000_000.0
                    reqs = 2_410_000
                    is_anomalous = True

                metrics.append(
                    {
                        "event_id": f"cw-{counter:05d}",
                        "resource_id": rid,
                        "region": profile["region"],
                        "timestamp": _iso(ts),
                        "cpu_utilization": round(cpu, 2),
                        "network_in_bytes": round(net_in, 1),
                        "network_out_bytes": round(net_out, 1),
                        "request_count": reqs,
                        "baseline_cpu_pct": profile["cpu_base"],
                        "is_anomalous": is_anomalous,
                    }
                )
                counter += 1

        if self.include_anomalies:
            breach_base = end_day.replace(hour=2, minute=35) - timedelta(hours=0)
            if breach_base > self.reference_time:
                breach_base -= timedelta(days=1)

            for idx, rogue_id in enumerate(_ROGUE_INSTANCE_IDS):
                if resource_id is not None and rogue_id != resource_id:
                    continue
                for step in range(3):
                    ts = breach_base + timedelta(minutes=step * 10 + idx)
                    metrics.append(
                        {
                            "event_id": f"cw-rogue-{idx + 1:02d}-{step + 1}",
                            "resource_id": rogue_id,
                            "region": "ap-southeast-1",
                            "timestamp": _iso(ts),
                            "cpu_utilization": round(rng.uniform(92.0, 97.8), 2),
                            "network_in_bytes": round(rng.uniform(14_000_000.0, 22_000_000.0), 1),
                            "network_out_bytes": round(rng.uniform(85_000_000.0, 128_000_000.0), 1),
                            "request_count": rng.randint(150, 420),
                            "baseline_cpu_pct": 12.0,
                            "is_anomalous": True,
                        }
                    )

        metrics.sort(key=lambda item: (item["timestamp"], item["resource_id"]))
        return metrics

    def generate_cloudtrail_events(self) -> list[dict[str, Any]]:
        """Generate routine baseline IAM events plus off-hours breach activity."""
        anchor = self.reference_time
        events: list[dict[str, Any]] = [
            {
                "event_id": "ct-1001",
                "timestamp": _iso(anchor - timedelta(hours=18)),
                "event_name": "ConsoleLogin",
                "region": "us-east-1",
                "principal": "ops-lead",
                "resource_id": "i-0baseweb01",
                "resource_ids": ["i-0baseweb01"],
                "source_ip": "203.0.113.14",
                "is_anomalous": False,
                "risk_hint": 0.12,
                "metadata": {"eventSource": "signin.amazonaws.com", "mfaUsed": "Yes"},
            },
            {
                "event_id": "ct-1002",
                "timestamp": _iso(anchor - timedelta(hours=14)),
                "event_name": "DescribeInstances",
                "region": "us-east-1",
                "principal": "monitoring-ro",
                "resource_id": "i-0a1b2c3d4e5f60001",
                "resource_ids": ["i-0a1b2c3d4e5f60001"],
                "source_ip": "10.20.4.18",
                "is_anomalous": False,
                "risk_hint": 0.05,
                "metadata": {"eventSource": "ec2.amazonaws.com", "readOnly": True},
            },
            {
                "event_id": "ct-1003",
                "timestamp": _iso(anchor - timedelta(hours=9)),
                "event_name": "CreateSnapshot",
                "region": "us-east-1",
                "principal": "aws-backup-service",
                "resource_id": "i-0baseweb01",
                "resource_ids": ["i-0baseweb01"],
                "source_ip": "backup.amazonaws.com",
                "is_anomalous": False,
                "risk_hint": 0.08,
                "metadata": {"eventSource": "ec2.amazonaws.com"},
            },
        ]

        if self.include_anomalies:
            breach_start = anchor.replace(hour=2, minute=14, second=0, microsecond=0)
            if breach_start > anchor:
                breach_start -= timedelta(days=1)

            events.extend(
                [
                    {
                        "event_id": "ct-9001",
                        "timestamp": _iso(breach_start),
                        "event_name": "ConsoleLogin",
                        "region": "ap-southeast-1",
                        "principal": "ci-deploy-temp",
                        "resource_id": None,
                        "resource_ids": [],
                        "source_ip": "185.220.101.42",
                        "is_anomalous": True,
                        "risk_hint": 0.92,
                        "metadata": {
                            "eventSource": "signin.amazonaws.com",
                            "mfaUsed": "No",
                            "reason": "off_hours_unseen_region_login",
                        },
                    },
                    {
                        "event_id": "ct-9002",
                        "timestamp": _iso(breach_start + timedelta(minutes=5)),
                        "event_name": "AuthorizeSecurityGroupIngress",
                        "region": "ap-southeast-1",
                        "principal": "ci-deploy-temp",
                        "resource_id": "sg-0f8899aabbccdd",
                        "resource_ids": ["sg-0f8899aabbccdd"],
                        "source_ip": "185.220.101.42",
                        "is_anomalous": True,
                        "risk_hint": 0.88,
                        "metadata": {
                            "eventSource": "ec2.amazonaws.com",
                            "cidrIp": "0.0.0.0/0",
                            "toPort": 443,
                        },
                    },
                    {
                        "event_id": "ct-9003",
                        "timestamp": _iso(breach_start + timedelta(minutes=9)),
                        "event_name": "RunInstances",
                        "region": "ap-southeast-1",
                        "principal": "ci-deploy-temp",
                        "resource_id": _ROGUE_INSTANCE_IDS[0],
                        "resource_ids": list(_ROGUE_INSTANCE_IDS),
                        "source_ip": "185.220.101.42",
                        "is_anomalous": True,
                        "risk_hint": 0.95,
                        "metadata": {
                            "eventSource": "ec2.amazonaws.com",
                            "instanceCount": len(_ROGUE_INSTANCE_IDS),
                            "instanceType": "c6i.2xlarge",
                        },
                    },
                    {
                        "event_id": "ct-9004",
                        "timestamp": _iso(anchor - timedelta(hours=6)),
                        "event_name": "ModifyDBInstance",
                        "region": "us-east-1",
                        "principal": "ops-maintenance",
                        "resource_id": "db-prod-orders-01",
                        "resource_ids": ["db-prod-orders-01"],
                        "source_ip": "203.0.113.29",
                        "is_anomalous": True,
                        "risk_hint": 0.65,
                        "metadata": {
                            "eventSource": "rds.amazonaws.com",
                            "backupRetentionPeriod": 0,
                        },
                    },
                ]
            )

        events.sort(key=lambda item: item["timestamp"])
        return events

    def generate_traffic_logs(self) -> list[dict[str, Any]]:
        """Generate application traffic logs including repetitive 2.4M-scale bot scraping."""
        anchor = self.reference_time
        logs: list[dict[str, Any]] = [
            {
                "log_id": "tr-1001",
                "timestamp": _iso(anchor - timedelta(hours=4)),
                "resource_id": "i-0baseweb01",
                "region": "us-east-1",
                "endpoint": "/api/orders/status",
                "method": "GET",
                "request_count": 48_200,
                "bot_requests": 1_200,
                "bot_share_pct": 2.49,
                "bot_flagged": False,
                "avg_cpu_pct": 33.8,
                "network_out_gb": 4.1,
                "top_user_agent": "Mozilla/5.0",
                "source_ips_count": 640,
                "pattern_reason": "Normal authenticated user traffic",
            },
            {
                "log_id": "tr-1002",
                "timestamp": _iso(anchor - timedelta(hours=3)),
                "resource_id": "i-0a1b2c3d4e5f60002",
                "region": "us-east-1",
                "endpoint": "/api/products/featured",
                "method": "GET",
                "request_count": 93_800,
                "bot_requests": 6_400,
                "bot_share_pct": 6.82,
                "bot_flagged": False,
                "avg_cpu_pct": 30.5,
                "network_out_gb": 7.9,
                "top_user_agent": "Mozilla/5.0",
                "source_ips_count": 1_120,
                "pattern_reason": "Normal storefront browsing",
            },
        ]

        if self.include_anomalies:
            logs.extend(
                [
                    {
                        "log_id": "tr-9001",
                        "timestamp": _iso(anchor - timedelta(hours=2)),
                        "resource_id": "i-0a1b2c3d4e5f60002",
                        "region": "us-east-1",
                        "endpoint": "/api/catalog/export",
                        "method": "GET",
                        "request_count": 1_380_000,
                        "bot_requests": 1_330_320,
                        "bot_share_pct": 96.4,
                        "bot_flagged": True,
                        "avg_cpu_pct": 91.4,
                        "network_out_gb": 198.4,
                        "top_user_agent": "python-requests/2.31.0",
                        "source_ips_count": 19,
                        "pattern_reason": "High-frequency sequential pagination without session cookies",
                    },
                    {
                        "log_id": "tr-9002",
                        "timestamp": _iso(anchor - timedelta(hours=1, minutes=30)),
                        "resource_id": "i-0a1b2c3d4e5f60002",
                        "region": "us-east-1",
                        "endpoint": "/api/pricing/search",
                        "method": "GET",
                        "request_count": 745_000,
                        "bot_requests": 683_910,
                        "bot_share_pct": 91.8,
                        "bot_flagged": True,
                        "avg_cpu_pct": 89.2,
                        "network_out_gb": 112.6,
                        "top_user_agent": "Go-http-client/2.0",
                        "source_ips_count": 16,
                        "pattern_reason": "Uniform 40ms request cadence across rotating ASN IPs",
                    },
                    {
                        "log_id": "tr-9003",
                        "timestamp": _iso(anchor - timedelta(hours=1)),
                        "resource_id": "i-0a1b2c3d4e5f60002",
                        "region": "us-east-1",
                        "endpoint": "/auth/login",
                        "method": "POST",
                        "request_count": 143_000,
                        "bot_requests": 120_406,
                        "bot_share_pct": 84.2,
                        "bot_flagged": True,
                        "avg_cpu_pct": 84.7,
                        "network_out_gb": 31.0,
                        "top_user_agent": "curl/8.5.0",
                        "source_ips_count": 12,
                        "pattern_reason": "Credential-stuffing burst with elevated 401 failure ratio",
                    },
                ]
            )

        logs.sort(key=lambda item: item["timestamp"])
        return logs

    def generate_cost_usage(self, days: int = 30) -> list[dict[str, Any]]:
        """Generate daily Cost Explorer records with compute and egress cost spikes."""
        if days < 1:
            raise ValueError("days must be at least 1")

        rng = random.Random(self.seed + 303)
        records: list[dict[str, Any]] = []
        end_day = self.reference_time.replace(hour=0, minute=0, second=0, microsecond=0)

        service_baselines: list[dict[str, Any]] = [
            {
                "service": "AmazonEC2",
                "baseline_usd": 20.30,
                "resource_id": "i-0baseweb01",
                "region": "us-east-1",
            },
            {
                "service": "AmazonRDS",
                "baseline_usd": 13.75,
                "resource_id": "db-prod-orders-01",
                "region": "us-east-1",
            },
            {
                "service": "AmazonS3",
                "baseline_usd": 5.90,
                "resource_id": "s3-awsense-audit-logs",
                "region": "us-east-1",
            },
            {
                "service": "AmazonEBS",
                "baseline_usd": 1.60,
                "resource_id": "vol-09911223344556677",
                "region": "us-east-1",
            },
            {
                "service": "AWSDataTransfer",
                "baseline_usd": 6.45,
                "resource_id": "i-0a1b2c3d4e5f60002",
                "region": "us-east-1",
            },
        ]

        counter = 1
        for offset in range(days - 1, -1, -1):
            day_dt = end_day - timedelta(days=offset)
            day_str = day_dt.strftime("%Y-%m-%d")
            ts = _iso(day_dt.replace(hour=3, minute=0))

            for entry in service_baselines:
                base = entry["baseline_usd"]
                cost = round(max(0.1, base * (1.0 + rng.uniform(-0.04, 0.04))), 2)
                delta = round(max(0.0, cost - base), 2)
                delta_pct = round((delta / base) * 100.0, 1) if base > 0 else 0.0
                is_anomalous = False
                record_region = entry["region"]
                record_resource = entry["resource_id"]

                # Inject bot-driven egress spike on most recent day.
                if self.include_anomalies and offset == 0 and entry["service"] == "AWSDataTransfer":
                    ts = _iso(self.reference_time - timedelta(minutes=15))
                    delta = 138.20
                    cost = round(base + delta, 2)
                    delta_pct = round((delta / base) * 100.0, 1)
                    is_anomalous = True

                records.append(
                    {
                        "event_id": f"ce-{counter:05d}",
                        "date": day_str,
                        "timestamp": ts,
                        "service": entry["service"],
                        "resource_id": record_resource,
                        "region": record_region,
                        "cost_usd": cost,
                        "baseline_usd": base,
                        "delta_usd": delta,
                        "delta_pct": delta_pct,
                        "is_anomalous": is_anomalous,
                    }
                )
                counter += 1

        if self.include_anomalies:
            breach_ts = self.reference_time.replace(hour=2, minute=50, second=0, microsecond=0)
            if breach_ts > self.reference_time:
                breach_ts -= timedelta(days=1)

            records.append(
                {
                    "event_id": "ce-90001",
                    "date": breach_ts.strftime("%Y-%m-%d"),
                    "timestamp": _iso(breach_ts),
                    "service": "AmazonEC2",
                    "resource_id": _ROGUE_INSTANCE_IDS[0],
                    "region": "ap-southeast-1",
                    "cost_usd": 485.50,
                    "baseline_usd": 65.00,
                    "delta_usd": 420.50,
                    "delta_pct": 646.9,
                    "is_anomalous": True,
                }
            )

        return records


class MockTelemetryProvider(TelemetryProvider):
    """TelemetryProvider implementation backed by MockTelemetryGenerator."""

    source_name: str = "mock"

    def __init__(
        self,
        *,
        seed: int = 42,
        reference_time: datetime | None = None,
        include_anomalies: bool = True,
    ) -> None:
        self._generator = MockTelemetryGenerator(
            seed=seed,
            reference_time=reference_time,
            include_anomalies=include_anomalies,
        )

    def get_resources(self) -> list[dict[str, Any]]:
        return self._generator.generate_resources()

    def get_metrics(
        self,
        resource_id: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        return self._generator.generate_metrics(resource_id=resource_id, days=days)

    def get_cloudtrail_events(self) -> list[dict[str, Any]]:
        return self._generator.generate_cloudtrail_events()

    def get_traffic_logs(self) -> list[dict[str, Any]]:
        return self._generator.generate_traffic_logs()

    def get_cost_usage(self, days: int = 30) -> list[dict[str, Any]]:
        return self._generator.generate_cost_usage(days=days)


def generate_full_snapshot(
    *,
    seed: int = 42,
    include_anomalies: bool = True,
    days: int = 30,
) -> dict[str, Any]:
    """Build a complete JSON-serializable telemetry bundle across all five provider methods."""
    provider = MockTelemetryProvider(seed=seed, include_anomalies=include_anomalies)
    return {
        "source": provider.source_name,
        "include_anomalies": include_anomalies,
        "resources": provider.get_resources(),
        "metrics": provider.get_metrics(days=days),
        "cloudtrail_events": provider.get_cloudtrail_events(),
        "traffic_logs": provider.get_traffic_logs(),
        "cost_usage": provider.get_cost_usage(days=days),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mock AWS telemetry JSON.")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic PRNG seed.")
    parser.add_argument("--days", type=int, default=30, help="Number of historical days.")
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Emit clean baseline data without injected anomalies.",
    )
    args = parser.parse_args()

    snapshot = generate_full_snapshot(
        seed=args.seed,
        include_anomalies=not args.baseline_only,
        days=args.days,
    )
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
