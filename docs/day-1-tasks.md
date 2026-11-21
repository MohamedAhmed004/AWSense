# Day 1 Tasks

5 isolated tasks. Each targets separate files and uses self-contained sample data so all 5 can be built and verified in parallel.

---

## Task 1: Database Setup & ORM Models
**Files:** `backend/app/core/database.py`, `backend/app/models/entities.py`, `backend/.env.example`

* [ ] Configure SQLAlchemy database connection (PostgreSQL via env `DATABASE_URL` with SQLite fallback for local runs).
* [ ] Define ORM models for:
  * `CloudResource` (resource ID, type `ec2|ebs|rds|s3`, region, status, CPU/utilization, backup status, monthly cost)
  * `TelemetryMetric` (resource ID, timestamp, CPU, network in/out, request count)
  * `SecurityAlert` (alert ID, severity, risk score, correlated event IDs, AI summary, status, timestamp)
  * `Recommendation` (recommendation ID, resource ID, category `cost|security|backup`, action, estimated savings, state `pending|approved|dismissed`)
* [ ] Add a `create_tables()` startup helper.
* **Verify:** Run a standalone Python snippet that calls `create_tables()` and inserts/queries 1 sample row per table.

---

## Task 2: Telemetry Provider & Mock AWS Generator
**Files:** `backend/app/services/telemetry_provider.py`, `backend/app/services/mock_generator.py`

* [ ] Define a base `TelemetryProvider` interface with methods: `get_resources()`, `get_metrics()`, `get_cloudtrail_events()`, `get_traffic_logs()`, and `get_cost_usage()`.
* [ ] Add a `Boto3TelemetryProvider` stub class implementing the interface signatures (raising `NotImplementedError` or returning empty sets until AWS credentials are added).
* [ ] Implement `MockTelemetryProvider` backed by `mock_generator.py` generating realistic JSON payloads for:
  * **Normal baseline:** 30-day steady CPU/network/request/cost curves.
  * **Resource waste & backup gaps:** Underutilized EC2 (`~7%` CPU), unattached EBS volumes, RDS instance missing recent backup/snapshot.
  * **IAM + compute anomaly:** Unusual IAM login (off-hours/new region) + 8 new EC2 instances + security group change + network/cost jump.
  * **Automated bot traffic:** High-frequency repetitive endpoint requests (`~2.4M` scale) + correlated CPU/network spike.
* **Verify:** Run `python -m app.services.mock_generator` (or a quick script) and confirm valid JSON output for all 5 provider methods.

---

## Task 3: API Routes & Correlation Engine
**Files:** `backend/app/api/overview.py`, `backend/app/api/resources.py`, `backend/app/api/alerts.py`, `backend/app/api/traffic.py`, `backend/app/api/recommendations.py`, `backend/app/services/correlator.py`

* [ ] Implement FastAPI `APIRouter` modules (prefix `/api/v1`) returning clean Pydantic response models using local static sample data:
  * `GET /overview` — health score, total monthly savings, active alert counts, cost/usage trend series.
  * `GET /resources` — resource inventory, utilization, backup protection status.
  * `GET /alerts` — correlated security/cost incidents, severity, risk score breakdown, summary text.
  * `GET /traffic` — request rate timeline, suspicious endpoint patterns, bot flags, cost impact.
  * `GET /recommendations` & `POST /recommendations/{id}/action` — list recommendations and toggle `approved` / `dismissed`.
* [ ] Implement `correlator.py` with pure Python functions taking lists of CloudTrail events, metric spikes, and cost deltas and grouping related signals within a time window into correlated incident objects.
* **Verify:** Test all routers with FastAPI `TestClient` and run unit tests for `correlator.py`.

---

## Task 4: ML Anomaly Detection, Risk Scoring & AI Explainer
**Files:** `backend/app/services/ml_detector.py`, `backend/app/services/risk_scorer.py`, `backend/app/services/ai_explainer.py`

* [ ] Implement `ml_detector.py` using Scikit-learn `IsolationForest` trained on synthetic normal numeric series (CPU, network in/out, request rate) to return a normalized `0.0–1.0` anomaly score per data point/window.
* [ ] Implement `risk_scorer.py` computing a unified risk score (`0–100`) and level (`LOW | MEDIUM | HIGH | CRITICAL`) from weighted inputs: `ml_score`, `iam_risk`, `resource_impact`, `cost_impact`, and `traffic_anomaly`.
* [ ] Implement `ai_explainer.py` taking a correlated incident dictionary and generating a plain-English summary + numbered remediation steps via an LLM API (configured by env key), with a deterministic template fallback when no key is set.
* **Verify:** Run a `pytest` suite passing sample normal and anomalous arrays/incidents through all three modules.

---

## Task 5: Frontend App Shell & Dashboard Views
**Files:** `frontend/` (Vite + React + Tailwind CSS + Recharts, replacing `frontend/init.txt`)

* [ ] Initialize a Vite + React + Tailwind CSS app inside `frontend/` with routing and dark-mode dashboard layout (sidebar + top bar).
* [ ] Create local mock fixture files inside `frontend/src/mock/` so all views render without a running backend.
* [ ] Build the 5 dashboard pages:
  * **Overview:** KPI stat cards (Cloud Health, Active Alerts, Monthly Savings, Risk Level) + time-series chart.
  * **Resources:** Filterable resource table showing CPU/utilization, status badges, and backup protection warnings.
  * **Security:** Alert feed with Risk Score breakdown and AI incident summary panel.
  * **Traffic:** Request volume vs. CPU/cost correlation chart and flagged bot/scraper patterns.
  * **Recommendations:** Action cards showing estimated savings, confidence, and local state `Approve` / `Dismiss` buttons.
* [ ] Add a clean `src/services/api.js` wrapper ready to switch from local fixtures to `http://localhost:8000/api/v1`.
* **Verify:** `npm run build` passes with zero errors and all 5 routes render cleanly in the browser.
