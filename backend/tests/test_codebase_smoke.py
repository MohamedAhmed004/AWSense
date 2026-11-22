"""General codebase smoke test verifying backend modules, routes, DB pipeline, and frontend fixtures."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
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
    reset_recommendations_state,
)
from app.api.resources import get_resources  # noqa: E402
from app.api.traffic import get_traffic  # noqa: E402
from app.core.database import build_engine, create_tables  # noqa: E402
from app.main import app, health_check, read_root  # noqa: E402
from app.models.entities import BackupStatus, RecommendationState  # noqa: E402
from app.services.mock_generator import MockTelemetryProvider  # noqa: E402
from app.services.repository import (  # noqa: E402
    list_alerts,
    list_recommendations,
    list_resources,
    seed_database,
    update_recommendation_state,
)


@pytest.fixture(autouse=True)
def _reset_recs() -> Generator[None, None, None]:
    reset_recommendations_state()
    yield
    reset_recommendations_state()


def test_fastapi_routes_and_handlers_smoke() -> None:
    """Verify all expected API paths are registered and handler functions return valid payloads."""
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
    }
    assert expected_paths.issubset(openapi_paths)

    assert read_root()["status"] == "ok"
    assert health_check() == {"status": "healthy"}

    overview = get_overview()
    assert 0.0 <= overview.health_score <= 100.0
    assert overview.active_alerts.total >= 1

    resources = get_resources(resource_type=None, region=None, backup_status=None)
    assert resources.summary.total == len(resources.resources) >= 4

    alerts = get_alerts(severity=None, status=None)
    assert alerts.total == len(alerts.alerts) >= 2

    traffic = get_traffic()
    assert traffic.bot_flags.flagged_bot_requests_24h > 0

    recs = get_recommendations(category=None, state=None)
    assert recs.total >= 4
    first_id = recs.recommendations[0].recommendation_id
    toggled = act_on_recommendation(first_id, RecommendationActionRequest(action="approved"))
    assert toggled.recommendation.state == RecommendationState.APPROVED


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
