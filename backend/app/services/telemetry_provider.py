"""Telemetry provider interface, live AWS boto3 collectors, and provider factory."""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

_EC2_MONTHLY_COST_ESTIMATES_USD: dict[str, float] = {
    "t3.micro": 7.59,
    "t3.small": 15.18,
    "t3.medium": 30.37,
    "t3.large": 60.74,
    "t3.xlarge": 121.47,
    "m5.large": 70.08,
    "m5.xlarge": 140.16,
    "c6i.large": 62.05,
    "c6i.xlarge": 124.10,
    "c6i.2xlarge": 248.20,
    "g5.2xlarge": 884.76,
}

_EBS_GB_MONTHLY_USD: dict[str, float] = {
    "gp3": 0.08,
    "gp2": 0.10,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
    "standard": 0.05,
}

_SENSITIVE_CLOUDTRAIL_ACTIONS: dict[str, float] = {
    "ConsoleLogin": 0.55,
    "CreateAccessKey": 0.85,
    "CreateUser": 0.80,
    "AttachUserPolicy": 0.85,
    "AttachRolePolicy": 0.85,
    "PutUserPolicy": 0.85,
    "PutRolePolicy": 0.85,
    "AssumeRole": 0.45,
    "AuthorizeSecurityGroupIngress": 0.82,
    "RunInstances": 0.78,
    "StopLogging": 0.95,
    "DeleteTrail": 0.95,
    "ModifyDBInstance": 0.65,
    "PutBucketPolicy": 0.75,
    "PutBucketPublicAccessBlock": 0.70,
}


def _utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """Format a datetime as an ISO-8601 UTC Z string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tag_value(tags: list[dict[str, Any]] | None, key: str) -> str | None:
    """Extract a tag value from AWS Tag list by exact key."""
    if not tags:
        return None
    for tag in tags:
        if tag.get("Key") == key:
            value = tag.get("Value")
            return str(value) if value is not None else None
    return None


def _tags_dict(tags: list[dict[str, Any]] | None) -> dict[str, str]:
    """Convert AWS Tag list into a flat string dict."""
    if not tags:
        return {}
    return {
        str(tag["Key"]): str(tag.get("Value", ""))
        for tag in tags
        if tag.get("Key") is not None
    }


def _region_from_az(az: str | None, fallback: str) -> str:
    """Derive AWS region from an AvailabilityZone like 'us-east-1a'."""
    if az and len(az) > 1 and az[-1].isalpha():
        return az[:-1]
    return fallback


class TelemetryProvider(ABC):
    """Abstract data-ingestion interface decoupling analysis from AWS/mock sources."""

    source_name: str = "base"

    @abstractmethod
    def get_resources(self) -> list[dict[str, Any]]:
        """Return inventory records for monitored AWS resources (EC2, EBS, RDS, S3)."""

    @abstractmethod
    def get_metrics(
        self,
        resource_id: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Return time-series CloudWatch utilization and request metrics."""

    @abstractmethod
    def get_cloudtrail_events(self) -> list[dict[str, Any]]:
        """Return normalized CloudTrail API and IAM audit events."""

    @abstractmethod
    def get_traffic_logs(self) -> list[dict[str, Any]]:
        """Return application/network traffic telemetry and bot-indicator records."""

    @abstractmethod
    def get_cost_usage(self, days: int = 30) -> list[dict[str, Any]]:
        """Return Cost Explorer daily service spend and cost anomaly records."""


class Boto3TelemetryProvider(TelemetryProvider):
    """Read-only AWS SDK telemetry collector matching MockTelemetryProvider schemas."""

    source_name: str = "aws"

    def __init__(
        self,
        region_name: str | None = None,
        profile_name: str | None = None,
        *,
        session: boto3.Session | None = None,
        clients: dict[str, Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self.profile_name = profile_name or os.getenv("AWS_PROFILE")
        self._session: boto3.Session | None = session
        self._clients: dict[str, Any] = dict(clients) if clients else {}
        self._clock: Callable[[], datetime] = clock or _utc_now

    def get_session(self) -> boto3.Session:
        """Lazily create a boto3 session configured for the target region/profile."""
        if self._session is None:
            session_kwargs: dict[str, str] = {"region_name": self.region_name}
            if self.profile_name:
                session_kwargs["profile_name"] = self.profile_name
            self._session = boto3.Session(**session_kwargs)
        return self._session

    def get_client(self, service_name: str) -> Any:
        """Return a cached boto3 client, using us-east-1 for global Cost Explorer."""
        if service_name not in self._clients:
            session = self.get_session()
            if service_name == "ce":
                self._clients[service_name] = session.client(service_name, region_name="us-east-1")
            else:
                self._clients[service_name] = session.client(
                    service_name,
                    region_name=self.region_name,
                )
        return self._clients[service_name]

    def _now(self) -> datetime:
        dt = self._clock()
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

    def _collect_ec2_instances(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        try:
            ec2 = self.get_client("ec2")
            next_token: str | None = None
            while True:
                kwargs: dict[str, Any] = {"NextToken": next_token} if next_token else {}
                resp = ec2.describe_instances(**kwargs)
                for reservation in resp.get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        instance_id = str(inst["InstanceId"])
                        tags = inst.get("Tags")
                        tag_map = _tags_dict(tags)
                        instance_type = str(inst.get("InstanceType", "unknown"))
                        az = inst.get("Placement", {}).get("AvailabilityZone")
                        state_name = str(inst.get("State", {}).get("Name", "unknown"))
                        backup_tag = str(tag_map.get("Backup", "")).strip().lower()
                        backup_status = (
                            "protected"
                            if backup_tag in {"true", "yes", "enabled", "daily"}
                            else "not_applicable"
                        )
                        launch_time = inst.get("LaunchTime")
                        resources.append(
                            {
                                "resource_id": instance_id,
                                "name": _tag_value(tags, "Name") or instance_id,
                                "resource_type": "ec2",
                                "region": _region_from_az(az, self.region_name),
                                "status": state_name,
                                "utilization_pct": 0.0,
                                "backup_status": backup_status,
                                "last_backup_at": None,
                                "monthly_cost_usd": _EC2_MONTHLY_COST_ESTIMATES_USD.get(
                                    instance_type, 75.0
                                ),
                                "metadata": {
                                    "instance_type": instance_type,
                                    "availability_zone": az,
                                    "state": state_name,
                                    "tags": tag_map,
                                    "launch_time": (
                                        _iso(launch_time)
                                        if isinstance(launch_time, datetime)
                                        else None
                                    ),
                                },
                            }
                        )
                next_token = resp.get("NextToken")
                if not next_token:
                    break
        except (ClientError, BotoCoreError) as exc:
            logger.warning("EC2 instance collection failed: %s", exc)
        return resources

    def _collect_ebs_volumes(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        try:
            ec2 = self.get_client("ec2")
            next_token: str | None = None
            while True:
                kwargs: dict[str, Any] = {"NextToken": next_token} if next_token else {}
                resp = ec2.describe_volumes(**kwargs)
                for vol in resp.get("Volumes", []):
                    volume_id = str(vol["VolumeId"])
                    tags = vol.get("Tags")
                    volume_type = str(vol.get("VolumeType", "gp3"))
                    size_gb = int(vol.get("Size", 0))
                    attachments = vol.get("Attachments") or []
                    snapshot_id = str(vol.get("SnapshotId") or "")
                    az = vol.get("AvailabilityZone")
                    rate = _EBS_GB_MONTHLY_USD.get(volume_type, 0.08)
                    resources.append(
                        {
                            "resource_id": volume_id,
                            "name": _tag_value(tags, "Name") or volume_id,
                            "resource_type": "ebs",
                            "region": _region_from_az(az, self.region_name),
                            "status": str(vol.get("State", "unknown")),
                            "utilization_pct": 0.0,
                            "backup_status": "protected" if snapshot_id else "missing",
                            "last_backup_at": None,
                            "monthly_cost_usd": round(size_gb * rate, 2),
                            "metadata": {
                                "volume_type": volume_type,
                                "size_gb": size_gb,
                                "attached": bool(attachments),
                                "snapshot_id": snapshot_id or None,
                                "encrypted": bool(vol.get("Encrypted", False)),
                            },
                        }
                    )
                next_token = resp.get("NextToken")
                if not next_token:
                    break
        except (ClientError, BotoCoreError) as exc:
            logger.warning("EBS volume collection failed: %s", exc)
        return resources

    def _collect_rds_instances(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        now = self._now()
        try:
            rds = self.get_client("rds")
            marker: str | None = None
            while True:
                kwargs: dict[str, Any] = {"Marker": marker} if marker else {}
                resp = rds.describe_db_instances(**kwargs)
                for db in resp.get("DBInstances", []):
                    db_id = str(db["DBInstanceIdentifier"])
                    retention = int(db.get("BackupRetentionPeriod", 0) or 0)
                    latest_restore = db.get("LatestRestorableTime")
                    last_backup_at: str | None = None

                    if retention <= 0:
                        backup_status = "missing"
                    elif isinstance(latest_restore, datetime):
                        restore_utc = (
                            latest_restore.replace(tzinfo=timezone.utc)
                            if latest_restore.tzinfo is None
                            else latest_restore.astimezone(timezone.utc)
                        )
                        last_backup_at = _iso(restore_utc)
                        backup_status = (
                            "outdated" if (now - restore_utc) > timedelta(days=7) else "protected"
                        )
                    else:
                        backup_status = "protected"

                    az = db.get("AvailabilityZone")
                    resources.append(
                        {
                            "resource_id": db_id,
                            "name": db_id,
                            "resource_type": "rds",
                            "region": _region_from_az(az, self.region_name),
                            "status": str(db.get("DBInstanceStatus", "unknown")),
                            "utilization_pct": 0.0,
                            "backup_status": backup_status,
                            "last_backup_at": last_backup_at,
                            "monthly_cost_usd": 180.0,
                            "metadata": {
                                "engine": str(db.get("Engine", "unknown")),
                                "instance_class": str(db.get("DBInstanceClass", "unknown")),
                                "multi_az": bool(db.get("MultiAZ", False)),
                                "backup_retention_days": retention,
                                "storage_encrypted": bool(db.get("StorageEncrypted", False)),
                            },
                        }
                    )
                marker = resp.get("Marker")
                if not marker:
                    break
        except (ClientError, BotoCoreError) as exc:
            logger.warning("RDS instance collection failed: %s", exc)
        return resources

    def _collect_s3_buckets(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        try:
            s3 = self.get_client("s3")
            resp = s3.list_buckets()
            for bucket in resp.get("Buckets", []):
                name = str(bucket["Name"])
                created = bucket.get("CreationDate")
                resources.append(
                    {
                        "resource_id": name,
                        "name": name,
                        "resource_type": "s3",
                        "region": self.region_name,
                        "status": "active",
                        "utilization_pct": 0.0,
                        "backup_status": "not_applicable",
                        "last_backup_at": None,
                        "monthly_cost_usd": 0.0,
                        "metadata": {
                            "created_at": _iso(created) if isinstance(created, datetime) else None,
                        },
                    }
                )
        except (ClientError, BotoCoreError) as exc:
            logger.warning("S3 bucket collection failed: %s", exc)
        return resources

    def get_resources(self) -> list[dict[str, Any]]:
        """Collect normalized EC2, EBS, RDS, and S3 inventory via AWS SDK."""
        return [
            *self._collect_ec2_instances(),
            *self._collect_ebs_volumes(),
            *self._collect_rds_instances(),
            *self._collect_s3_buckets(),
        ]

    def _fetch_metric_data(
        self,
        queries: list[dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, dict[datetime, float]]:
        """Execute CloudWatch GetMetricData with NextToken pagination."""
        cw = self.get_client("cloudwatch")
        series: dict[str, dict[datetime, float]] = {}
        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "MetricDataQueries": queries,
                "StartTime": start_time,
                "EndTime": end_time,
            }
            if next_token:
                kwargs["NextToken"] = next_token
            resp = cw.get_metric_data(**kwargs)
            for result in resp.get("MetricDataResults", []):
                qid = str(result["Id"])
                buckets = series.setdefault(qid, {})
                for ts, val in zip(
                    result.get("Timestamps", []),
                    result.get("Values", []),
                ):
                    if isinstance(ts, datetime):
                        ts_utc = (
                            ts.replace(tzinfo=timezone.utc)
                            if ts.tzinfo is None
                            else ts.astimezone(timezone.utc)
                        )
                        buckets[ts_utc] = float(val)
            next_token = resp.get("NextToken")
            if not next_token:
                break
        return series

    def get_metrics(
        self,
        resource_id: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Query CloudWatch CPUUtilization, NetworkIn, and NetworkOut over the day window."""
        if days < 1:
            raise ValueError("days must be at least 1")

        if resource_id is not None:
            target_ids = [resource_id]
        else:
            target_ids = [item["resource_id"] for item in self._collect_ec2_instances()]

        if not target_ids:
            return []

        end_time = self._now()
        start_time = end_time - timedelta(days=days)
        period = 3600 if days <= 3 else 86400

        queries: list[dict[str, Any]] = []
        id_map: dict[str, tuple[str, str]] = {}
        for idx, rid in enumerate(target_ids):
            for key, metric_name in (
                ("cpu", "CPUUtilization"),
                ("netin", "NetworkIn"),
                ("netout", "NetworkOut"),
            ):
                qid = f"{key}_{idx}"
                id_map[qid] = (rid, key)
                queries.append(
                    {
                        "Id": qid,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/EC2",
                                "MetricName": metric_name,
                                "Dimensions": [{"Name": "InstanceId", "Value": rid}],
                            },
                            "Period": period,
                            "Stat": "Average",
                        },
                        "ReturnData": True,
                    }
                )

        try:
            raw_series: dict[str, dict[datetime, float]] = {}
            for chunk_start in range(0, len(queries), 100):
                chunk = queries[chunk_start : chunk_start + 100]
                raw_series.update(self._fetch_metric_data(chunk, start_time, end_time))
        except (ClientError, BotoCoreError) as exc:
            logger.warning("CloudWatch metric collection failed: %s", exc)
            return []

        pivoted: dict[tuple[str, datetime], dict[str, float]] = {}
        cpu_by_resource: dict[str, list[float]] = {}
        for qid, points in raw_series.items():
            rid, field_key = id_map[qid]
            for ts, val in points.items():
                bucket = pivoted.setdefault((rid, ts), {"cpu": 0.0, "netin": 0.0, "netout": 0.0})
                bucket[field_key] = val
                if field_key == "cpu":
                    cpu_by_resource.setdefault(rid, []).append(val)

        baselines = {
            rid: round(float(median(vals)), 2) if vals else 0.0
            for rid, vals in cpu_by_resource.items()
        }

        metrics: list[dict[str, Any]] = []
        for counter, ((rid, ts), vals) in enumerate(
            sorted(pivoted.items(), key=lambda entry: (entry[0][1], entry[0][0])),
            start=1,
        ):
            cpu = round(vals["cpu"], 2)
            baseline = baselines.get(rid, 0.0)
            is_anomalous = cpu >= 85.0 or (baseline > 0.0 and cpu >= baseline * 2.5 and cpu >= 50.0)
            metrics.append(
                {
                    "event_id": f"cw-{counter:05d}",
                    "resource_id": rid,
                    "region": self.region_name,
                    "timestamp": _iso(ts),
                    "cpu_utilization": cpu,
                    "network_in_bytes": round(vals["netin"], 1),
                    "network_out_bytes": round(vals["netout"], 1),
                    "request_count": 0,
                    "baseline_cpu_pct": baseline,
                    "is_anomalous": is_anomalous,
                }
            )
        return metrics

    def get_cloudtrail_events(self) -> list[dict[str, Any]]:
        """Query CloudTrail LookupEvents over the last 24h and flag sensitive/off-hours calls."""
        end_time = self._now()
        start_time = end_time - timedelta(hours=24)
        events: list[dict[str, Any]] = []

        try:
            ct = self.get_client("cloudtrail")
            next_token: str | None = None
            for _ in range(5):
                kwargs: dict[str, Any] = {
                    "StartTime": start_time,
                    "EndTime": end_time,
                    "MaxResults": 50,
                }
                if next_token:
                    kwargs["NextToken"] = next_token
                resp = ct.lookup_events(**kwargs)
                for raw_ev in resp.get("Events", []):
                    event_name = str(raw_ev.get("EventName", "Unknown"))
                    event_time = raw_ev.get("EventTime")
                    ts_utc = (
                        event_time.replace(tzinfo=timezone.utc)
                        if isinstance(event_time, datetime) and event_time.tzinfo is None
                        else event_time.astimezone(timezone.utc)
                        if isinstance(event_time, datetime)
                        else end_time
                    )

                    detail: dict[str, Any] = {}
                    raw_json = raw_ev.get("CloudTrailEvent")
                    if isinstance(raw_json, str) and raw_json.strip():
                        try:
                            detail = json.loads(raw_json)
                        except json.JSONDecodeError:
                            detail = {}

                    resource_ids = [
                        str(res["ResourceName"])
                        for res in raw_ev.get("Resources", [])
                        if res.get("ResourceName")
                    ]
                    source_ip = detail.get("sourceIPAddress")
                    region = str(detail.get("awsRegion") or self.region_name)
                    user_identity = detail.get("userIdentity") or {}
                    principal = str(
                        raw_ev.get("Username")
                        or user_identity.get("userName")
                        or user_identity.get("arn")
                        or "unknown"
                    )
                    mfa_used = (detail.get("additionalEventData") or {}).get("MFAUsed")
                    off_hours = ts_utc.hour < 6 or ts_utc.hour >= 22

                    base_risk = _SENSITIVE_CLOUDTRAIL_ACTIONS.get(event_name, 0.10)
                    risk_hint = base_risk
                    if off_hours and event_name in _SENSITIVE_CLOUDTRAIL_ACTIONS:
                        risk_hint = min(1.0, risk_hint + 0.20)
                    if event_name == "ConsoleLogin" and str(mfa_used).lower() == "no":
                        risk_hint = max(risk_hint, 0.90)

                    is_anomalous = (
                        event_name in _SENSITIVE_CLOUDTRAIL_ACTIONS
                        and (off_hours or base_risk >= 0.75 or str(mfa_used).lower() == "no")
                    )

                    events.append(
                        {
                            "event_id": str(raw_ev.get("EventId", "")),
                            "timestamp": _iso(ts_utc),
                            "event_name": event_name,
                            "region": region,
                            "principal": principal,
                            "resource_id": resource_ids[0] if resource_ids else None,
                            "resource_ids": resource_ids,
                            "source_ip": str(source_ip) if source_ip else None,
                            "is_anomalous": is_anomalous,
                            "risk_hint": round(risk_hint, 2),
                            "metadata": {
                                "eventSource": raw_ev.get("EventSource")
                                or detail.get("eventSource"),
                                "readOnly": raw_ev.get("ReadOnly"),
                                "mfaUsed": mfa_used,
                                "offHours": off_hours,
                            },
                        }
                    )
                next_token = resp.get("NextToken")
                if not next_token:
                    break
        except (ClientError, BotoCoreError) as exc:
            logger.warning("CloudTrail lookup failed: %s", exc)
            return []

        events.sort(key=lambda item: item["timestamp"])
        return events

    def get_cost_usage(self, days: int = 30) -> list[dict[str, Any]]:
        """Query Cost Explorer daily UnblendedCost grouped by AWS SERVICE."""
        if days < 1:
            raise ValueError("days must be at least 1")

        end_day = self._now().date() + timedelta(days=1)
        start_day = end_day - timedelta(days=days)
        raw_rows: list[tuple[str, str, float]] = []

        try:
            ce = self.get_client("ce")
            next_token: str | None = None
            while True:
                kwargs: dict[str, Any] = {
                    "TimePeriod": {
                        "Start": start_day.strftime("%Y-%m-%d"),
                        "End": end_day.strftime("%Y-%m-%d"),
                    },
                    "Granularity": "DAILY",
                    "Metrics": ["UnblendedCost"],
                    "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
                }
                if next_token:
                    kwargs["NextPageToken"] = next_token
                resp = ce.get_cost_and_usage(**kwargs)
                for period in resp.get("ResultsByTime", []):
                    day_str = str(period.get("TimePeriod", {}).get("Start", ""))
                    for group in period.get("Groups", []):
                        keys = group.get("Keys") or ["UnknownService"]
                        service = str(keys[0])
                        amount_str = (
                            group.get("Metrics", {})
                            .get("UnblendedCost", {})
                            .get("Amount", "0")
                        )
                        raw_rows.append((day_str, service, float(amount_str)))
                next_token = resp.get("NextPageToken")
                if not next_token:
                    break
        except (ClientError, BotoCoreError) as exc:
            logger.warning("Cost Explorer collection failed: %s", exc)
            return []

        costs_by_service: dict[str, list[float]] = {}
        for _, service, amount in raw_rows:
            costs_by_service.setdefault(service, []).append(amount)

        baselines = {
            service: round(float(median(vals)), 2) if vals else 0.0
            for service, vals in costs_by_service.items()
        }

        records: list[dict[str, Any]] = []
        for idx, (day_str, service, amount) in enumerate(raw_rows, start=1):
            cost_usd = round(amount, 2)
            base_usd = baselines.get(service, 0.0)
            delta_usd = round(max(0.0, cost_usd - base_usd), 2)
            delta_pct = (
                round((delta_usd / base_usd) * 100.0, 1)
                if base_usd > 0.0
                else (100.0 if delta_usd > 0.0 else 0.0)
            )
            is_anomalous = (delta_usd >= 20.0 and delta_pct >= 50.0) or (
                base_usd == 0.0 and delta_usd >= 50.0
            )
            records.append(
                {
                    "event_id": f"ce-{idx:05d}",
                    "date": day_str,
                    "timestamp": f"{day_str}T03:00:00Z" if day_str else _iso(self._now()),
                    "service": service,
                    "resource_id": None,
                    "region": self.region_name,
                    "cost_usd": cost_usd,
                    "baseline_usd": base_usd,
                    "delta_usd": delta_usd,
                    "delta_pct": delta_pct,
                    "is_anomalous": is_anomalous,
                }
            )
        return records

    def get_traffic_logs(self) -> list[dict[str, Any]]:
        """Query ALB or WAFv2 CloudWatch request metrics, returning [] when absent."""
        end_time = self._now()
        start_time = end_time - timedelta(hours=24)

        try:
            cw = self.get_client("cloudwatch")
            alb_metrics = cw.list_metrics(
                Namespace="AWS/ApplicationELB",
                MetricName="RequestCount",
            ).get("Metrics", [])

            if alb_metrics:
                return self._collect_alb_traffic(alb_metrics, start_time, end_time)

            waf_metrics = cw.list_metrics(
                Namespace="AWS/WAFV2",
                MetricName="AllowedRequests",
            ).get("Metrics", [])

            if waf_metrics:
                return self._collect_waf_traffic(waf_metrics, start_time, end_time)

            return []
        except (ClientError, BotoCoreError) as exc:
            logger.warning("Traffic log collection failed: %s", exc)
            return []

    def _collect_alb_traffic(
        self,
        alb_metrics: list[dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        lb_names: dict[int, str] = {}
        for idx, metric in enumerate(alb_metrics[:10]):
            dims = metric.get("Dimensions", [])
            lb_name = next(
                (str(d.get("Value")) for d in dims if d.get("Name") == "LoadBalancer"),
                f"alb-{idx}",
            )
            lb_names[idx] = lb_name
            queries.append(
                {
                    "Id": f"req_{idx}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ApplicationELB",
                            "MetricName": "RequestCount",
                            "Dimensions": dims,
                        },
                        "Period": 3600,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )
            queries.append(
                {
                    "Id": f"bytes_{idx}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ApplicationELB",
                            "MetricName": "ProcessedBytes",
                            "Dimensions": dims,
                        },
                        "Period": 3600,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )

        series = self._fetch_metric_data(queries, start_time, end_time)
        logs: list[dict[str, Any]] = []
        counter = 1
        for idx, lb_name in lb_names.items():
            req_points = series.get(f"req_{idx}", {})
            bytes_points = series.get(f"bytes_{idx}", {})
            req_vals = list(req_points.values())
            baseline_req = float(median(req_vals)) if req_vals else 0.0

            for ts in sorted(set(req_points.keys()) | set(bytes_points.keys())):
                reqs = int(round(req_points.get(ts, 0.0)))
                egress_gb = round(bytes_points.get(ts, 0.0) / (1024**3), 3)
                is_spike = reqs >= 100_000 and (baseline_req == 0.0 or reqs >= baseline_req * 4.0)
                bot_reqs = int(round(reqs * 0.85)) if is_spike else 0
                bot_share = round((bot_reqs / reqs) * 100.0, 2) if reqs > 0 else 0.0
                logs.append(
                    {
                        "log_id": f"tr-alb-{counter:04d}",
                        "timestamp": _iso(ts),
                        "resource_id": lb_name,
                        "region": self.region_name,
                        "endpoint": "/",
                        "method": "GET",
                        "request_count": reqs,
                        "bot_requests": bot_reqs,
                        "bot_share_pct": bot_share,
                        "bot_flagged": is_spike,
                        "avg_cpu_pct": 0.0,
                        "network_out_gb": egress_gb,
                        "top_user_agent": "ALB-Aggregate",
                        "source_ips_count": 0,
                        "pattern_reason": (
                            "Anomalous ALB request spike" if is_spike else "Normal ALB traffic"
                        ),
                    }
                )
                counter += 1
        logs.sort(key=lambda item: item["timestamp"])
        return logs

    def _collect_waf_traffic(
        self,
        waf_metrics: list[dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        acl_names: dict[int, str] = {}
        for idx, metric in enumerate(waf_metrics[:10]):
            dims = metric.get("Dimensions", [])
            acl_name = next(
                (str(d.get("Value")) for d in dims if d.get("Name") == "WebACL"),
                f"waf-{idx}",
            )
            acl_names[idx] = acl_name
            for key, metric_name in (
                ("allowed", "AllowedRequests"),
                ("blocked", "BlockedRequests"),
            ):
                queries.append(
                    {
                        "Id": f"{key}_{idx}",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/WAFV2",
                                "MetricName": metric_name,
                                "Dimensions": dims,
                            },
                            "Period": 3600,
                            "Stat": "Sum",
                        },
                        "ReturnData": True,
                    }
                )

        series = self._fetch_metric_data(queries, start_time, end_time)
        logs: list[dict[str, Any]] = []
        counter = 1
        for idx, acl_name in acl_names.items():
            allowed_pts = series.get(f"allowed_{idx}", {})
            blocked_pts = series.get(f"blocked_{idx}", {})
            for ts in sorted(set(allowed_pts.keys()) | set(blocked_pts.keys())):
                allowed = int(round(allowed_pts.get(ts, 0.0)))
                blocked = int(round(blocked_pts.get(ts, 0.0)))
                total = allowed + blocked
                bot_share = round((blocked / total) * 100.0, 2) if total > 0 else 0.0
                flagged = blocked > 0 and bot_share >= 20.0
                logs.append(
                    {
                        "log_id": f"tr-waf-{counter:04d}",
                        "timestamp": _iso(ts),
                        "resource_id": acl_name,
                        "region": self.region_name,
                        "endpoint": "/",
                        "method": "ANY",
                        "request_count": total,
                        "bot_requests": blocked,
                        "bot_share_pct": bot_share,
                        "bot_flagged": flagged,
                        "avg_cpu_pct": 0.0,
                        "network_out_gb": 0.0,
                        "top_user_agent": "WAFv2-Aggregate",
                        "source_ips_count": 0,
                        "pattern_reason": (
                            "Elevated WAFv2 blocked request share"
                            if flagged
                            else "Normal WAFv2 traffic"
                        ),
                    }
                )
                counter += 1
        logs.sort(key=lambda item: item["timestamp"])
        return logs


def get_telemetry_provider(source: str | None = None) -> TelemetryProvider:
    """Instantiate the configured telemetry provider ('mock' or 'aws')."""
    selected = (source or os.getenv("DATA_SOURCE", "mock")).strip().lower()
    if selected == "mock":
        from app.services.mock_generator import MockTelemetryProvider

        return MockTelemetryProvider()
    if selected == "aws":
        return Boto3TelemetryProvider()
    raise ValueError(f"Unsupported DATA_SOURCE '{selected}'. Expected 'mock' or 'aws'.")
