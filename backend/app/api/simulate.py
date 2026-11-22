
"""Scenario simulation endpoint for AWSense."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.entities import RecommendationCategory, RecommendationState
from app.services.correlator import correlate_signals, CorrelatedIncident
from app.api.recommendations import RecommendationItem


router = APIRouter(prefix="/api/v1", tags=["simulate"])


class SimulationRequest(BaseModel):
    """Request body for a simulation scenario."""

    scenario: Literal["iam_breach", "bot_traffic", "resource_waste"]


class SimulationResponse(BaseModel):
    """Response returned after running a simulation."""

    scenario: str
    signals: list[dict[str, Any]]
    incident: CorrelatedIncident | None
    recommendations: list[RecommendationItem]


def _now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def _recommendation(
    resource_id: str,
    category: RecommendationCategory,
    title: str,
    action: str,
    rationale: str,
    savings: float = 0.0,
) -> RecommendationItem:
    """Create a recommendation for the simulated scenario."""

    now = _now()

    return RecommendationItem(
        recommendation_id=f"sim_{uuid4().hex[:10]}",
        resource_id=resource_id,
        category=category,
        title=title,
        action=action,
        rationale=rationale,
        estimated_monthly_savings_usd=savings,
        confidence="high",
        state=RecommendationState.PENDING,
        created_at=now,
        updated_at=now,
    )


def _generate_iam_breach() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[RecommendationItem],
]:
    """Generate signals and recommendations for a suspicious IAM breach."""

    now = _now()
    resource_id = "i-sim-iam-001"
    region = "us-east-1"
    principal = "suspicious-user"

    cloudtrail_events = [
        {
            "event_id": "sim_iam_001",
            "timestamp": now.isoformat(),
            "event_name": "ConsoleLogin",
            "region": region,
            "principal": principal,
            "resource_id": resource_id,
            "source_ip": "198.51.100.25",
            "is_anomalous": True,
            "risk_hint": 0.95,
        },
        {
            "event_id": "sim_iam_002",
            "timestamp": now.isoformat(),
            "event_name": "RunInstances",
            "region": region,
            "principal": principal,
            "resource_id": resource_id,
            "source_ip": "198.51.100.25",
            "is_anomalous": True,
            "risk_hint": 0.90,
        },
    ]

    metric_spikes = [
        {
            "event_id": "sim_iam_metric_001",
            "timestamp": now.isoformat(),
            "resource_id": resource_id,
            "metric_name": "cpu_utilization",
            "value": 96.0,
            "baseline": 25.0,
            "region": region,
            "anomaly_score": 0.95,
        }
    ]

    cost_deltas = [
        {
            "event_id": "sim_iam_cost_001",
            "timestamp": now.isoformat(),
            "service": "Amazon EC2",
            "delta_usd": 180.0,
            "baseline_usd": 100.0,
            "delta_pct": 180.0,
            "resource_id": resource_id,
            "region": region,
        }
    ]

    recommendations = [
        _recommendation(
            resource_id,
            RecommendationCategory.SECURITY,
            "Investigate suspicious IAM activity",
            "Revoke suspicious sessions, rotate exposed credentials, and review CloudTrail events.",
            "An anomalous login was followed by an unexpected EC2 instance launch.",
        ),
        _recommendation(
            resource_id,
            RecommendationCategory.COST,
            "Inspect unexpected EC2 resource usage",
            "Verify the newly launched instance and terminate it if unauthorized.",
            "Unexpected compute activity was correlated with increased CPU utilization and cost.",
            180.0,
        ),
    ]

    return cloudtrail_events, metric_spikes, cost_deltas, recommendations


def _generate_bot_traffic() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[RecommendationItem],
]:
    """Generate signals and recommendations for suspicious bot traffic."""

    now = _now()
    resource_id = "i-sim-web-001"
    region = "us-east-1"

    cloudtrail_events: list[dict[str, Any]] = []

    metric_spikes = [
        {
            "event_id": "sim_bot_metric_001",
            "timestamp": now.isoformat(),
            "resource_id": resource_id,
            "metric_name": "request_count",
            "value": 1500000.0,
            "baseline": 50000.0,
            "region": region,
            "anomaly_score": 0.98,
            "metadata": {
                "endpoint": "/api/catalog/export",
                "bot_share_pct": 96.4,
            },
        },
        {
            "event_id": "sim_bot_metric_002",
            "timestamp": now.isoformat(),
            "resource_id": resource_id,
            "metric_name": "network_out_bytes",
            "value": 95000000000.0,
            "baseline": 5000000000.0,
            "region": region,
            "anomaly_score": 0.92,
        },
    ]

    cost_deltas = [
        {
            "event_id": "sim_bot_cost_001",
            "timestamp": now.isoformat(),
            "service": "Amazon CloudFront",
            "delta_usd": 250.0,
            "baseline_usd": 100.0,
            "delta_pct": 250.0,
            "resource_id": resource_id,
            "region": region,
        }
    ]

    recommendations = [
        _recommendation(
            resource_id,
            RecommendationCategory.SECURITY,
            "Block suspicious bot traffic",
            "Configure AWS WAF rate-based rules and block abusive IP addresses.",
            "Automated traffic accounts for a very high percentage of requests.",
        ),
        _recommendation(
            resource_id,
            RecommendationCategory.COST,
            "Reduce bot-related infrastructure costs",
            "Enable CDN caching and apply rate limits to expensive API endpoints.",
            "Unusual request and network traffic caused a significant increase in service costs.",
            250.0,
        ),
    ]

    return cloudtrail_events, metric_spikes, cost_deltas, recommendations


def _generate_resource_waste() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[RecommendationItem],
]:
    """Generate signals and recommendations for underutilized resources."""

    now = _now()
    resource_id = "i-sim-waste-001"
    region = "us-east-1"

    cloudtrail_events: list[dict[str, Any]] = []

    metric_spikes = [
        {
            "event_id": "sim_waste_metric_001",
            "timestamp": now.isoformat(),
            "resource_id": resource_id,
            "metric_name": "cpu_utilization",
            "value": 7.0,
            "baseline": 35.0,
            "region": region,
            "anomaly_score": 0.70,
            "metadata": {
                "condition": "underutilized",
                "threshold_pct": 15.0,
            },
        }
    ]

    cost_deltas = [
        {
            "event_id": "sim_waste_cost_001",
            "timestamp": now.isoformat(),
            "service": "Amazon EC2",
            "delta_usd": 168.0,
            "baseline_usd": 0.0,
            "delta_pct": 100.0,
            "resource_id": resource_id,
            "region": region,
        }
    ]

    recommendations = [
        _recommendation(
            resource_id,
            RecommendationCategory.COST,
            "Right-size underutilized EC2 instance",
            "Review instance sizing and move to a smaller instance type if workload requirements allow.",
            "CPU utilization is below the 15% threshold while the instance continues to incur monthly costs.",
            84.0,
        )
    ]

    return cloudtrail_events, metric_spikes, cost_deltas, recommendations


@router.post("/simulate", response_model=SimulationResponse)
def simulate_scenario(payload: SimulationRequest) -> SimulationResponse:
    """Run a scenario and return generated signals, incident, and recommendations."""

    generators = {
        "iam_breach": _generate_iam_breach,
        "bot_traffic": _generate_bot_traffic,
        "resource_waste": _generate_resource_waste,
    }

    cloudtrail_events, metric_spikes, cost_deltas, recommendations = (
        generators[payload.scenario]()
    )

    # Correlate the generated signals into incidents.
    incidents = correlate_signals(
        cloudtrail_events=cloudtrail_events,
        metric_spikes=metric_spikes,
        cost_deltas=cost_deltas,
        time_window_minutes=60,
        min_signals=2,
    )

    # Prepare a unified list of signals for the response.
    signals: list[dict[str, Any]] = []

    for event in cloudtrail_events:
        signals.append({"signal_type": "cloudtrail", **event})

    for metric in metric_spikes:
        signals.append({"signal_type": "metric_spike", **metric})

    for cost in cost_deltas:
        signals.append({"signal_type": "cost_delta", **cost})

    return SimulationResponse(
        scenario=payload.scenario,
        signals=signals,
        incident=incidents[0] if incidents else None,
        recommendations=recommendations,
    )
