
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.simulate import router
from app.services.auditor import (
    audit_resources,
    summarize_traffic_impact,
)


# Create a small FastAPI app for testing the simulate router.
app = FastAPI()
app.include_router(router)

client = TestClient(app)


# -------------------------
# Auditor tests
# -------------------------

def test_audit_underutilized_ec2():
    resources = [
        {
            "resource_id": "i-test-001",
            "resource_type": "ec2",
            "utilization_pct": 10.0,
            "monthly_cost_usd": 100.0,
            "backup_status": "healthy",
        }
    ]

    findings = audit_resources(resources, [])

    assert len(findings) == 1
    assert findings[0]["issue"] == "underutilized_ec2"
    assert findings[0]["estimated_monthly_savings_usd"] == 50.0


def test_ec2_at_threshold_is_not_flagged():
    resources = [
        {
            "resource_id": "i-test-002",
            "resource_type": "ec2",
            "utilization_pct": 15.0,
            "monthly_cost_usd": 100.0,
            "backup_status": "healthy",
        }
    ]

    findings = audit_resources(resources, [])

    assert findings == []


def test_audit_unattached_ebs():
    resources = [
        {
            "resource_id": "vol-test-001",
            "resource_type": "ebs",
            "status": "available",
            "monthly_cost_usd": 40.0,
            "backup_status": "healthy",
            "metadata": {"attached": False},
        }
    ]

    findings = audit_resources(resources, [])

    assert len(findings) == 1
    assert findings[0]["issue"] == "unattached_ebs"
    assert findings[0]["estimated_monthly_savings_usd"] == 40.0


def test_audit_missing_and_outdated_backups():
    resources = [
        {
            "resource_id": "db-test-001",
            "resource_type": "rds",
            "backup_status": "missing",
            "monthly_cost_usd": 100.0,
        },
        {
            "resource_id": "db-test-002",
            "resource_type": "rds",
            "backup_status": "outdated",
            "monthly_cost_usd": 200.0,
        },
    ]

    findings = audit_resources(resources, [])

    assert len(findings) == 2
    assert findings[0]["issue"] == "missing_backup"
    assert findings[1]["issue"] == "outdated_backup"


def test_summarize_traffic_impact():
    traffic_logs = [
        {
            "endpoint": "/api/products",
            "request_count": 1000,
            "bot_requests": 800,
            "bot_flagged": True,
            "network_out_gb": 10.0,
        },
        {
            "endpoint": "/api/login",
            "request_count": 1000,
            "bot_requests": 200,
            "bot_flagged": False,
            "network_out_gb": 5.0,
        },
    ]

    summary = summarize_traffic_impact(traffic_logs)

    assert summary["total_requests"] == 2000
    assert summary["bot_share_pct"] == 50.0
    assert summary["flagged_endpoints"] == ["/api/products"]
    assert summary["estimated_daily_cost_impact_usd"] == 0.72
    assert summary["estimated_monthly_cost_impact_usd"] == 21.6


# -------------------------
# Simulation API tests
# -------------------------

def test_simulate_iam_breach():
    response = client.post(
        "/api/v1/simulate",
        json={"scenario": "iam_breach"},
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {
        "incident",
        "findings",
        "recommendations",
    }

    assert isinstance(data["incident"], dict)
    assert data["incident"]["title"] == "Potential IAM Security Breach"
    assert isinstance(data["incident"]["risk_score"], int)
    assert data["incident"]["severity"] == "critical"
    assert isinstance(data["incident"]["summary"], str)
    assert isinstance(data["incident"]["recommended_actions"], list)

    assert isinstance(data["findings"], list)
    assert len(data["findings"]) > 0
    assert all(isinstance(item, str) for item in data["findings"])

    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0
    assert all(isinstance(item, dict) for item in data["recommendations"])


def test_simulate_bot_traffic():
    response = client.post(
        "/api/v1/simulate",
        json={"scenario": "bot_traffic"},
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {
        "incident",
        "findings",
        "recommendations",
    }

    assert isinstance(data["incident"], dict)
    assert data["incident"]["title"] == "Abnormal Bot Traffic Detected"
    assert isinstance(data["incident"]["risk_score"], int)
    assert data["incident"]["severity"] == "critical"
    assert isinstance(data["incident"]["summary"], str)
    assert isinstance(data["incident"]["recommended_actions"], list)

    assert isinstance(data["findings"], list)
    assert len(data["findings"]) > 0
    assert all(isinstance(item, str) for item in data["findings"])

    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0
    assert all(isinstance(item, dict) for item in data["recommendations"])


def test_simulate_resource_waste():
    response = client.post(
        "/api/v1/simulate",
        json={"scenario": "resource_waste"},
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {
        "incident",
        "findings",
        "recommendations",
    }

    assert isinstance(data["incident"], dict)
    assert data["incident"]["title"] == "Cloud Resource Waste Detected"
    assert isinstance(data["incident"]["risk_score"], int)
    assert data["incident"]["severity"] == "high"
    assert isinstance(data["incident"]["summary"], str)
    assert isinstance(data["incident"]["recommended_actions"], list)

    assert isinstance(data["findings"], list)
    assert len(data["findings"]) > 0
    assert all(isinstance(item, str) for item in data["findings"])

    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0
    assert all(isinstance(item, dict) for item in data["recommendations"])


def test_simulate_invalid_scenario():
    response = client.post(
        "/api/v1/simulate",
        json={"scenario": "invalid_scenario"},
    )

    assert response.status_code == 422
