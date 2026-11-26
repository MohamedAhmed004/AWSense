"""General codebase smoke test verifying backend modules, routes, DB pipeline, and frontend fixtures."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.alerts import get_alerts  # noqa: E402
from app.api.overview import get_overview  # noqa: E402
from app.api.recommendations import (  # noqa: E402
    RecommendationActionRequest,
    act_on_recommendation,
    get_recommendations,
)
from app.api.resources import get_resources  # noqa: E402
from app.api.traffic import get_traffic  # noqa: E402
from app.core import database  # noqa: E402
from app.core.database import build_engine, create_tables, get_db  # noqa: E402
from app.main import app, health_check, read_root  # noqa: E402
from app.models.entities import BackupStatus, RecommendationState  # noqa: E402
from app.services.ml_eval import evaluate_ml  # noqa: E402
from app.services.mock_generator import MockTelemetryProvider  # noqa: E402
from app.services.repository import (  # noqa: E402
    list_alerts,
    list_recommendations,
    list_resources,
    seed_database,
    update_recommendation_state,
)
from app.services.telemetry_provider import (  # noqa: E402
    Boto3TelemetryProvider,
    TelemetryProvider,
    get_telemetry_provider,
)


def test_fastapi_routes_and_handlers_smoke(tmp_path: Path) -> None:
    """Verify all expected API paths are registered and DB-backed handlers return valid payloads."""
    openapi_paths = set(app.openapi()["paths"].keys())
    expected_paths = {
        "/",
        "/api/v1/health",
        "/api/v1/overview",
        "/api/v1/resources",
        "/api/v1/alerts",
        "/api/v1/traffic",
        "/api/v1/recommendations",
        "/api/v1/recommendations/{recommendation_id}/action",
        "/api/v1/simulate",
    }
    assert expected_paths.issubset(openapi_paths)

    assert read_root()["status"] == "ok"
    assert health_check() == {"status": "healthy"}

    db_file = tmp_path / "handlers_smoke.db"
    engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    create_tables(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with session_factory() as session:
        seed_database(session)

        overview = get_overview(db=session)
        assert 0.0 <= overview.health_score <= 100.0
        assert overview.active_alerts.total >= 1

        resources = get_resources(resource_type=None, region=None, backup_status=None, db=session)
        assert resources.summary.total == len(resources.resources) >= 14

        alerts = get_alerts(severity=None, status=None, db=session)
        assert alerts.total == len(alerts.alerts) >= 2

        traffic = get_traffic()
        assert traffic.bot_flags.flagged_bot_requests_24h > 0

        recs = get_recommendations(category=None, state=None, db=session)
        assert recs.total >= 4
        first_id = recs.recommendations[0].recommendation_id
        toggled = act_on_recommendation(
            first_id,
            RecommendationActionRequest(action="approved"),
            db=session,
        )
        assert toggled.recommendation.state == RecommendationState.APPROVED
        restored = act_on_recommendation(
            first_id,
            RecommendationActionRequest(action="pending"),
            db=session,
        )
        assert restored.recommendation.state == RecommendationState.PENDING

    engine.dispose()


def test_end_to_end_provider_correlator_and_db_pipeline(tmp_path: Path) -> None:
    """Verify MockTelemetryProvider -> correlator -> ORM seed -> repository queries end-to-end."""
    db_file = tmp_path / "smoke.db"
    engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    create_tables(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    provider = MockTelemetryProvider(seed=42, include_anomalies=True)
    with session_factory() as session:
        counts = seed_database(session, provider=provider)
        assert counts["resources"] >= 14
        assert counts["metrics"] >= 100
        assert counts["alerts"] >= 2
        assert counts["recommendations"] >= 4

        missing_backups = list_resources(session, backup_status=BackupStatus.MISSING)
        assert any(r.resource_id == "db-prod-orders-01" for r in missing_backups)

        alerts = list_alerts(session)
        assert any(a.alert_type == "iam_compute_surge" for a in alerts)
        assert any(a.alert_type == "bot_traffic_cost_spike" for a in alerts)

        recs = list_recommendations(session)
        updated = update_recommendation_state(session, recs[0].recommendation_id, "approved")
        assert updated.state == RecommendationState.APPROVED

    engine.dispose()


def test_frontend_structure_and_mock_fixtures_smoke() -> None:
    """Verify required frontend files exist and mock ES module fixtures load cleanly in Node."""
    frontend_dir = REPO_ROOT / "frontend"
    required_files = [
        "package.json",
        "index.html",
        "src/App.jsx",
        "src/components/Layout.jsx",
        "src/components/SimulatePanel.jsx",
        "src/components/ui.jsx",
        "src/pages/Overview.jsx",
        "src/pages/Resources.jsx",
        "src/pages/Security.jsx",
        "src/pages/Traffic.jsx",
        "src/pages/Recommendations.jsx",
        "src/services/api.js",
        "src/mock/index.js",
    ]
    for rel_path in required_files:
        assert (frontend_dir / rel_path).is_file(), f"Missing frontend file: {rel_path}"

    node_bin = shutil.which("node")
    if node_bin is None:
        pytest.skip("Node.js not available in PATH for ES module fixture verification")

    mock_index_uri = (frontend_dir / "src" / "mock" / "index.js").as_uri()
    script = (
        f"import * as m from '{mock_index_uri}'; "
        "console.log(JSON.stringify({"
        "healthScore: m.overview.healthScore, "
        "resources: m.resources.length, "
        "alerts: m.alerts.length, "
        "trafficTotal: m.traffic.totalRequests, "
        "recommendations: m.recommendations.length"
        "}));"
    )
    proc = subprocess.run(
        [node_bin, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(proc.stdout)
    assert 0 <= summary["healthScore"] <= 100
    assert summary["resources"] >= 5
    assert summary["alerts"] >= 2
    assert summary["trafficTotal"] > 0
    assert summary["recommendations"] >= 4


def test_ml_eval_evaluate_ml_smoke() -> None:
    """Verify ml_eval.evaluate_ml() runs the IsolationForest benchmark and scoring pipeline."""
    report = evaluate_ml()

    assert report["training_rows"] >= 100
    assert report["evaluation_rows"] >= 100
    assert 0.95 <= report["precision"] <= 1.0
    assert 0.95 <= report["recall"] <= 1.0
    assert report["f1"] >= 0.95
    assert 0.0 <= report["false_positive_rate"] <= 0.10
    assert report["score_separation"] > 0.0
    assert report["inference_ms_total"] > 0.0

    cm = report["confusion_matrix"]
    assert set(cm.keys()) == {"tn", "fp", "fn", "tp"}
    assert sum(cm.values()) == report["evaluation_rows"]

    assert len(report["incidents"]) >= 1
    assert any(item["matches_injected_anomaly"] for item in report["incidents"])
    for item in report["incidents"]:
        assert 0.0 <= item["risk_score"] <= 100.0
        assert item["severity"] in {"low", "medium", "high", "critical"}


def test_get_telemetry_provider_aws_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_telemetry_provider('aws') builds a Boto3TelemetryProvider safely offline."""
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_PROFILE", "awsense-readonly")

    provider = get_telemetry_provider("aws")
    assert isinstance(provider, TelemetryProvider)
    assert isinstance(provider, Boto3TelemetryProvider)
    assert provider.source_name == "aws"
    assert provider.region_name == "eu-west-1"
    assert provider.profile_name == "awsense-readonly"

    monkeypatch.setenv("DATA_SOURCE", "aws")
    env_provider = get_telemetry_provider()
    assert isinstance(env_provider, Boto3TelemetryProvider)

    # Clear AWS_PROFILE before instantiating an offline Session so botocore
    # does not look up a non-existent profile in ~/.aws/config.
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    session = boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="eu-west-1",
    )
    stub_plan = {
        "ec2": [
            ("describe_instances", {"Reservations": []}),
            ("describe_volumes", {"Volumes": []}),
            ("describe_instances", {"Reservations": []}),
        ],
        "rds": [("describe_db_instances", {"DBInstances": []})],
        "s3": [("list_buckets", {"Buckets": []})],
        "cloudwatch": [
            ("list_metrics", {"Metrics": []}),
            ("list_metrics", {"Metrics": []}),
        ],
        "cloudtrail": [("lookup_events", {"Events": []})],
        "ce": [("get_cost_and_usage", {"ResultsByTime": []})],
    }
    clients = {}
    stubbers = []
    for svc, responses in stub_plan.items():
        client = session.client(svc, region_name="eu-west-1")
        stubber = Stubber(client)
        for op, payload in responses:
            stubber.add_response(op, payload)
        stubber.activate()
        clients[svc] = client
        stubbers.append(stubber)

    aws = Boto3TelemetryProvider(
        region_name="eu-west-1",
        profile_name="awsense-readonly",
        session=session,
        clients=clients,
    )
    assert aws.get_resources() == []
    assert aws.get_metrics() == []
    assert aws.get_cloudtrail_events() == []
    assert aws.get_traffic_logs() == []
    assert aws.get_cost_usage() == []
    for stubber in stubbers:
        stubber.assert_no_pending_responses()


def test_simulate_endpoint_compatible_with_simulate_panel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify POST /api/v1/simulate responses satisfy SimulatePanel.jsx's parser and scenarios."""
    simulate_panel = (
        REPO_ROOT / "frontend" / "src" / "components" / "SimulatePanel.jsx"
    ).read_text(encoding="utf-8")
    assert "`${BASE}/simulate`" in simulate_panel

    ui_src = (REPO_ROOT / "frontend" / "src" / "components" / "ui.jsx").read_text(
        encoding="utf-8",
    )
    for ui_level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        assert ui_level in ui_src

    db_file = tmp_path / "simulate_smoke.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    test_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(database, "SessionLocal", test_factory)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    def override_get_db():
        db = test_factory()
        try:
            yield db
        finally:
            db.close()

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            for scenario in ("iam_breach", "bot_traffic", "resource_waste"):
                assert f"id: '{scenario}'" in simulate_panel

                resp = client.post("/api/v1/simulate", json={"scenario": scenario})
                assert resp.status_code == 200
                body = resp.json()

                # Exact shape parsed by parseSimulationResponse(body) in SimulatePanel.jsx
                assert set(body.keys()) >= {"incident", "findings", "recommendations"}
                incident = body["incident"]
                assert isinstance(incident["risk_score"], (int, float))
                assert 0 <= incident["risk_score"] <= 100
                assert str(incident["severity"]).upper() in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
                assert isinstance(incident["title"], str) and incident["title"].strip()
                assert isinstance(incident["summary"], str) and incident["summary"].strip()

                actions = incident["recommended_actions"]
                assert isinstance(actions, list) and len(actions) > 0
                assert all(isinstance(step, str) and step.strip() for step in actions)

                findings = body["findings"]
                assert isinstance(findings, list) and len(findings) > 0
                assert all(isinstance(item, str) and item.strip() for item in findings)

                recs = body["recommendations"]
                assert isinstance(recs, list) and len(recs) > 0
                assert all(
                    isinstance(rec, dict)
                    and isinstance(rec.get("action") or rec.get("title"), str)
                    and (rec.get("action") or rec.get("title")).strip()
                    for rec in recs
                )

            alerts_resp = client.get("/api/v1/alerts")
            assert alerts_resp.status_code == 200
            alert_ids = {item["alert_id"] for item in alerts_resp.json()["alerts"]}
            assert {"sim_alert_iam_breach", "sim_alert_bot_traffic", "sim_alert_resource_waste"}.issubset(
                alert_ids,
            )
    finally:
        app.dependency_overrides = previous_overrides
        test_engine.dispose()

