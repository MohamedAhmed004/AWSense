"""Cloud resource inventory, utilization, and backup status endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import BackupStatus, ResourceType
from app.services.repository import list_resources

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


@router.get("/resources", response_model=ResourcesResponse)
def get_resources(
    resource_type: ResourceType | None = Query(default=None),
    region: str | None = Query(default=None),
    backup_status: BackupStatus | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ResourcesResponse:
    """Return cloud resource inventory with utilization and backup protection metadata."""
    rows = list_resources(
        db,
        resource_type=resource_type,
        region=region,
        backup_status=backup_status,
    )
    items = [
        ResourceItem(
            resource_id=row.resource_id,
            name=row.name,
            resource_type=row.resource_type,
            region=row.region,
            status=row.status,
            utilization_pct=row.utilization_pct,
            backup_status=row.backup_status,
            last_backup_at=row.last_backup_at,
            monthly_cost_usd=row.monthly_cost_usd,
            metadata=dict(row.metadata_json or {}),
        )
        for row in rows
    ]

    summary = ResourceSummary(
        total=len(items),
        total_monthly_cost_usd=round(sum(item.monthly_cost_usd for item in items), 2),
        unprotected_count=sum(
            1
            for item in items
            if item.backup_status in {BackupStatus.MISSING, BackupStatus.OUTDATED}
        ),
        underutilized_count=sum(
            1
            for item in items
            if item.utilization_pct < 15.0 and item.resource_type != ResourceType.S3
        ),
    )
    return ResourcesResponse(summary=summary, resources=items)
