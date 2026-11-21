"""Cloud resource inventory, utilization, and backup status endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.models.entities import BackupStatus, ResourceType

router = APIRouter(prefix="/api/v1", tags=["resources"])


class ResourceItem(BaseModel):
    """Inventory, utilization, and backup status for a single AWS resource."""

    resource_id: str
    name: str | None = None
    resource_type: ResourceType
    region: str
    status: str
    utilization_pct: float = Field(ge=0.0, le=100.0)
    backup_status: BackupStatus
    last_backup_at: datetime | None = None
    monthly_cost_usd: float = Field(ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceSummary(BaseModel):
    """Aggregate summary calculated over the returned resource list."""

    total: int
    total_monthly_cost_usd: float
    unprotected_count: int
    underutilized_count: int


class ResourcesResponse(BaseModel):
    """Response payload for GET /api/v1/resources."""

    summary: ResourceSummary
    resources: list[ResourceItem]


_SAMPLE_RESOURCES: tuple[ResourceItem, ...] = (
    ResourceItem(
        resource_id="i-0a1b2c3d4e5f60001",
        name="legacy-batch-worker",
        resource_type=ResourceType.EC2,
        region="us-east-1",
        status="running",
        utilization_pct=6.8,
        backup_status=BackupStatus.PROTECTED,
        last_backup_at=datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc),
        monthly_cost_usd=168.00,
        metadata={"instance_type": "m5.xlarge", "env": "production"},
    ),
    ResourceItem(
        resource_id="i-0a1b2c3d4e5f60002",
        name="public-catalog-web",
        resource_type=ResourceType.EC2,
        region="us-east-1",
        status="running",
        utilization_pct=91.4,
        backup_status=BackupStatus.PROTECTED,
        last_backup_at=datetime(2026, 11, 21, 3, 15, tzinfo=timezone.utc),
        monthly_cost_usd=295.50,
        metadata={"instance_type": "c6i.xlarge", "env": "production"},
    ),
    ResourceItem(
        resource_id="i-0f9e8d7c6b5a49999",
        name="unrecognized-gpu-node",
        resource_type=ResourceType.EC2,
        region="ap-southeast-1",
        status="running",
        utilization_pct=96.2,
        backup_status=BackupStatus.MISSING,
        last_backup_at=None,
        monthly_cost_usd=742.00,
        metadata={"instance_type": "g5.2xlarge", "launched_by": "ci-deploy-temp"},
    ),
    ResourceItem(
        resource_id="vol-09911223344556677",
        name="orphan-analytics-ebs",
        resource_type=ResourceType.EBS,
        region="us-east-1",
        status="available",
        utilization_pct=0.0,
        backup_status=BackupStatus.MISSING,
        last_backup_at=None,
        monthly_cost_usd=48.00,
        metadata={"volume_type": "gp3", "size_gb": 600, "attached": False},
    ),
    ResourceItem(
        resource_id="db-prod-orders-01",
        name="orders-primary-rds",
        resource_type=ResourceType.RDS,
        region="us-east-1",
        status="available",
        utilization_pct=54.3,
        backup_status=BackupStatus.MISSING,
        last_backup_at=None,
        monthly_cost_usd=412.25,
        metadata={"engine": "postgres", "instance_class": "db.r6g.large", "multi_az": True},
    ),
    ResourceItem(
        resource_id="s3-awsense-audit-logs",
        name="central-audit-archive",
        resource_type=ResourceType.S3,
        region="us-east-1",
        status="active",
        utilization_pct=62.0,
        backup_status=BackupStatus.PROTECTED,
        last_backup_at=datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc),
        monthly_cost_usd=177.00,
        metadata={"versioning": True, "encryption": "aws:kms"},
    ),
)


@router.get("/resources", response_model=ResourcesResponse)
def get_resources(
    resource_type: ResourceType | None = Query(default=None),
    region: str | None = Query(default=None),
    backup_status: BackupStatus | None = Query(default=None),
) -> ResourcesResponse:
    """Return cloud resource inventory with utilization and backup protection metadata."""
    filtered = [
        item
        for item in _SAMPLE_RESOURCES
        if (resource_type is None or item.resource_type == resource_type)
        and (region is None or item.region == region)
        and (backup_status is None or item.backup_status == backup_status)
    ]

    summary = ResourceSummary(
        total=len(filtered),
        total_monthly_cost_usd=round(sum(item.monthly_cost_usd for item in filtered), 2),
        unprotected_count=sum(
            1
            for item in filtered
            if item.backup_status in {BackupStatus.MISSING, BackupStatus.OUTDATED}
        ),
        underutilized_count=sum(
            1 for item in filtered if item.utilization_pct < 15.0 and item.resource_type != ResourceType.S3
        ),
    )
    return ResourcesResponse(summary=summary, resources=filtered)
