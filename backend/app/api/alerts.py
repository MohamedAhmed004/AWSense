"""Correlated security and cost alerts endpoint backed by SQLAlchemy and ML scoring."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import AlertSeverity, AlertStatus, TelemetryMetric
from app.services.ai_explainer import explain_incident
from app.services.correlator import SignalBreakdown
from app.services.ml_detector import score_metrics
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
    ml_score: float | None = Field(default=None, ge=0.0, le=1.0)
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


def _normalize_breakdown(raw: dict[str, Any] | None) -> SignalBreakdown:
    """Fill default values so alerts without full signal counts still validate cleanly."""
    data = raw or {}
    return SignalBreakdown(
        cloudtrail_count=int(data.get("cloudtrail_count", 0)),
        metric_spike_count=int(data.get("metric_spike_count", 0)),
        cost_delta_count=int(data.get("cost_delta_count", 0)),
        iam_risk=float(data.get("iam_risk", 0.0)),
        resource_impact=float(data.get("resource_impact", 0.0)),
        cost_impact=float(data.get("cost_impact", 0.0)),
        traffic_anomaly=float(data.get("traffic_anomaly", 0.0)),
        total_cost_delta_usd=float(data.get("total_cost_delta_usd", 0.0)),
    )


def _compute_ml_scores_by_resource(db: Session) -> dict[str, float]:
    """Compute peak IsolationForest anomaly score per resource from stored TelemetryMetrics."""
    rows = list(db.scalars(select(TelemetryMetric)).all())
    if not rows:
        return {}

    records_by_resource: dict[str, list[dict[str, Any]]] = {}
    baseline_rows: list[dict[str, Any]] = []

    for row in rows:
        payload = {
            "resource_id": row.resource_id,
            "cpu_utilization": float(row.cpu_utilization),
            "network_in_bytes": float(row.network_in_bytes),
            "network_out_bytes": float(row.network_out_bytes),
            "request_count": int(row.request_count),
        }
        records_by_resource.setdefault(row.resource_id, []).append(payload)
        if row.cpu_utilization < 80.0 and row.request_count < 1_000_000:
            baseline_rows.append(payload)

    if len(baseline_rows) < 10:
        return {}

    scores_by_resource: dict[str, float] = {}
    for rid, target_rows in records_by_resource.items():
        scores = score_metrics(baseline_rows, target_rows)
        if scores:
            scores_by_resource[rid] = round(max(scores), 4)
    return scores_by_resource


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    severity: AlertSeverity | None = Query(default=None),
    status: AlertStatus | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AlertsResponse:
    """Return correlated security and cost-impact alerts from the database."""
    rows = list_alerts(db, severity=severity, status=status)
    ml_scores = _compute_ml_scores_by_resource(db)

    items: list[AlertItem] = []
    for row in rows:
        breakdown = _normalize_breakdown(row.signal_breakdown)
        resource_ids = [row.resource_id] if row.resource_id else []
        summary = row.ai_summary
        actions = list(row.recommended_actions or [])

        if not summary or not actions:
            explained = explain_incident(
                {
                    "title": row.title,
                    "resource_ids": resource_ids,
                    "signals": [{"event_id": eid} for eid in (row.correlated_event_ids or [])],
                    "signal_breakdown": breakdown.model_dump(),
                }
            )
            summary = summary or explained["summary"]
            if not actions:
                actions = explained["recommended_actions"]

        items.append(
            AlertItem(
                alert_id=row.alert_id,
                resource_id=row.resource_id,
                resource_ids=resource_ids,
                alert_type=row.alert_type,
                severity=row.severity,
                risk_score=row.risk_score,
                ml_score=ml_scores.get(row.resource_id) if row.resource_id else None,
                title=row.title,
                correlated_event_ids=list(row.correlated_event_ids or []),
                signal_breakdown=breakdown,
                summary=summary,
                recommended_actions=actions,
                status=row.status,
                created_at=row.created_at,
            )
        )

    return AlertsResponse(total=len(items), alerts=items)
