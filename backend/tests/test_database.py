"""Standalone verification test for database table creation and ORM roundtrips."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import sessionmaker

# Allow running directly from repo root or backend/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import build_engine, create_tables  # noqa: E402
from app.models.entities import (  # noqa: E402
    AlertSeverity,
    AlertStatus,
    BackupStatus,
    CloudResource,
    Recommendation,
    RecommendationCategory,
    RecommendationState,
    ResourceType,
    SecurityAlert,
    TelemetryMetric,
)


def test_create_tables_and_roundtrip(tmp_path: Path) -> None:
    """Verify create_tables() and insert/query across all four ORM tables."""
    db_file = tmp_path / "test_awsense.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    create_tables(test_engine)

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    now = datetime.now(timezone.utc)

    with session_factory() as session:
        resource = CloudResource(
            resource_id="i-0abcd1234efgh5678",
            name="prod-web-01",
            resource_type=ResourceType.EC2,
            region="us-east-1",
            status="running",
            utilization_pct=7.2,
            backup_status=BackupStatus.PROTECTED,
            last_backup_at=now,
            monthly_cost_usd=142.50,
            metadata_json={"instance_type": "t3.xlarge"},
        )
        session.add(resource)
        session.flush()

        metric = TelemetryMetric(
            resource_id=resource.resource_id,
            timestamp=now,
            cpu_utilization=7.2,
            network_in_bytes=12500.0,
            network_out_bytes=8400.0,
            request_count=420,
            anomaly_score=0.12,
        )
        alert = SecurityAlert(
            alert_id="alert_0001",
            resource_id=resource.resource_id,
            alert_type="behavioral_anomaly",
            severity=AlertSeverity.HIGH,
            risk_score=84.5,
            title="Unusual IAM activity followed by EC2 launch",
            correlated_event_ids=["ct-101", "cw-202"],
            signal_breakdown={"ml_score": 0.91, "iam_risk": "high"},
            ai_summary="IAM user launched an instance outside baseline hours.",
            recommended_actions=["Review IAM access keys", "Inspect instance i-0abcd1234efgh5678"],
            status=AlertStatus.OPEN,
        )
        recommendation = Recommendation(
            recommendation_id="rec_0001",
            resource_id=resource.resource_id,
            category=RecommendationCategory.COST,
            title="Downsize underutilized EC2 instance",
            action="Resize t3.xlarge to t3.medium",
            rationale="Average CPU utilization stayed below 8% over 30 days.",
            estimated_monthly_savings_usd=71.25,
            confidence="high",
            state=RecommendationState.PENDING,
        )

        session.add_all([metric, alert, recommendation])
        session.commit()

    with session_factory() as session:
        fetched_resource = session.get(CloudResource, "i-0abcd1234efgh5678")
        assert fetched_resource is not None
        assert fetched_resource.resource_type == ResourceType.EC2
        assert len(fetched_resource.metrics) == 1
        assert len(fetched_resource.alerts) == 1
        assert len(fetched_resource.recommendations) == 1

        fetched_metric = session.query(TelemetryMetric).one()
        assert fetched_metric.request_count == 420

        fetched_alert = session.get(SecurityAlert, "alert_0001")
        assert fetched_alert is not None
        assert fetched_alert.severity == AlertSeverity.HIGH
        assert fetched_alert.correlated_event_ids == ["ct-101", "cw-202"]

        fetched_rec = session.get(Recommendation, "rec_0001")
        assert fetched_rec is not None
        assert fetched_rec.state == RecommendationState.PENDING
        assert fetched_rec.estimated_monthly_savings_usd == 71.25

    test_engine.dispose()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_create_tables_and_roundtrip(Path(tmp))
    print("Database schema and roundtrip verification passed.")
