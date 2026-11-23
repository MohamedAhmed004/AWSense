"""Optimization, security, and backup recommendation endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import Recommendation, RecommendationCategory, RecommendationState
from app.services.repository import list_recommendations, update_recommendation_state

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

    action: Literal["pending", "approved", "dismissed"]


class RecommendationActionResponse(BaseModel):
    """Response payload returned after toggling a recommendation's state."""

    recommendation: RecommendationItem
    previous_state: RecommendationState
    message: str


def _to_item(row: Recommendation) -> RecommendationItem:
    return RecommendationItem(
        recommendation_id=row.recommendation_id,
        resource_id=row.resource_id,
        category=row.category,
        title=row.title,
        action=row.action,
        rationale=row.rationale,
        estimated_monthly_savings_usd=row.estimated_monthly_savings_usd,
        confidence=row.confidence,
        state=row.state,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    category: RecommendationCategory | None = Query(default=None),
    state: RecommendationState | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RecommendationsResponse:
    """List cost, security, and backup recommendations with optional category/state filters."""
    rows = list_recommendations(db, category=category, state=state)
    items = [_to_item(row) for row in rows]
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
    """Transition a recommendation state to 'pending', 'approved', or 'dismissed'."""
    existing = db.get(Recommendation, recommendation_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recommendation '{recommendation_id}' not found",
        )

    previous_state = existing.state
    updated = update_recommendation_state(db, recommendation_id, payload.action)

    return RecommendationActionResponse(
        recommendation=_to_item(updated),
        previous_state=previous_state,
        message=(
            f"Recommendation '{recommendation_id}' updated from "
            f"'{previous_state.value}' to '{updated.state.value}'"
        ),
    )
