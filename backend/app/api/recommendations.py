"""Optimization, security, and backup recommendation endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.entities import RecommendationCategory, RecommendationState

router = APIRouter(prefix="/api/v1", tags=["recommendations"])


class RecommendationItem(BaseModel):
    """Actionable cost, security, or backup recommendation."""

    recommendation_id: str
    resource_id: str
    category: RecommendationCategory
    title: str
    action: str
    rationale: str | None = None
    estimated_monthly_savings_usd: float = Field(ge=0.0)
    confidence: str
    state: RecommendationState
    created_at: datetime
    updated_at: datetime


class RecommendationsResponse(BaseModel):
    """Response payload for GET /api/v1/recommendations."""

    total: int
    total_estimated_monthly_savings_usd: float
    recommendations: list[RecommendationItem]


class RecommendationActionRequest(BaseModel):
    """State transition payload for POST /api/v1/recommendations/{id}/action."""

    action: Literal["approved", "dismissed"]


class RecommendationActionResponse(BaseModel):
    """Response payload returned after toggling a recommendation's state."""

    recommendation: RecommendationItem
    previous_state: RecommendationState
    message: str


_SEED_RECOMMENDATIONS: tuple[RecommendationItem, ...] = (
    RecommendationItem(
        recommendation_id="rec_0001",
        resource_id="i-0a1b2c3d4e5f60001",
        category=RecommendationCategory.COST,
        title="Downsize underutilized batch EC2 instance",
        action="Resize i-0a1b2c3d4e5f60001 from m5.xlarge to t3.medium",
        rationale="Average CPU utilization remained at 6.8% over the last 30 days.",
        estimated_monthly_savings_usd=132.20,
        confidence="high",
        state=RecommendationState.PENDING,
        created_at=datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc),
    ),
    RecommendationItem(
        recommendation_id="rec_0002",
        resource_id="vol-09911223344556677",
        category=RecommendationCategory.COST,
        title="Snapshot and delete unattached EBS volume",
        action="Create final snapshot and delete unattached 600 GB gp3 volume vol-09911223344556677",
        rationale="Volume has remained in 'available' (unattached) state for 21 days.",
        estimated_monthly_savings_usd=48.00,
        confidence="high",
        state=RecommendationState.PENDING,
        created_at=datetime(2026, 11, 19, 9, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 11, 19, 9, 15, tzinfo=timezone.utc),
    ),
    RecommendationItem(
        recommendation_id="rec_0003",
        resource_id="i-0a1b2c3d4e5f60002",
        category=RecommendationCategory.SECURITY,
        title="Apply WAF rate limiting against scraper bot traffic",
        action="Attach AWS WAF rate-based rule (100 req/5min per IP) on /api/catalog/export and /api/pricing/search",
        rationale="Automated requests represent 94.1% of 24h traffic and drive $138.20/day in extra egress/compute.",
        estimated_monthly_savings_usd=138.20,
        confidence="high",
        state=RecommendationState.PENDING,
        created_at=datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc),
    ),
    RecommendationItem(
        recommendation_id="rec_0004",
        resource_id="db-prod-orders-01",
        category=RecommendationCategory.BACKUP,
        title="Enable automated daily backups on production RDS",
        action="Set RDS backup retention period to 14 days and trigger an immediate manual snapshot",
        rationale="Critical production database db-prod-orders-01 currently has backup_status='missing'.",
        estimated_monthly_savings_usd=0.0,
        confidence="high",
        state=RecommendationState.PENDING,
        created_at=datetime(2026, 11, 20, 16, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 11, 20, 16, 30, tzinfo=timezone.utc),
    ),
    RecommendationItem(
        recommendation_id="rec_0005",
        resource_id="i-0f9e8d7c6b5a49999",
        category=RecommendationCategory.SECURITY,
        title="Quarantine and terminate unauthorized GPU instance",
        action="Revoke ci-deploy-temp IAM session, isolate sg-0f8899aabbccdd, and terminate i-0f9e8d7c6b5a49999",
        rationale="Launched after anomalous off-hours login from Tor exit IP in unused region ap-southeast-1.",
        estimated_monthly_savings_usd=0.0,
        confidence="high",
        state=RecommendationState.PENDING,
        created_at=datetime(2026, 11, 21, 2, 55, tzinfo=timezone.utc),
        updated_at=datetime(2026, 11, 21, 2, 55, tzinfo=timezone.utc),
    ),
)

_RECOMMENDATIONS_STORE: dict[str, RecommendationItem] = {}


def reset_recommendations_state() -> None:
    """Restore the in-memory recommendations store to its initial static seed."""
    _RECOMMENDATIONS_STORE.clear()
    for item in _SEED_RECOMMENDATIONS:
        _RECOMMENDATIONS_STORE[item.recommendation_id] = item.model_copy(deep=True)


reset_recommendations_state()


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    category: RecommendationCategory | None = Query(default=None),
    state: RecommendationState | None = Query(default=None),
) -> RecommendationsResponse:
    """List cost, security, and backup recommendations with optional category/state filters."""
    items = [
        item.model_copy(deep=True)
        for item in _RECOMMENDATIONS_STORE.values()
        if (category is None or item.category == category)
        and (state is None or item.state == state)
    ]
    total_savings = round(
        sum(
            item.estimated_monthly_savings_usd
            for item in items
            if item.state != RecommendationState.DISMISSED
        ),
        2,
    )
    return RecommendationsResponse(
        total=len(items),
        total_estimated_monthly_savings_usd=total_savings,
        recommendations=items,
    )


@router.post(
    "/recommendations/{recommendation_id}/action",
    response_model=RecommendationActionResponse,
)
def act_on_recommendation(
    recommendation_id: str,
    payload: RecommendationActionRequest,
) -> RecommendationActionResponse:
    """Toggle a recommendation state to 'approved' or 'dismissed'."""
    existing = _RECOMMENDATIONS_STORE.get(recommendation_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recommendation '{recommendation_id}' not found",
        )

    previous_state = existing.state
    new_state = RecommendationState(payload.action)
    updated = existing.model_copy(
        update={
            "state": new_state,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    _RECOMMENDATIONS_STORE[recommendation_id] = updated

    return RecommendationActionResponse(
        recommendation=updated.model_copy(deep=True),
        previous_state=previous_state,
        message=f"Recommendation '{recommendation_id}' updated from '{previous_state.value}' to '{new_state.value}'",
    )
