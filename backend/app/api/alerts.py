
"""Correlated security and cost alerts endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import AlertSeverity, AlertStatus
from app.services.correlator import (
    CloudTrailEvent,
    CostDelta,
    MetricSpike,
    SignalBreakdown,
    correlate_signals,
)
from app.services.repository import list_alerts

router = APIRouter(prefix="/api/v1", tags=["alerts"])


class AlertItem(BaseModel):
    """Correlated security or cost incident exposed by GET /api/v1/alerts."""

    alert_id: str
    resource_id: str | None = None
    resource_ids: list[str] = Field(default_factory=list)
    alert_type: str
    severity: AlertSeverity
    risk_score: float = Field(ge=0.0, le=100.0)
    title: str
    correlated_event_ids: list[str] = Field(default_factory=list)
    signal_breakdown: SignalBreakdown
    summary: str
    recommended_actions: list[str] = Field(default_factory=list)
    status: AlertStatus
    created_at: datetime


class AlertsResponse(BaseModel):
    """Response payload for GET /api/v1/alerts."""

    total: int
    alerts: list[AlertItem]


def _build_sample_alerts() -> tuple[AlertItem, ...]:
    """Generate deterministic static alerts via the correlation engine."""

    incidents = correlate_signals(
        cloudtrail_events=[
            CloudTrailEvent(
                event_id="ct-9001",
                timestamp="2026-11-21T02:14:00Z",
                event_name="ConsoleLogin",
                region="ap-southeast-1",
                principal="ci-deploy-temp",
                source_ip="185.220.101.42",
                is_anomalous=True,
                risk_hint=0.92,
            ),
            CloudTrailEvent(
                event_id="ct-9002",
                timestamp="2026-11-21T02:19:00Z",
                event_name="AuthorizeSecurityGroupIngress",
                region="ap-southeast-1",
                principal="ci-deploy-temp",
                resource_id="sg-0f8899aabbccdd",
                is_anomalous=True,
                risk_hint=0.88,
            ),
            CloudTrailEvent(
                event_id="ct-9003",
                timestamp="2026-11-21T02:23:00Z",
                event_name="RunInstances",
                region="ap-southeast-1",
                principal="ci-deploy-temp",
                resource_id="i-0f9e8d7c6b5a49999",
                is_anomalous=True,
                risk_hint=0.94,
            ),
            CloudTrailEvent(
                event_id="ct-9010",
                timestamp="2026-11-20T16:10:00Z",
                event_name="ModifyDBInstance",
                region="us-east-1",
                principal="ops-maintenance",
                resource_id="db-prod-orders-01",
                is_anomalous=False,
                risk_hint=0.52,
            ),
        ],
        metric_spikes=[
            MetricSpike(
                event_id="cw-9004",
                timestamp="2026-11-21T02:35:00Z",
                resource_id="i-0f9e8d7c6b5a49999",
                metric_name="CPUUtilization",
                value=96.2,
                baseline=12.0,
                region="ap-southeast-1",
                anomaly_score=0.93,
            ),
            MetricSpike(
                event_id="cw-9021",
                timestamp="2026-11-20T19:05:00Z",
                resource_id="i-0a1b2c3d4e5f60002",
                metric_name="RequestCount",
                value=2410000.0,
                baseline=148500.0,
                region="us-east-1",
                anomaly_score=0.86,
            ),
            MetricSpike(
                event_id="cw-9022",
                timestamp="2026-11-20T19:15:00Z",
                resource_id="i-0a1b2c3d4e5f60002",
                metric_name="CPUUtilization",
                value=91.4,
                baseline=31.0,
                region="us-east-1",
                anomaly_score=0.81,
            ),
            MetricSpike(
                event_id="cw-9011",
                timestamp="2026-11-20T16:28:00Z",
                resource_id="db-prod-orders-01",
                metric_name="CPUUtilization",
                value=64.0,
                baseline=35.0,
                region="us-east-1",
                anomaly_score=0.45,
            ),
        ],
        cost_deltas=[
            CostDelta(
                event_id="ce-9005",
                timestamp="2026-11-21T02:50:00Z",
                service="AmazonEC2",
                delta_usd=420.50,
                baseline_usd=65.00,
                delta_pct=646.9,
                resource_id="i-0f9e8d7c6b5a49999",
                region="ap-southeast-1",
            ),
            CostDelta(
                event_id="ce-9023",
                timestamp="2026-11-20T19:35:00Z",
                service="AWSDataTransfer",
                delta_usd=138.20,
                baseline_usd=28.00,
                delta_pct=493.6,
                resource_id="i-0a1b2c3d4e5f60002",
                region="us-east-1",
            ),
        ],
        time_window_minutes=60,
        min_signals=2,
    )

    items: list[AlertItem] = []

    for index, inc in enumerate(incidents):
        alert_status = (
            AlertStatus.INVESTIGATING
            if index == 1
            else AlertStatus.OPEN
        )

        items.append(
            AlertItem(
                alert_id=f"alert_{inc.incident_id}",
                resource_id=inc.primary_resource_id,
                resource_ids=inc.resource_ids,
                alert_type=inc.incident_type,
                severity=inc.severity,
                risk_score=inc.risk_score,
                title=inc.title,
                correlated_event_ids=inc.correlated_event_ids,
                signal_breakdown=inc.signal_breakdown,
                summary=inc.summary,
                recommended_actions=inc.recommended_actions,
                status=alert_status,
                created_at=inc.window_end,
            )
        )

    return tuple(items)


_SAMPLE_ALERTS = _build_sample_alerts()


def _datetime_sort_key(value: datetime) -> float:
    """Normalize naive and timezone-aware datetimes for sorting."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.timestamp()


def _convert_db_alert(alert) -> AlertItem:
    """Convert a SQLAlchemy SecurityAlert into the API response schema."""

    raw_breakdown = alert.signal_breakdown or {}

    # Simulation alerts use a simplified breakdown.
    # Normalize it to the SignalBreakdown schema.
    breakdown = SignalBreakdown(
        cloudtrail_count=int(raw_breakdown.get("cloudtrail_count", 0)),
        metric_spike_count=int(raw_breakdown.get("metric_spike_count", 0)),
        cost_delta_count=int(raw_breakdown.get("cost_delta_count", 0)),
        iam_risk=float(
            raw_breakdown.get(
                "iam_risk",
                alert.risk_score if alert.alert_type == "iam_breach" else 0.0,
            )
        ),
        resource_impact=float(
            raw_breakdown.get(
                "resource_impact",
                raw_breakdown.get("risk_score", alert.risk_score),
            )
        ),
        cost_impact=float(raw_breakdown.get("cost_impact", 0.0)),
        traffic_anomaly=float(
            raw_breakdown.get(
                "traffic_anomaly",
                alert.risk_score if alert.alert_type == "bot_traffic" else 0.0,
            )
        ),
        total_cost_delta_usd=float(
            raw_breakdown.get("total_cost_delta_usd", 0.0)
        ),
    )

    resource_ids = [alert.resource_id] if alert.resource_id else []

    return AlertItem(
        alert_id=alert.alert_id,
        resource_id=alert.resource_id,
        resource_ids=resource_ids,
        alert_type=alert.alert_type,
        severity=alert.severity,
        risk_score=alert.risk_score,
        title=alert.title,
        correlated_event_ids=alert.correlated_event_ids or [],
        signal_breakdown=breakdown,
        summary=alert.ai_summary or "",
        recommended_actions=alert.recommended_actions or [],
        status=alert.status,
        created_at=alert.created_at,
    )


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    severity: AlertSeverity | None = Query(default=None),
    status: AlertStatus | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AlertsResponse:
    """Return sample and persisted alerts with optional filters."""

    # Start with the existing sample alerts.
    alerts_by_id = {
        alert.alert_id: alert.model_copy(deep=True)
        for alert in _SAMPLE_ALERTS
    }

    # Depends is not resolved when the function is called directly
    # outside FastAPI (for example, by a unit test).
    if isinstance(db, Session):
        # Add database alerts. Database records take priority on duplicate IDs.
        database_alerts = list_alerts(db)

        for db_alert in database_alerts:
            alerts_by_id[db_alert.alert_id] = _convert_db_alert(db_alert)

    filtered = [
        alert
        for alert in alerts_by_id.values()
        if (severity is None or alert.severity == severity)
        and (status is None or alert.status == status)
    ]

    filtered.sort(
        key=lambda alert: (
            alert.risk_score,
            _datetime_sort_key(alert.created_at),
        ),
        reverse=True,
    )

    return AlertsResponse(
        total=len(filtered),
        alerts=filtered,
    )
