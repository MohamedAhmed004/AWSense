"""SQLAlchemy ORM entities for AWSense resources, telemetry, alerts, and recommendations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


def _str_enum(enum_cls: type[StrEnum], name: str) -> SqlEnum:
    """Store string enums cleanly across both SQLite and PostgreSQL."""
    return SqlEnum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda items: [item.value for item in items],
    )


class ResourceType(StrEnum):
    EC2 = "ec2"
    EBS = "ebs"
    RDS = "rds"
    S3 = "s3"


class BackupStatus(StrEnum):
    PROTECTED = "protected"
    MISSING = "missing"
    OUTDATED = "outdated"
    NOT_APPLICABLE = "not_applicable"


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class RecommendationCategory(StrEnum):
    COST = "cost"
    SECURITY = "security"
    BACKUP = "backup"


class RecommendationState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"


class CloudResource(Base):
    """Tracked AWS infrastructure resource and its utilization/backup state."""

    __tablename__ = "cloud_resources"

    resource_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_type: Mapped[ResourceType] = mapped_column(
        _str_enum(ResourceType, "resource_type_enum"),
        nullable=False,
        index=True,
    )
    region: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    utilization_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    backup_status: Mapped[BackupStatus] = mapped_column(
        _str_enum(BackupStatus, "backup_status_enum"),
        nullable=False,
        default=BackupStatus.NOT_APPLICABLE,
    )
    last_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monthly_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    metrics: Mapped[list[TelemetryMetric]] = relationship(
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list[SecurityAlert]] = relationship(back_populates="resource")
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="resource",
        cascade="all, delete-orphan",
    )


class TelemetryMetric(Base):
    """Time-series utilization and traffic datapoint for a cloud resource."""

    __tablename__ = "telemetry_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("cloud_resources.resource_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    cpu_utilization: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    network_in_bytes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    network_out_bytes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    resource: Mapped[CloudResource] = relationship(back_populates="metrics")


class SecurityAlert(Base):
    """Correlated security, behavioral, or cost-impact alert."""

    __tablename__ = "security_alerts"

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str | None] = mapped_column(
        ForeignKey("cloud_resources.resource_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[AlertSeverity] = mapped_column(
        _str_enum(AlertSeverity, "alert_severity_enum"),
        nullable=False,
        index=True,
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    correlated_event_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    signal_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[AlertStatus] = mapped_column(
        _str_enum(AlertStatus, "alert_status_enum"),
        nullable=False,
        default=AlertStatus.OPEN,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        index=True,
    )

    resource: Mapped[CloudResource | None] = relationship(back_populates="alerts")


class Recommendation(Base):
    """Actionable cost, security, or backup optimization recommendation."""

    __tablename__ = "recommendations"

    recommendation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("cloud_resources.resource_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[RecommendationCategory] = mapped_column(
        _str_enum(RecommendationCategory, "recommendation_category_enum"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_monthly_savings_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="high")
    state: Mapped[RecommendationState] = mapped_column(
        _str_enum(RecommendationState, "recommendation_state_enum"),
        nullable=False,
        default=RecommendationState.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    resource: Mapped[CloudResource] = relationship(back_populates="recommendations")
