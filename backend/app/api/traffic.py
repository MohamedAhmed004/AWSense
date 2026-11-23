"""Traffic telemetry, bot pattern detection, and cost impact endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.auditor import summarize_traffic_impact
from app.services.correlator import parse_timestamp
from app.services.telemetry_provider import get_telemetry_provider

router = APIRouter(prefix="/api/v1", tags=["traffic"])


class TrafficTimelinePoint(BaseModel):
    """Hourly request volume, bot share, CPU, and egress datapoint."""

    timestamp: datetime
    total_requests: int = Field(ge=0)
    bot_requests: int = Field(ge=0)
    avg_cpu_pct: float = Field(ge=0.0, le=100.0)
    network_out_gb: float = Field(ge=0.0)


class SuspiciousEndpointPattern(BaseModel):
    """Endpoint flagged for high-frequency repetitive or scraper behavior."""

    endpoint: str
    method: str
    request_count_24h: int = Field(ge=0)
    bot_share_pct: float = Field(ge=0.0, le=100.0)
    bot_flagged: bool
    pattern_reason: str
    top_user_agent: str


class BotFlagSummary(BaseModel):
    """Aggregate summary of flagged automated traffic."""

    total_requests_24h: int
    flagged_bot_requests_24h: int
    bot_traffic_pct: float = Field(ge=0.0, le=100.0)
    suspicious_ips_count: int
    flagged_endpoints_count: int


class TrafficCostImpact(BaseModel):
    """Estimated infrastructure and egress cost caused by automated traffic."""

    affected_resource_id: str
    estimated_daily_cost_usd: float
    estimated_monthly_cost_usd: float
    added_egress_gb_24h: float
    cpu_overhead_pct: float


class TrafficResponse(BaseModel):
    """Response payload for GET /api/v1/traffic."""

    request_rate_timeline: list[TrafficTimelinePoint]
    suspicious_endpoints: list[SuspiciousEndpointPattern]
    bot_flags: BotFlagSummary
    cost_impact: TrafficCostImpact


@router.get("/traffic", response_model=TrafficResponse)
def get_traffic() -> TrafficResponse:
    """Return traffic rate timeline, suspicious endpoint patterns, bot flags, and cost impact."""
    provider = get_telemetry_provider()
    logs = sorted(provider.get_traffic_logs(), key=lambda entry: entry["timestamp"])
    impact_summary = summarize_traffic_impact(logs)

    timeline = [
        TrafficTimelinePoint(
            timestamp=parse_timestamp(entry["timestamp"]),
            total_requests=int(entry.get("request_count", 0)),
            bot_requests=int(entry.get("bot_requests", 0)),
            avg_cpu_pct=float(entry.get("avg_cpu_pct", 0.0)),
            network_out_gb=float(entry.get("network_out_gb", 0.0)),
        )
        for entry in logs
    ]

    flagged_logs = [entry for entry in logs if entry.get("bot_flagged")]
    endpoint_rows = flagged_logs if flagged_logs else logs
    suspicious_endpoints = [
        SuspiciousEndpointPattern(
            endpoint=str(entry.get("endpoint", "/")),
            method=str(entry.get("method", "GET")),
            request_count_24h=int(entry.get("request_count", 0)),
            bot_share_pct=float(entry.get("bot_share_pct", 0.0)),
            bot_flagged=bool(entry.get("bot_flagged", False)),
            pattern_reason=str(entry.get("pattern_reason", "")),
            top_user_agent=str(entry.get("top_user_agent", "unknown")),
        )
        for entry in endpoint_rows
    ]

    total_reqs = int(impact_summary["total_requests"])
    flagged_bot_reqs = sum(int(entry.get("bot_requests", 0)) for entry in flagged_logs)
    bot_pct = round((flagged_bot_reqs / total_reqs) * 100.0, 1) if total_reqs > 0 else 0.0
    suspicious_ips = sum(int(entry.get("source_ips_count", 0)) for entry in flagged_logs)

    # Combine modeled egress cost with any anomalous AWSDataTransfer delta from billing.
    affected_resource = (
        str(flagged_logs[0]["resource_id"])
        if flagged_logs and flagged_logs[0].get("resource_id")
        else "account-wide"
    )
    egress_deltas = [
        float(cost.get("delta_usd", 0.0))
        for cost in provider.get_cost_usage(days=1)
        if cost.get("is_anomalous") and cost.get("resource_id") == affected_resource
    ]
    daily_cost = round(
        max(float(impact_summary["estimated_daily_cost_impact_usd"]), sum(egress_deltas)),
        2,
    )
    added_egress_gb = round(sum(float(entry.get("network_out_gb", 0.0)) for entry in flagged_logs), 1)
    baseline_cpu = [float(entry.get("avg_cpu_pct", 0.0)) for entry in logs if not entry.get("bot_flagged")]
    flagged_cpu = [float(entry.get("avg_cpu_pct", 0.0)) for entry in flagged_logs]
    cpu_overhead = (
        round(max(0.0, max(flagged_cpu) - (sum(baseline_cpu) / len(baseline_cpu))), 1)
        if flagged_cpu and baseline_cpu
        else round(max(flagged_cpu), 1) if flagged_cpu else 0.0
    )

    return TrafficResponse(
        request_rate_timeline=timeline,
        suspicious_endpoints=suspicious_endpoints,
        bot_flags=BotFlagSummary(
            total_requests_24h=total_reqs,
            flagged_bot_requests_24h=flagged_bot_reqs,
            bot_traffic_pct=bot_pct,
            suspicious_ips_count=suspicious_ips,
            flagged_endpoints_count=len(impact_summary["flagged_endpoints"]),
        ),
        cost_impact=TrafficCostImpact(
            affected_resource_id=affected_resource,
            estimated_daily_cost_usd=daily_cost,
            estimated_monthly_cost_usd=round(daily_cost * 30.0, 2),
            added_egress_gb_24h=added_egress_gb,
            cpu_overhead_pct=cpu_overhead,
        ),
    )
