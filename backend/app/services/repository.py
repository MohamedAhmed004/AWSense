"""Database repository and idempotent mock seeder for AWSense ORM entities."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AlertSeverity,
    AlertStatus,
    BackupStatus,
    CloudResource,
    Recommendation,
    RecommendationCategory,
    RecommendationState,
    ResourceType,
    SecurityAlert,
    TelemetryMetric,
)
from app.services.correlator import correlate_signals, parse_timestamp
from app.services.mock_generator import MockTelemetryProvider
from app.services.telemetry_provider import TelemetryProvider

EnumT = TypeVar("EnumT", bound=StrEnum)


def _utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


def _coerce_enum(enum_cls: type[EnumT], value: EnumT | str | None) -> EnumT | None:
    """Convert optional string/enum values into a validated StrEnum member."""
    if value is None or isinstance(value, enum_cls):
        return value
    return enum_cls(str(value).strip().lower())


def _extract_metric_spikes(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert anomalous multi-metric telemetry records into Correlator MetricSpike dicts."""
    spikes: list[dict[str, Any]] = []
    for row in metrics:
        if not row.get("is_anomalous"):
            continue
        spikes.append(
            {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"],
                "resource_id": row["resource_id"],
                "metric_name": "CPUUtilization",
                "value": float(row.get("cpu_utilization", 0.0)),
                "baseline": float(row.get("baseline_cpu_pct", 0.0)),
                "region": row.get("region"),
            }
        )
        req_count = int(row.get("request_count", 0))
        if req_count >= 1_000_000:
            spikes.append(
                {
                    "event_id": f"{row['event_id']}-req",
                    "timestamp": row["timestamp"],
                    "resource_id": row["resource_id"],
                    "metric_name": "RequestCount",
                    "value": float(req_count),
                    "baseline": 148_500.0,
                    "region": row.get("region"),
                }
            )
    return spikes


def _build_seed_recommendations(
    resources: list[dict[str, Any]],
    traffic_logs: list[dict[str, Any]],
    cost_usage: list[dict[str, Any]],
) -> list[Recommendation]:
    """Derive deterministic optimization, security, and backup recommendations from provider data."""
    recs: list[Recommendation] = []
    counter = 1

    rogue_resources = [
        res
        for res in resources
        if res.get("metadata", {}).get("launched_by") == "ci-deploy-temp"
        and res.get("resource_type") == "ec2"
    ]
    if rogue_resources:
        primary_rogue = rogue_resources[0]
        rogue_savings = round(sum(float(r.get("monthly_cost_usd", 0.0)) for r in rogue_resources), 2)
        recs.append(
            Recommendation(
                recommendation_id=f"rec_{counter:04d}",
                resource_id=primary_rogue["resource_id"],
                category=RecommendationCategory.SECURITY,
                title=f"Quarantine and terminate {len(rogue_resources)} unauthorized EC2 instances",
                action=(
                    f"Revoke ci-deploy-temp credentials, remove open ingress on "
                    f"{primary_rogue.get('metadata', {}).get('security_group', 'security group')}, "
                    f"and terminate {len(rogue_resources)} rogue instances in {primary_rogue['region']}."
                ),
                rationale=(
                    "Launched after off-hours ConsoleLogin from an unseen IP and running above 90% CPU."
                ),
                estimated_monthly_savings_usd=rogue_savings,
                confidence="high",
                state=RecommendationState.PENDING,
            )
        )
        counter += 1

    for res in resources:
        rid = res["resource_id"]
        rtype = res["resource_type"]
        util = float(res.get("utilization_pct", 0.0))
        cost = float(res.get("monthly_cost_usd", 0.0))
        meta = res.get("metadata", {})

        if rtype == "ec2" and res.get("status") == "running" and util < 15.0:
            recs.append(
                Recommendation(
                    recommendation_id=f"rec_{counter:04d}",
                    resource_id=rid,
                    category=RecommendationCategory.COST,
                    title=f"Downsize underutilized EC2 instance ({res.get('name') or rid})",
                    action=f"Resize {rid} from {meta.get('instance_type', 'current type')} to a smaller tier.",
                    rationale=f"Utilization averaged {util:.1f}% across the baseline window.",
                    estimated_monthly_savings_usd=round(cost * 0.5, 2),
                    confidence="high",
                    state=RecommendationState.PENDING,
                )
            )
            counter += 1
        elif rtype == "ebs" and res.get("status") == "available" and meta.get("attached") is False:
            recs.append(
                Recommendation(
                    recommendation_id=f"rec_{counter:04d}",
                    resource_id=rid,
                    category=RecommendationCategory.COST,
                    title=f"Snapshot and delete unattached EBS volume ({res.get('name') or rid})",
                    action=f"Create a final snapshot and delete unattached volume {rid}.",
                    rationale="Volume is in 'available' (unattached) state with 0% utilization.",
                    estimated_monthly_savings_usd=round(cost, 2),
                    confidence="high",
                    state=RecommendationState.PENDING,
                )
            )
            counter += 1
        elif rtype == "rds" and res.get("backup_status") in {"missing", "outdated"}:
            recs.append(
                Recommendation(
                    recommendation_id=f"rec_{counter:04d}",
                    resource_id=rid,
                    category=RecommendationCategory.BACKUP,
                    title=f"Enable automated backups on RDS ({res.get('name') or rid})",
                    action=f"Set backup retention to 14 days and take an immediate snapshot of {rid}.",
                    rationale=f"Critical database {rid} currently reports backup_status='{res.get('backup_status')}'.",
                    estimated_monthly_savings_usd=0.0,
                    confidence="high",
                    state=RecommendationState.PENDING,
                )
            )
            counter += 1

    flagged_traffic = [entry for entry in traffic_logs if entry.get("bot_flagged")]
    if flagged_traffic:
        target_rid = flagged_traffic[0]["resource_id"]
        endpoints = ", ".join(entry["endpoint"] for entry in flagged_traffic[:3])
        egress_delta = sum(
            float(c.get("delta_usd", 0.0))
            for c in cost_usage
            if c.get("is_anomalous") and c.get("resource_id") == target_rid
        )
        recs.append(
            Recommendation(
                recommendation_id=f"rec_{counter:04d}",
                resource_id=target_rid,
                category=RecommendationCategory.SECURITY,
                title="Apply WAF rate limiting against automated scraper traffic",
                action=f"Attach AWS WAF rate-based rules and edge caching for {endpoints}.",
                rationale="Automated clients generate sustained high-frequency bursts driving CPU and egress spikes.",
                estimated_monthly_savings_usd=round(egress_delta, 2),
                confidence="high",
                state=RecommendationState.PENDING,
            )
        )

    return recs


def seed_database(
    session: Session,
    provider: TelemetryProvider | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Populate ORM tables from a TelemetryProvider idempotently.

    Returns inserted row counts per table. When ``force=False`` and resources
    already exist, performs no writes and returns zero counts.
    """
    existing_count = session.scalar(select(func.count()).select_from(CloudResource)) or 0
    if existing_count > 0 and not force:
        return {"resources": 0, "metrics": 0, "alerts": 0, "recommendations": 0}

    if force:
        session.execute(delete(TelemetryMetric))
        session.execute(delete(Recommendation))
        session.execute(delete(SecurityAlert))
        session.execute(delete(CloudResource))
        session.flush()

    source = provider or MockTelemetryProvider()
    raw_resources = source.get_resources()
    raw_metrics = source.get_metrics()
    raw_cloudtrail = source.get_cloudtrail_events()
    raw_traffic = source.get_traffic_logs()
    raw_costs = source.get_cost_usage()

    known_resource_ids: set[str] = set()
    resource_models: list[CloudResource] = []
    for item in raw_resources:
        rid = item["resource_id"]
        known_resource_ids.add(rid)
        last_backup = item.get("last_backup_at")
        resource_models.append(
            CloudResource(
                resource_id=rid,
                name=item.get("name"),
                resource_type=_coerce_enum(ResourceType, item["resource_type"]),  # type: ignore[arg-type]
                region=item["region"],
                status=item["status"],
                utilization_pct=float(item.get("utilization_pct", 0.0)),
                backup_status=_coerce_enum(BackupStatus, item.get("backup_status", "not_applicable")),  # type: ignore[arg-type]
                last_backup_at=parse_timestamp(last_backup) if last_backup else None,
                monthly_cost_usd=float(item.get("monthly_cost_usd", 0.0)),
                metadata_json=dict(item.get("metadata", {})),
            )
        )
    session.add_all(resource_models)
    session.flush()

    metric_models: list[TelemetryMetric] = []
    for row in raw_metrics:
        if row["resource_id"] not in known_resource_ids:
            continue
        metric_models.append(
            TelemetryMetric(
                resource_id=row["resource_id"],
                timestamp=parse_timestamp(row["timestamp"]),
                cpu_utilization=float(row.get("cpu_utilization", 0.0)),
                network_in_bytes=float(row.get("network_in_bytes", 0.0)),
                network_out_bytes=float(row.get("network_out_bytes", 0.0)),
                request_count=int(row.get("request_count", 0)),
                anomaly_score=row.get("anomaly_score"),
            )
        )
    session.add_all(metric_models)

    incidents = correlate_signals(
        cloudtrail_events=[ev for ev in raw_cloudtrail if ev.get("is_anomalous")],
        metric_spikes=_extract_metric_spikes(raw_metrics),
        cost_deltas=[cost for cost in raw_costs if cost.get("is_anomalous")],
        time_window_minutes=60,
        min_signals=2,
    )

    alert_models: list[SecurityAlert] = []
    alerted_resources: set[str] = set()
    for inc in incidents:
        primary_rid = inc.primary_resource_id if inc.primary_resource_id in known_resource_ids else None
        if primary_rid:
            alerted_resources.add(primary_rid)
        alert_models.append(
            SecurityAlert(
                alert_id=f"alert_{inc.incident_id}",
                resource_id=primary_rid,
                alert_type=inc.incident_type,
                severity=inc.severity,
                risk_score=inc.risk_score,
                title=inc.title,
                correlated_event_ids=list(inc.correlated_event_ids),
                signal_breakdown=inc.signal_breakdown.model_dump(),
                ai_summary=inc.summary,
                recommended_actions=list(inc.recommended_actions),
                status=AlertStatus.OPEN,
                created_at=inc.window_end,
            )
        )

    for res in raw_resources:
        rid = res["resource_id"]
        if (
            res.get("resource_type") == "rds"
            and res.get("backup_status") == "missing"
            and rid not in alerted_resources
        ):
            alert_models.append(
                SecurityAlert(
                    alert_id=f"alert_backup_{rid}",
                    resource_id=rid,
                    alert_type="backup_missing",
                    severity=AlertSeverity.HIGH,
                    risk_score=66.0,
                    title=f"Critical RDS instance {res.get('name') or rid} has no recent backup",
                    correlated_event_ids=[],
                    signal_breakdown={"resource_impact": 78.0, "iam_risk": 40.0, "cost_impact": 10.0},
                    ai_summary=f"Production database {rid} currently has backup_status='missing'.",
                    recommended_actions=[
                        f"Enable automated backups on {rid} and run an immediate manual snapshot."
                    ],
                    status=AlertStatus.OPEN,
                )
            )
    session.add_all(alert_models)

    rec_models = [
        rec
        for rec in _build_seed_recommendations(raw_resources, raw_traffic, raw_costs)
        if rec.resource_id in known_resource_ids
    ]
    session.add_all(rec_models)
    session.commit()

    return {
        "resources": len(resource_models),
        "metrics": len(metric_models),
        "alerts": len(alert_models),
        "recommendations": len(rec_models),
    }


def list_resources(
    session: Session,
    resource_type: ResourceType | str | None = None,
    region: str | None = None,
    backup_status: BackupStatus | str | None = None,
) -> list[CloudResource]:
    """Query monitored cloud resources with optional type, region, and backup filters."""
    stmt = select(CloudResource)
    coerced_type = _coerce_enum(ResourceType, resource_type)
    coerced_backup = _coerce_enum(BackupStatus, backup_status)

    if coerced_type is not None:
        stmt = stmt.where(CloudResource.resource_type == coerced_type)
    if region is not None:
        stmt = stmt.where(CloudResource.region == region)
    if coerced_backup is not None:
        stmt = stmt.where(CloudResource.backup_status == coerced_backup)

    stmt = stmt.order_by(CloudResource.monthly_cost_usd.desc(), CloudResource.resource_id.asc())
    return list(session.scalars(stmt).all())


def list_alerts(
    session: Session,
    severity: AlertSeverity | str | None = None,
    status: AlertStatus | str | None = None,
) -> list[SecurityAlert]:
    """Query security alerts with optional severity and status filters."""
    stmt = select(SecurityAlert)
    coerced_severity = _coerce_enum(AlertSeverity, severity)
    coerced_status = _coerce_enum(AlertStatus, status)

    if coerced_severity is not None:
        stmt = stmt.where(SecurityAlert.severity == coerced_severity)
    if coerced_status is not None:
        stmt = stmt.where(SecurityAlert.status == coerced_status)

    stmt = stmt.order_by(SecurityAlert.risk_score.desc(), SecurityAlert.created_at.desc())
    return list(session.scalars(stmt).all())


def list_recommendations(
    session: Session,
    category: RecommendationCategory | str | None = None,
    state: RecommendationState | str | None = None,
) -> list[Recommendation]:
    """Query optimization/security/backup recommendations with optional filters."""
    stmt = select(Recommendation)
    coerced_category = _coerce_enum(RecommendationCategory, category)
    coerced_state = _coerce_enum(RecommendationState, state)

    if coerced_category is not None:
        stmt = stmt.where(Recommendation.category == coerced_category)
    if coerced_state is not None:
        stmt = stmt.where(Recommendation.state == coerced_state)

    stmt = stmt.order_by(
        Recommendation.estimated_monthly_savings_usd.desc(),
        Recommendation.recommendation_id.asc(),
    )
    return list(session.scalars(stmt).all())


def update_recommendation_state(
    session: Session,
    recommendation_id: str,
    new_state: RecommendationState | str,
) -> Recommendation:
    """Transition a recommendation's state ('pending', 'approved', or 'dismissed')."""
    target_state = _coerce_enum(RecommendationState, new_state)
    if target_state is None:
        raise ValueError("new_state cannot be None")

    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise LookupError(f"Recommendation '{recommendation_id}' not found")

    rec.state = target_state
    rec.updated_at = _utc_now()
    session.commit()
    session.refresh(rec)
    return rec


def save_alert(
    session: Session,
    alert_data: SecurityAlert | dict[str, Any] | Any,
) -> SecurityAlert:
    """Insert or update a SecurityAlert from an ORM entity, dict, or Pydantic model."""
    if isinstance(alert_data, SecurityAlert):
        merged = session.merge(alert_data)
        session.commit()
        session.refresh(merged)
        return merged

    if hasattr(alert_data, "model_dump"):
        payload: dict[str, Any] = alert_data.model_dump()
    elif isinstance(alert_data, dict):
        payload = dict(alert_data)
    else:
        raise TypeError(f"Unsupported alert_data type: {type(alert_data).__name__}")

    alert_id = payload.get("alert_id") or payload.get("incident_id")
    if not alert_id:
        raise ValueError("alert_data must include 'alert_id' or 'incident_id'")
    if "alert_id" not in payload and payload.get("incident_id"):
        alert_id = f"alert_{alert_id}"

    alert_type = payload.get("alert_type") or payload.get("incident_type") or "correlated_anomaly"
    severity = _coerce_enum(AlertSeverity, payload.get("severity", AlertSeverity.MEDIUM))
    status = _coerce_enum(AlertStatus, payload.get("status", AlertStatus.OPEN))
    resource_id = payload.get("resource_id") or payload.get("primary_resource_id")
    ai_summary = payload.get("ai_summary") if "ai_summary" in payload else payload.get("summary")
    created_raw = payload.get("created_at") or payload.get("window_end")
    created_at = parse_timestamp(created_raw) if created_raw is not None else _utc_now()

    existing = session.get(SecurityAlert, str(alert_id))
    if existing is None:
        if "title" not in payload:
            raise ValueError("New alert payload must include 'title'")
        record = SecurityAlert(
            alert_id=str(alert_id),
            resource_id=resource_id,
            alert_type=str(alert_type),
            severity=severity or AlertSeverity.MEDIUM,
            risk_score=float(payload.get("risk_score", 0.0)),
            title=str(payload["title"]),
            correlated_event_ids=list(payload.get("correlated_event_ids", [])),
            signal_breakdown=dict(payload.get("signal_breakdown", {})),
            ai_summary=ai_summary,
            recommended_actions=list(payload.get("recommended_actions", [])),
            status=status or AlertStatus.OPEN,
            created_at=created_at,
        )
        session.add(record)
        target = record
    else:
        if "resource_id" in payload or "primary_resource_id" in payload:
            existing.resource_id = resource_id
        if "alert_type" in payload or "incident_type" in payload:
            existing.alert_type = str(alert_type)
        if "severity" in payload and severity is not None:
            existing.severity = severity
        if "risk_score" in payload:
            existing.risk_score = float(payload["risk_score"])
        if "title" in payload:
            existing.title = str(payload["title"])
        if "correlated_event_ids" in payload:
            existing.correlated_event_ids = list(payload["correlated_event_ids"])
        if "signal_breakdown" in payload:
            existing.signal_breakdown = dict(payload["signal_breakdown"])
        if "ai_summary" in payload or "summary" in payload:
            existing.ai_summary = ai_summary
        if "recommended_actions" in payload:
            existing.recommended_actions = list(payload["recommended_actions"])
        if "status" in payload and status is not None:
            existing.status = status
        if created_raw is not None:
            existing.created_at = created_at
        target = existing

    session.commit()
    session.refresh(target)
    return target
