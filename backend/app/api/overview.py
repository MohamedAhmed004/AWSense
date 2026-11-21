"""Overview dashboard summary endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models.entities import AlertSeverity

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


_SAMPLE_OVERVIEW = OverviewResponse(
    health_score=64.0,
    risk_level=AlertSeverity.HIGH,
    total_monthly_savings_usd=318.40,
    monthly_spend_usd=1842.75,
    active_alerts=AlertCountBreakdown(
        total=3,
        critical=1,
        high=1,
        medium=1,
        low=0,
    ),
    monitored_resources=6,
    unprotected_resources=3,
    cost_usage_trend=[
        CostUsagePoint(date="2026-11-15", daily_cost_usd=48.20, avg_cpu_pct=28.4, request_count=142000),
        CostUsagePoint(date="2026-11-16", daily_cost_usd=49.10, avg_cpu_pct=29.1, request_count=148500),
        CostUsagePoint(date="2026-11-17", daily_cost_usd=47.80, avg_cpu_pct=27.6, request_count=139800),
        CostUsagePoint(date="2026-11-18", daily_cost_usd=50.40, avg_cpu_pct=30.2, request_count=155400),
        CostUsagePoint(date="2026-11-19", daily_cost_usd=188.60, avg_cpu_pct=68.5, request_count=1180000),
        CostUsagePoint(date="2026-11-20", daily_cost_usd=312.90, avg_cpu_pct=84.2, request_count=2410000),
        CostUsagePoint(date="2026-11-21", daily_cost_usd=289.45, avg_cpu_pct=76.9, request_count=2190000),
    ],
)


@router.get("/overview", response_model=OverviewResponse)
def get_overview() -> OverviewResponse:
    """Return global cloud health score, savings potential, active alerts, and trend series."""
    return _SAMPLE_OVERVIEW
