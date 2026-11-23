# Day 4 Tasks

5 independent tasks. Each targets separate files and verifies standalone with zero blocking dependencies across tracks.

---

## Task 1: Frontend Backend-to-UI Schema Adapters
**Files:** `frontend/src/services/adapters.js`, `frontend/src/services/api.js`, `frontend/src/services/adapters.test.mjs`

* [ ] Implement pure mapper functions in `adapters.js` converting FastAPI `/api/v1/*` JSON into the exact camelCase structures consumed by the React pages:
  * `adaptOverview(raw)` → `{ healthScore, riskLevel, monthlySavings, activeAlerts: { CRITICAL, HIGH, MEDIUM, LOW }, trend: [{ date, expected, cost, cpu }] }`
  * `adaptResources(raw)` → `[{ id, name, type, region, status, cpu, backup, lastBackup, monthlyCost, finding }]` (map `outdated` → `stale`, `not_applicable` → `n/a`)
  * `adaptAlerts(raw)` → `[{ id, title, severity, riskScore, status, timestamp, breakdown, events, summary, steps }]` (uppercase `severity`, 5-factor `breakdown` list using weights `0.30 / 0.25 / 0.20 / 0.15 / 0.10`)
  * `adaptTraffic(raw)` → `{ totalRequests, botShare, costImpact, timeline: [{ time, requests, cpu, cost, cumulativeCost }], patterns: [{ endpoint, requests, ip, userAgent, bot, confidence }] }` (`botShare` as `0.0–1.0` ratio)
  * `adaptRecommendations(raw)` → `[{ id, resourceId, category, title, action, estimatedSavings, confidence, state }]` (map `"high"|"medium"|"low"` → `0.9|0.7|0.5`)
* [ ] Update `frontend/src/services/api.js` to pass live backend responses (`VITE_USE_MOCK=false`) through `adapters.js` while leaving `VITE_USE_MOCK=true` unchanged.
* **Verify:** `node --test frontend/src/services/adapters.test.mjs` and `npm run build --prefix frontend` pass cleanly.

---

## Task 2: Simulation Persistence & AI Enrichment
**Files:** `backend/app/api/simulate.py`, `backend/tests/test_auditor_and_simulate.py`

* [ ] Update `POST /api/v1/simulate` in `simulate.py` to accept `db: Session = Depends(get_db)` and persist simulated state so refreshing Overview, Security, or Recommendations reflects newly triggered scenarios:
  * Ensure target simulated `CloudResource` records exist before saving child rows (upsert `i-sim-iam-001`, `i-sim-web-001`, `i-sim-waste-001` as needed).
  * Enrich the correlated incident with `app.services.ai_explainer.explain_incident()` (falling back deterministically when no LLM API key is set) and persist it via `app.services.repository.save_alert()`.
  * Persist generated `Recommendation` rows with unique IDs (`sim_<hex>`) into the database.
* [ ] Update `test_auditor_and_simulate.py` with an isolated temporary SQLite `get_db` override and verify that simulated alerts and recommendations persist in DB queries after `POST /api/v1/simulate`.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auditor_and_simulate.py -v` passes.

---

## Task 3: Live AWS `boto3` Collectors & Stubber Tests
**Files:** `backend/app/services/telemetry_provider.py`, `backend/tests/test_boto3_provider.py`, `backend/tests/test_telemetry_provider.py`

* [ ] Implement real read-only AWS SDK collection inside `Boto3TelemetryProvider` in `telemetry_provider.py` matching the normalized dict schema of `MockTelemetryProvider`:
  * `get_resources()`: query `ec2.describe_instances`, `ec2.describe_volumes`, `rds.describe_db_instances` (checking `BackupRetentionPeriod` / snapshot status), and `s3.list_buckets`.
  * `get_metrics()`: query `cloudwatch.get_metric_data` (`CPUUtilization`, `NetworkIn`, `NetworkOut`) over the requested day window.
  * `get_cloudtrail_events()`: query `cloudtrail.lookup_events` and flag sensitive/off-hours actions.
  * `get_cost_usage()`: query `ce.get_cost_and_usage` grouped by `SERVICE` and `DAILY` granularity.
  * `get_traffic_logs()`: map CloudWatch/WAF or ALB request metrics (or return `[]` cleanly when WAF/ALB is absent) with graceful handling of AWS `ClientError` / missing sandbox resources.
* [ ] Add `test_boto3_provider.py` using `botocore.stub.Stubber` to verify all collectors offline without live AWS credentials, and update `test_telemetry_provider.py` to match the implemented `Boto3TelemetryProvider`.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_boto3_provider.py backend\tests\test_telemetry_provider.py -v` passes.

---

## Task 4: ML Evaluation Benchmark & Frontend Dynamic Polish
**Files:** `backend/app/services/ml_eval.py`, `backend/tests/test_ml_eval.py`, `frontend/vite.config.js`, `frontend/src/pages/Overview.jsx`, `frontend/src/pages/Traffic.jsx`

* [ ] Implement `ml_eval.py` to evaluate `MLDetector` (`IsolationForest`), `correlate_signals`, and `score_risk` against labeled synthetic baseline + anomaly datasets from `MockTelemetryProvider`, computing precision, recall, F1 score, false-positive rate, normal-vs-anomaly score separation, and inference latency (plus optional CLI JSON output via `python -m app.services.ml_eval`).
* [ ] Add `test_ml_eval.py` verifying detection precision/recall thresholds and score separation.
* [ ] Remove remaining hardcoded mock captions in `Overview.jsx` (e.g., `"Down from 91 last week"`, `"Driven by ALT-1042"`) and `Traffic.jsx` (e.g., `"Across 3 flagged IP ranges"`), deriving subtitles dynamically from the loaded API/mock payload.
* [ ] Add a Vite dev proxy for `/api` → `http://localhost:8000` in `frontend/vite.config.js` for seamless local development.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_ml_eval.py -v` and `npm run build --prefix frontend` pass.

---

## Task 5: System Analysis, Design Diagrams & Runbook Documentation
**Files:** `docs/system-analysis-and-design.md`, `README.md`

* [ ] Create `docs/system-analysis-and-design.md` covering formal engineering deliverables:
  * Problem statement, objectives, functional & non-functional requirements, and stakeholder roles.
  * Mermaid diagrams: System Architecture, Use Case / Component Flow, Data Flow Diagram (DFD), Sequence Diagram (ingestion → `IsolationForest` → `correlator` → `risk_scorer` → `ai_explainer` → DB/API), and Entity-Relationship Diagram (ERD) matching `cloud_resources`, `telemetry_metrics`, `security_alerts`, and `recommendations` in `backend/app/models/entities.py`.
  * Algorithms & methodology section detailing `IsolationForest` feature engineering (`log1p` + `StandardScaler`), chronological signal clustering in `correlator.py`, and the 5-factor risk scoring weights.
* [ ] Update `README.md` with verified setup, `.env`, `pytest`, `uvicorn`, and Vite (`npm ci`, `npm run dev`, `npm run build`, `VITE_USE_MOCK=false`) commands.
* **Verify:** Confirm all documented file paths, table columns, endpoints, and CLI commands match the live codebase.
