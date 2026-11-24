
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    Recommendation,
    RecommendationCategory,
    RecommendationState,
)
from app.services.repository import (
    list_recommendations,
    update_recommendation_state,
)

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
    """State transition payload."""

    action: Literal["approved", "dismissed"]


class RecommendationActionResponse(BaseModel):
    """Response after changing recommendation state."""

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
    """Restore the in-memory seed recommendations."""

    _RECOMMENDATIONS_STORE.clear()

    for item in _SEED_RECOMMENDATIONS:
        _RECOMMENDATIONS_STORE[item.recommendation_id] = (
            item.model_copy(deep=True)
        )


reset_recommendations_state()


def _datetime_sort_key(value: datetime) -> float:
    """Normalize naive and timezone-aware datetimes for sorting."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.timestamp()


def _convert_db_recommendation(
    recommendation: Recommendation,
) -> RecommendationItem:
    """Convert a SQLAlchemy Recommendation into the API response schema."""

    return RecommendationItem(
        recommendation_id=recommendation.recommendation_id,
        resource_id=recommendation.resource_id,
        category=recommendation.category,
        title=recommendation.title,
        action=recommendation.action,
        rationale=recommendation.rationale,
        estimated_monthly_savings_usd=recommendation.estimated_monthly_savings_usd,
        confidence=recommendation.confidence,
        state=recommendation.state,
        created_at=recommendation.created_at,
        updated_at=recommendation.updated_at,
    )


@router.get(
    "/recommendations",
    response_model=RecommendationsResponse,
)
def get_recommendations(
    category: RecommendationCategory | None = Query(default=None),
    state: RecommendationState | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RecommendationsResponse:
    """List sample and database recommendations."""

    # Keep existing seed recommendations.
    recommendations_by_id = {
        item.recommendation_id: item.model_copy(deep=True)
        for item in _RECOMMENDATIONS_STORE.values()
    }

    # Depends is not resolved when the function is called directly.
    # Only query SQLite when a real SQLAlchemy Session is available.
    if isinstance(db, Session):
        database_recommendations = list_recommendations(db)
    else:
        database_recommendations = []

    # Database records override seed records with the same ID.
    for recommendation in database_recommendations:
        item = _convert_db_recommendation(recommendation)
        recommendations_by_id[item.recommendation_id] = item

    items = [
        item
        for item in recommendations_by_id.values()
        if (category is None or item.category == category)
        and (state is None or item.state == state)
    ]

    # Sort safely when SQLite returns naive datetimes
    # and seed recommendations contain timezone-aware datetimes.
    items.sort(
        key=lambda item: (
            _datetime_sort_key(item.created_at),
            item.estimated_monthly_savings_usd,
        ),
        reverse=True,
    )

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
    db: Session = Depends(get_db),
) -> RecommendationActionResponse:
    """Update recommendation state in the database or seed store."""

    new_state = RecommendationState(payload.action)

    # Query the database only when a real Session is available.
    existing_db_record = (
        db.get(Recommendation, recommendation_id)
        if isinstance(db, Session)
        else None
    )

    if existing_db_record is not None:
        previous_state = existing_db_record.state

        updated_record = update_recommendation_state(
            db,
            recommendation_id,
            new_state,
        )

        updated_item = _convert_db_recommendation(updated_record)

    else:
        # Preserve support for the original in-memory seed recommendations.
        existing = _RECOMMENDATIONS_STORE.get(recommendation_id)

        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recommendation '{recommendation_id}' not found",
            )

        previous_state = existing.state

        updated_item = existing.model_copy(
            update={
                "state": new_state,
                "updated_at": datetime.now(timezone.utc),
            }
        )

        _RECOMMENDATIONS_STORE[recommendation_id] = (
            updated_item.model_copy(deep=True)
        )

    return RecommendationActionResponse(
        recommendation=updated_item,
        previous_state=previous_state,
        message=(
            f"Recommendation '{recommendation_id}' updated "
            f"from '{previous_state.value}' to '{new_state.value}'"
        ),
    )
