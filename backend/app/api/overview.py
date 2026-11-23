"""Overview dashboard summary endpoint computed from DB state and telemetry."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    AlertSeverity,
    AlertStatus,
    BackupStatus,
    RecommendationState,
    TelemetryMetric,
)
from app.services.repository import list_alerts, list_recommendations, list_resources
from app.services.telemetry_provider import get_telemetry_provider

router = APIRouter(prefix="/api/v1", tags=["overview"])


class AlertCountBreakdown(BaseModel):
    """Active alert counts broken down by severity."""

    total: int
    critical: int
    high: int
    medium: int
    low: int


class CostUsagePoint(BaseModel):
    """Single day datapoint for the cost and utilization trend chart."""

    date: str
    daily_cost_usd: float
    avg_cpu_pct: float
    request_count: int


class OverviewResponse(BaseModel):
    """Top-level AWSense overview KPIs and trend series."""

    health_score: float = Field(ge=0.0, le=100.0)
    risk_level: AlertSeverity
    total_monthly_savings_usd: float
    monthly_spend_usd: float
    active_alerts: AlertCountBreakdown
    monitored_resources: int
    unprotected_resources: int
    cost_usage_trend: list[CostUsagePoint]


def _build_trend_series(db: Session) -> list[CostUsagePoint]:
    """Combine daily provider cost totals with DB telemetry CPU and request metrics."""
    provider = get_telemetry_provider()
    cost_rows = provider.get_cost_usage(days=30)

    daily_cost: dict[str, float] = defaultdict(float)
    for entry in cost_rows:
        day = str(entry.get("date") or entry["timestamp"][:10])
        daily_cost[day] += float(entry.get("cost_usd", 0.0))

    daily_cpu: dict[str, list[float]] = defaultdict(list)
    daily_reqs: dict[str, int] = defaultdict(int)

    metric_rows = list(db.scalars(select(TelemetryMetric)).all())
    for metric in metric_rows:
        day = metric.timestamp.strftime("%Y-%m-%d")
        daily_cpu[day].append(float(metric.cpu_utilization))
        daily_reqs[day] += int(metric.request_count)

    all_days = sorted(set(daily_cost.keys()) | set(daily_cpu.keys()))
    trend: list[CostUsagePoint] = []
    for day in all_days:
        cpus = daily_cpu.get(day, [])
        avg_cpu = round(sum(cpus) / len(cpus), 1) if cpus else 0.0
        trend.append(
            CostUsagePoint(
                date=day,
                daily_cost_usd=round(daily_cost.get(day, 0.0), 2),
                avg_cpu_pct=avg_cpu,
                request_count=daily_reqs.get(day, 0),
            )
        )
    return trend


@router.get("/overview", response_model=OverviewResponse)
def get_overview(db: Session = Depends(get_db)) -> OverviewResponse:
    """Return global cloud health score, savings potential, active alerts, and trend series."""
    resources = list_resources(db)
    alerts = list_alerts(db)
    recommendations = list_recommendations(db)

    active = [
        a for a in alerts if a.status in {AlertStatus.OPEN, AlertStatus.INVESTIGATING}
    ]
    counts = {
        AlertSeverity.CRITICAL: 0,
        AlertSeverity.HIGH: 0,
        AlertSeverity.MEDIUM: 0,
        AlertSeverity.LOW: 0,
    }
    for alert in active:
        counts[alert.severity] += 1

    if counts[AlertSeverity.CRITICAL] > 0:
        risk_level = AlertSeverity.CRITICAL
    elif counts[AlertSeverity.HIGH] > 0:
        risk_level = AlertSeverity.HIGH
    elif counts[AlertSeverity.MEDIUM] > 0:
        risk_level = AlertSeverity.MEDIUM
    else:
        risk_level = AlertSeverity.LOW

    unprotected = sum(
        1
        for res in resources
        if res.backup_status in {BackupStatus.MISSING, BackupStatus.OUTDATED}
    )

    penalty = (
        counts[AlertSeverity.CRITICAL] * 20.0
        + counts[AlertSeverity.HIGH] * 10.0
        + counts[AlertSeverity.MEDIUM] * 5.0
        + counts[AlertSeverity.LOW] * 2.0
        + unprotected * 2.0
    )
    health_score = round(max(0.0, min(100.0, 100.0 - penalty)), 1)

    total_savings = round(
        sum(
            rec.estimated_monthly_savings_usd
            for rec in recommendations
            if rec.state != RecommendationState.DISMISSED
        ),
        2,
    )
    monthly_spend = round(sum(res.monthly_cost_usd for res in resources), 2)

    return OverviewResponse(
        health_score=health_score,
        risk_level=risk_level,
        total_monthly_savings_usd=total_savings,
        monthly_spend_usd=monthly_spend,
        active_alerts=AlertCountBreakdown(
            total=len(active),
            critical=counts[AlertSeverity.CRITICAL],
            high=counts[AlertSeverity.HIGH],
            medium=counts[AlertSeverity.MEDIUM],
            low=counts[AlertSeverity.LOW],
        ),
        monitored_resources=len(resources),
        unprotected_resources=unprotected,
        cost_usage_trend=_build_trend_series(db),
    )
