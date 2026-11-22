
"""Resource and traffic auditing helpers for AWSense."""

from collections import defaultdict
from typing import Any


# Approximate AWS data-transfer-out rate.
# This is an estimate, not an exact AWS bill.
EGRESS_COST_PER_GB_USD = 0.09

UNDERUTILIZED_THRESHOLD = 15.0


def audit_resources(
    resources: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find underutilized EC2s, unattached EBS volumes, and backup gaps."""

    findings: list[dict[str, Any]] = []

    # Calculate average CPU utilization for each resource.
    # Used only when utilization_pct is missing from the resource.
    cpu_values: dict[str, list[float]] = defaultdict(list)

    for metric in metrics:
        resource_id = metric.get("resource_id")
        cpu = metric.get("cpu_utilization")

        if resource_id and cpu is not None:
            cpu_values[resource_id].append(float(cpu))

    for resource in resources:
        resource_id = resource.get("resource_id", "unknown")
        resource_type = str(resource.get("resource_type", "")).lower()
        monthly_cost = float(resource.get("monthly_cost_usd") or 0.0)
        metadata = resource.get("metadata") or {}

        # 1. Underutilized EC2 instances
        if resource_type == "ec2":
            utilization = resource.get("utilization_pct")

            if utilization is None and cpu_values.get(resource_id):
                values = cpu_values[resource_id]
                utilization = sum(values) / len(values)

            if (
                utilization is not None
                and float(utilization) < UNDERUTILIZED_THRESHOLD
            ):
                findings.append(
                    {
                        "resource_id": resource_id,
                        "resource_type": resource_type,
                        "issue": "underutilized_ec2",
                        "description": (
                            f"EC2 utilization is {float(utilization):.1f}%, "
                            f"below the {UNDERUTILIZED_THRESHOLD:.1f}% threshold."
                        ),
                        "estimated_monthly_savings_usd": round(
                            monthly_cost * 0.5, 2
                        ),
                    }
                )

        # 2. Unattached EBS volumes
        if resource_type == "ebs":
            attached = metadata.get(
                "attached",
                resource.get("attached", True),
            )

            if resource.get("status") == "available" and attached is False:
                findings.append(
                    {
                        "resource_id": resource_id,
                        "resource_type": resource_type,
                        "issue": "unattached_ebs",
                        "description": "EBS volume is available but not attached.",
                        "estimated_monthly_savings_usd": round(
                            monthly_cost, 2
                        ),
                    }
                )

        # 3. Missing or outdated backups
        backup_status = str(
            resource.get("backup_status", "")
        ).lower()

        if backup_status in {"missing", "outdated"}:
            findings.append(
                {
                    "resource_id": resource_id,
                    "resource_type": resource_type,
                    "issue": f"{backup_status}_backup",
                    "description": (
                        f"Resource backup status is '{backup_status}'."
                    ),
                    "estimated_monthly_savings_usd": 0.0,
                }
            )

    return findings


def summarize_traffic_impact(
    traffic_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize requests, bot traffic, flagged endpoints, and cost impact."""

    total_requests = 0
    total_bot_requests = 0
    estimated_daily_cost = 0.0
    flagged_endpoints: list[str] = []

    for log in traffic_logs:
        requests = int(log.get("request_count") or 0)
        bot_requests = int(log.get("bot_requests") or 0)

        total_requests += requests
        total_bot_requests += bot_requests

        is_flagged = bool(log.get("bot_flagged", False))

        if is_flagged:
            endpoint = log.get("endpoint")

            if endpoint and endpoint not in flagged_endpoints:
                flagged_endpoints.append(endpoint)

            # Estimate the network cost attributable to bot requests.
            network_out_gb = float(log.get("network_out_gb") or 0.0)

            bot_ratio = (
                bot_requests / requests
                if requests > 0
                else 0.0
            )

            estimated_daily_cost += (
                network_out_gb
                * bot_ratio
                * EGRESS_COST_PER_GB_USD
            )

    bot_share_pct = (
        (total_bot_requests / total_requests) * 100
        if total_requests > 0
        else 0.0
    )

    estimated_daily_cost = round(estimated_daily_cost, 2)

    return {
        "total_requests": total_requests,
        "bot_share_pct": round(bot_share_pct, 2),
        "flagged_endpoints": flagged_endpoints,
        "estimated_daily_cost_impact_usd": estimated_daily_cost,
        "estimated_monthly_cost_impact_usd": round(
            estimated_daily_cost * 30, 2
        ),
    }
