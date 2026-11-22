"""Unit tests for the database repository and idempotent mock seeder."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import build_engine, create_tables  # noqa: E402
from app.models.entities import (  # noqa: E402
    AlertSeverity,
    AlertStatus,
    BackupStatus,
    CloudResource,
    RecommendationCategory,
    RecommendationState,
    ResourceType,
    SecurityAlert,
    TelemetryMetric,
)
from app.services.correlator import correlate_signals  # noqa: E402
from app.services.mock_generator import MockTelemetryProvider  # noqa: E402
from app.services.repository import (  # noqa: E402
    list_alerts,
    list_recommendations,
    list_resources,
    save_alert,
    seed_database,
    update_recommendation_state,
)


@pytest.fixture
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Yield an isolated SQLite session initialized with all ORM tables."""
    db_file = tmp_path / "repo_test.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    create_tables(test_engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    with factory() as session:
        yield session
    test_engine.dispose()


def test_seed_database_is_idempotent_and_supports_force(db_session: Session) -> None:
    """First seed populates all 4 tables; second call is a no-op unless force=True."""
    provider = MockTelemetryProvider(seed=42, include_anomalies=True)

    first_counts = seed_database(db_session, provider=provider)
    assert first_counts["resources"] >= 14  # 6 base + 8 rogue EC2s
    assert first_counts["metrics"] >= 100
    assert first_counts["alerts"] >= 2
    assert first_counts["recommendations"] >= 4

    # Second call without force inserts nothing and does not duplicate metrics.
    second_counts = seed_database(db_session, provider=provider)
    assert second_counts == {"resources": 0, "metrics": 0, "alerts": 0, "recommendations": 0}
    assert db_session.scalar(select(func.count()).select_from(TelemetryMetric)) == first_counts["metrics"]

    # Force re-seed resets and repopulates cleanly.
    forced_counts = seed_database(db_session, provider=provider, force=True)
    assert forced_counts == first_counts


def test_list_resources_and_alerts_filters(db_session: Session) -> None:
    """Query helpers honor enum/string filters and sort deterministically."""
    seed_database(db_session)

    all_resources = list_resources(db_session)
    assert len(all_resources) >= 14

    ec2_only = list_resources(db_session, resource_type=ResourceType.EC2)
    assert ec2_only
    assert all(r.resource_type == ResourceType.EC2 for r in ec2_only)

    ap_resources = list_resources(db_session, region="ap-southeast-1")
    assert len(ap_resources) == 8

    missing_backups = list_resources(db_session, backup_status="missing")
    assert any(r.resource_id == "db-prod-orders-01" for r in missing_backups)
    assert all(r.backup_status == BackupStatus.MISSING for r in missing_backups)

    all_alerts = list_alerts(db_session)
    assert len(all_alerts) >= 2
    assert all_alerts == sorted(all_alerts, key=lambda a: (-a.risk_score, -a.created_at.timestamp()))

    high_alerts = list_alerts(db_session, severity="high", status=AlertStatus.OPEN)
    assert all(a.severity == AlertSeverity.HIGH and a.status == AlertStatus.OPEN for a in high_alerts)

    with pytest.raises(ValueError):
        list_resources(db_session, resource_type="lambda")


def test_recommendations_filters_and_state_transitions(db_session: Session) -> None:
    """Recommendations filter properly and persist pending/approved/dismissed transitions."""
    seed_database(db_session)

    all_recs = list_recommendations(db_session)
    categories = {r.category for r in all_recs}
    assert {
        RecommendationCategory.COST,
        RecommendationCategory.SECURITY,
        RecommendationCategory.BACKUP,
    }.issubset(categories)

    target = all_recs[0]
    assert target.state == RecommendationState.PENDING

    approved = update_recommendation_state(db_session, target.recommendation_id, "approved")
    assert approved.state == RecommendationState.APPROVED

    dismissed = update_recommendation_state(
        db_session, target.recommendation_id, RecommendationState.DISMISSED
    )
    assert dismissed.state == RecommendationState.DISMISSED

    restored = update_recommendation_state(db_session, target.recommendation_id, "pending")
    assert restored.state == RecommendationState.PENDING

    pending_only = list_recommendations(db_session, state=RecommendationState.PENDING)
    assert any(r.recommendation_id == target.recommendation_id for r in pending_only)

    with pytest.raises(LookupError):
        update_recommendation_state(db_session, "rec_does_not_exist", "approved")

    with pytest.raises(ValueError):
        update_recommendation_state(db_session, target.recommendation_id, "delete_now")


def test_save_alert_accepts_dict_orm_and_correlated_incident(db_session: Session) -> None:
    """save_alert persists dicts, ORM instances, and CorrelatedIncident objects with upsert."""
    seed_database(db_session)

    # 1. Dict insert + upsert update.
    created = save_alert(
        db_session,
        {
            "alert_id": "alert_custom_1",
            "resource_id": "i-0baseweb01",
            "alert_type": "bot_traffic",
            "severity": "high",
            "risk_score": 81.5,
            "title": "Simulated scraper spike",
            "correlated_event_ids": ["tr-9001", "cw-0001"],
            "signal_breakdown": {"traffic_anomaly": 92.0},
            "ai_summary": "Repetitive requests saturated web tier.",
            "recommended_actions": ["Enable WAF rate limit"],
            "status": "open",
        },
    )
    assert created.alert_id == "alert_custom_1"
    assert created.severity == AlertSeverity.HIGH

    updated = save_alert(
        db_session,
        {
            "alert_id": "alert_custom_1",
            "resource_id": "i-0baseweb01",
            "title": "Simulated scraper spike (investigating)",
            "status": "investigating",
            "risk_score": 85.0,
        },
    )
    assert updated.status == AlertStatus.INVESTIGATING
    assert updated.risk_score == 85.0
    assert updated.ai_summary == "Repetitive requests saturated web tier."

    # 2. CorrelatedIncident object persistence.
    incidents = correlate_signals(
        metric_spikes=[
            {
                "event_id": "cw-sim-1",
                "timestamp": "2026-11-22T18:00:00Z",
                "resource_id": "i-0baseweb01",
                "metric_name": "RequestCount",
                "value": 1_800_000,
                "baseline": 120_000,
                "region": "us-east-1",
            }
        ],
        cost_deltas=[
            {
                "event_id": "ce-sim-1",
                "timestamp": "2026-11-22T18:20:00Z",
                "service": "AWSDataTransfer",
                "delta_usd": 195.0,
                "baseline_usd": 10.0,
                "resource_id": "i-0baseweb01",
                "region": "us-east-1",
            }
        ],
    )
    assert len(incidents) == 1
    persisted_inc = save_alert(db_session, incidents[0])
    assert persisted_inc.alert_id == f"alert_{incidents[0].incident_id}"
    assert persisted_inc.resource_id == "i-0baseweb01"

    # 3. Direct ORM instance persistence.
    direct = SecurityAlert(
        alert_id="alert_orm_1",
        resource_id=None,
        alert_type="iam_anomaly",
        severity=AlertSeverity.LOW,
        risk_score=22.0,
        title="Minor IAM baseline notice",
    )
    saved_orm = save_alert(db_session, direct)
    assert db_session.get(SecurityAlert, saved_orm.alert_id) is not None
