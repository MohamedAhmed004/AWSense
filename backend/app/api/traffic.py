"""Traffic telemetry, bot pattern detection, and cost impact endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

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


_SAMPLE_TRAFFIC = TrafficResponse(
    request_rate_timeline=[
        TrafficTimelinePoint(
            timestamp=datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc),
            total_requests=18500,
            bot_requests=1400,
            avg_cpu_pct=29.5,
            network_out_gb=3.2,
        ),
        TrafficTimelinePoint(
            timestamp=datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc),
            total_requests=21200,
            bot_requests=2100,
            avg_cpu_pct=31.0,
            network_out_gb=3.8,
        ),
        TrafficTimelinePoint(
            timestamp=datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc),
            total_requests=148000,
            bot_requests=126000,
            avg_cpu_pct=68.4,
            network_out_gb=24.6,
        ),
        TrafficTimelinePoint(
            timestamp=datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc),
            total_requests=640000,
            bot_requests=612000,
            avg_cpu_pct=91.4,
            network_out_gb=94.2,
        ),
        TrafficTimelinePoint(
            timestamp=datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc),
            total_requests=820000,
            bot_requests=791000,
            avg_cpu_pct=92.8,
            network_out_gb=118.5,
        ),
        TrafficTimelinePoint(
            timestamp=datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc),
            total_requests=762300,
            bot_requests=735500,
            avg_cpu_pct=88.1,
            network_out_gb=109.7,
        ),
    ],
    suspicious_endpoints=[
        SuspiciousEndpointPattern(
            endpoint="/api/catalog/export",
            method="GET",
            request_count_24h=1380000,
            bot_share_pct=96.4,
            bot_flagged=True,
            pattern_reason="High-frequency sequential pagination without session cookies",
            top_user_agent="python-requests/2.31.0",
        ),
        SuspiciousEndpointPattern(
            endpoint="/api/pricing/search",
            method="GET",
            request_count_24h=745000,
            bot_share_pct=91.8,
            bot_flagged=True,
            pattern_reason="Uniform 40ms request cadence across rotating ASN IPs",
            top_user_agent="Go-http-client/2.0",
        ),
        SuspiciousEndpointPattern(
            endpoint="/auth/login",
            method="POST",
            request_count_24h=143000,
            bot_share_pct=84.2,
            bot_flagged=True,
            pattern_reason="Credential-stuffing burst with elevated 401 failure ratio",
            top_user_agent="curl/8.5.0",
        ),
    ],
    bot_flags=BotFlagSummary(
        total_requests_24h=2410000,
        flagged_bot_requests_24h=2268000,
        bot_traffic_pct=94.1,
        suspicious_ips_count=47,
        flagged_endpoints_count=3,
    ),
    cost_impact=TrafficCostImpact(
        affected_resource_id="i-0a1b2c3d4e5f60002",
        estimated_daily_cost_usd=138.20,
        estimated_monthly_cost_usd=4146.00,
        added_egress_gb_24h=354.0,
        cpu_overhead_pct=60.4,
    ),
)


@router.get("/traffic", response_model=TrafficResponse)
def get_traffic() -> TrafficResponse:
    """Return traffic rate timeline, suspicious endpoint patterns, bot flags, and cost impact."""
    return _SAMPLE_TRAFFIC
