
"""Scenario simulation endpoint for AWSense."""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.auditor import (
    audit_resources,
    summarize_traffic_impact,
)
from app.services.telemetry_provider import get_telemetry_provider


router = APIRouter(prefix="/api/v1", tags=["simulate"])


class SimulationRequest(BaseModel):
    scenario: Literal["iam_breach", "bot_traffic", "resource_waste"]


class SimulationIncident(BaseModel):
    title: str
    risk_score: int
    severity: str
    summary: str
    recommended_actions: list[str]


class SimulationResponse(BaseModel):
    incident: SimulationIncident
    findings: list[str]
    recommendations: list[dict[str, Any]]


def simulate_iam_breach(provider: Any) -> SimulationResponse:
    events = provider.get_cloudtrail_events()

    suspicious_events = [
        event for event in events
        if event.get("is_anomalous") is True
    ]

    findings = [
        (
            f"Suspicious event: {event.get('event_name')} "
            f"by {event.get('principal')} "
            f"in {event.get('region')} "
            f"(risk hint: {event.get('risk_hint')})"
        )
        for event in suspicious_events
    ]

    if not findings:
        findings.append("No suspicious IAM activity was detected.")

    actions = [
        "Disable or rotate credentials for suspicious IAM principals.",
        "Review CloudTrail events and investigate unfamiliar regions and IP addresses.",
        "Inspect security group changes and newly created EC2 instances.",
        "Enable MFA and enforce least-privilege IAM policies.",
    ]

    recommendations = [
        {
            "title": "Secure suspicious IAM credentials",
            "action": "Disable or rotate credentials for suspicious principals.",
            "category": "security",
            "priority": "critical",
        },
        {
            "title": "Review unauthorized infrastructure changes",
            "action": "Investigate unexpected security group and EC2 changes.",
            "category": "security",
            "priority": "high",
        },
    ]

    incident = SimulationIncident(
        title="Potential IAM Security Breach",
        risk_score=96 if suspicious_events else 10,
        severity="critical" if suspicious_events else "low",
        summary=(
            f"Detected {len(suspicious_events)} suspicious CloudTrail events."
            if suspicious_events
            else "No suspicious IAM activity was detected."
        ),
        recommended_actions=actions if suspicious_events else [],
    )

    return SimulationResponse(
        incident=incident,
        findings=findings,
        recommendations=recommendations if suspicious_events else [],
    )


def simulate_bot_traffic(provider: Any) -> SimulationResponse:
    traffic_logs = provider.get_traffic_logs()
    impact = summarize_traffic_impact(traffic_logs)

    total_requests = impact.get("total_requests", 0)
    bot_share = impact.get("bot_share_pct", 0)
    flagged_endpoints = impact.get("flagged_endpoints", [])

    daily_cost = impact.get("estimated_daily_cost_impact_usd", 0)
    monthly_cost = impact.get("estimated_monthly_cost_impact_usd", 0)

    findings = [
        f"Total requests analyzed: {total_requests:,}.",
        f"Bot traffic represents {bot_share:.2f}% of total requests.",
        f"Estimated daily cost impact: ${daily_cost:.2f}.",
        f"Estimated monthly cost impact: ${monthly_cost:.2f}.",
    ]

    findings.extend(
        f"Suspicious bot traffic detected on endpoint: {endpoint}."
        for endpoint in flagged_endpoints
    )

    actions = [
        "Enable AWS WAF bot control rules.",
        "Apply rate limiting to suspicious endpoints.",
        "Block or challenge suspicious IP addresses and user agents.",
        "Monitor authentication endpoints for credential-stuffing attacks.",
    ]

    recommendations = [
        {
            "title": "Mitigate automated bot traffic",
            "action": "Configure AWS WAF and rate limiting for flagged endpoints.",
            "category": "security",
            "priority": "high",
        },
        {
            "title": "Reduce unnecessary network egress costs",
            "action": "Investigate excessive automated requests and optimize responses.",
            "category": "optimization",
            "priority": "medium",
            "estimated_monthly_savings_usd": round(monthly_cost, 2),
        },
    ]

    incident = SimulationIncident(
        title="Abnormal Bot Traffic Detected",
        risk_score=92 if flagged_endpoints else 15,
        severity="critical" if flagged_endpoints else "low",
        summary=(
            f"Bot traffic accounts for {bot_share:.2f}% of "
            f"{total_requests:,} requests. "
            f"{len(flagged_endpoints)} endpoints were flagged."
        ),
        recommended_actions=actions if flagged_endpoints else [],
    )

    return SimulationResponse(
        incident=incident,
        findings=findings,
        recommendations=recommendations if flagged_endpoints else [],
    )


def simulate_resource_waste(provider: Any) -> SimulationResponse:
    resources = provider.get_resources()
    metrics = provider.get_metrics(days=30)

    audit_findings = audit_resources(resources, metrics)

    findings = [
        (
            f"{item.get('description', item.get('issue', 'Resource issue'))} "
            f"(Resource: {item.get('resource_id', 'unknown')})"
        )
        for item in audit_findings
    ]

    recommendations = [
        {
            "title": f"Resolve {item.get('issue', 'resource issue')}",
            "action": item.get("description", "Review this resource."),
            "category": "optimization",
            "priority": "high",
            "resource_id": item.get("resource_id"),
            "estimated_monthly_savings_usd": item.get(
                "estimated_monthly_savings_usd", 0
            ),
        }
        for item in audit_findings
    ]

    total_savings = sum(
        float(item.get("estimated_monthly_savings_usd", 0))
        for item in audit_findings
    )

    incident = SimulationIncident(
        title="Cloud Resource Waste Detected",
        risk_score=78 if audit_findings else 10,
        severity="high" if audit_findings else "low",
        summary=(
            f"Detected {len(audit_findings)} resource issues. "
            f"Potential monthly savings: ${total_savings:.2f}."
        ),
        recommended_actions=[
            "Review and resize underutilized EC2 instances.",
            "Remove unattached EBS volumes when they are no longer needed.",
            "Enable or update backups for unprotected resources.",
            "Review monthly resource costs and utilization.",
        ] if audit_findings else [],
    )

    if not findings:
        findings.append("No resource waste or backup issues were detected.")

    return SimulationResponse(
        incident=incident,
        findings=findings,
        recommendations=recommendations,
    )


@router.post("/simulate", response_model=SimulationResponse)
def simulate_scenario(request: SimulationRequest) -> SimulationResponse:
    provider = get_telemetry_provider("mock")

    if request.scenario == "iam_breach":
        return simulate_iam_breach(provider)

    if request.scenario == "bot_traffic":
        return simulate_bot_traffic(provider)

    return simulate_resource_waste(provider)
