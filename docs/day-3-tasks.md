# Day 3 Tasks

5 independent tasks. Each targets separate files and verifies standalone with zero blocking dependencies across tracks.

---

## Task 1: ML Anomaly Detector, Risk Scorer & AI Explainer
**Files:** `backend/app/services/ml_detector.py`, `backend/app/services/risk_scorer.py`, `backend/app/services/ai_explainer.py`, `backend/tests/test_ml_ai.py`

* [ ] Implement `ml_detector.py`:
  * Fit Scikit-learn `IsolationForest` on baseline numeric vectors `[cpu_utilization, network_in_bytes, network_out_bytes, request_count]` (compatible with `MockTelemetryProvider(include_anomalies=False).get_metrics()`).
  * Expose `score_metrics(baseline_rows, target_rows) -> list[float]` returning normalized `0.0–1.0` anomaly scores (higher = more anomalous).
* [ ] Implement `risk_scorer.py`:
  * Compute weighted risk score (`0.0–100.0`) and severity (`low | medium | high | critical`) using factor weights: `ml_score` (`0.30`), `iam_risk` (`0.25`), `resource_impact` (`0.20`), `cost_impact` (`0.15`), `traffic_anomaly` (`0.10`).
* [ ] Implement `ai_explainer.py`:
  * Accept an incident dict (title, signals, resource IDs, cost delta, risk breakdown) and return `{ "summary": str, "recommended_actions": list[str] }`.
  * Call configured LLM API when `LLM_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` is set in env, with a deterministic template fallback when no key is configured.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_ml_ai.py -v` passes for baseline vs. anomalous samples and both fallback and mocked LLM responses.

---

## Task 2: Resource/Cost Auditor & Simulation Endpoint
**Files:** `backend/app/services/auditor.py`, `backend/app/api/simulate.py`, `backend/tests/test_auditor_and_simulate.py`

* [ ] Implement `auditor.py` operating on `TelemetryProvider` dict lists:
  * `audit_resources(resources, metrics) -> list[dict]` flagging underutilized EC2s (`utilization_pct < 15.0`), unattached EBS volumes (`status == "available"` and `attached is False`), and missing/outdated backups (`backup_status in {"missing", "outdated"}`) with estimated monthly savings.
  * `summarize_traffic_impact(traffic_logs) -> dict` aggregating total requests, bot share, flagged endpoints, and estimated daily/monthly cost impact.
* [ ] Implement `backend/app/api/simulate.py` (`APIRouter(prefix="/api/v1", tags=["simulate"])`, do not edit `main.py`):
  * `POST /api/v1/simulate` accepting `{ "scenario": "iam_breach" | "bot_traffic" | "resource_waste" }`.
  * Return `{ "incident": { "title", "risk_score", "severity", "summary", "recommended_actions" }, "findings": list[str], "recommendations": list[dict] }` matching the payload fields parsed by `frontend/src/components/SimulatePanel.jsx`.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auditor_and_simulate.py -v` passes using a local test FastAPI app mounting `simulate.router`.

---

## Task 3: Wire Database & Repository into FastAPI Routers
**Files:** `backend/app/main.py`, `backend/app/api/overview.py`, `backend/app/api/resources.py`, `backend/app/api/alerts.py`, `backend/app/api/traffic.py`, `backend/app/api/recommendations.py`, `backend/tests/test_api_routes.py`, `backend/tests/test_codebase_smoke.py`

* [ ] Update `main.py` with a FastAPI `lifespan` handler calling `create_tables()` and idempotently running `seed_database(session)` on startup.
* [ ] Replace static in-file fixtures in `resources.py`, `alerts.py`, and `recommendations.py` with live SQLAlchemy queries via `get_db()` and `app.services.repository` (`list_resources`, `list_alerts`, `list_recommendations`, `update_recommendation_state`).
* [ ] Update `RecommendationActionRequest` in `recommendations.py` to accept `Literal["pending", "approved", "dismissed"]` so frontend `Undo` transitions succeed and persist to SQLite/PostgreSQL.
* [ ] Update `overview.py` and `traffic.py` to compute dashboard trends, alert counts, savings totals, and bot traffic summaries dynamically from `get_telemetry_provider()` and repository queries.
* [ ] Update `test_api_routes.py` and `test_codebase_smoke.py` to pass/override an isolated temporary SQLite `get_db` session and test `"pending"` state restoration.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests -v` passes in a regular terminal.

---

## Task 4: Frontend Backend-to-UI Schema Adapters
**Files:** `frontend/src/services/adapters.js`, `frontend/src/services/api.js`, `frontend/src/services/adapters.test.mjs`

* [ ] Implement pure transform functions in `adapters.js` bridging FastAPI `/api/v1/*` JSON to the exact camelCase shapes consumed by `Overview.jsx`, `Resources.jsx`, `Security.jsx`, `Traffic.jsx`, and `Recommendations.jsx`:
  * `adaptOverview(raw)` → `{ healthScore, riskLevel, monthlySavings, activeAlerts: { CRITICAL, HIGH, MEDIUM, LOW }, trend: [{ date, expected, cost, cpu }] }`
  * `adaptResources(raw)` → `[{ id, name, type, region, status, cpu, backup, lastBackup, monthlyCost, finding }]` (map `outdated` → `stale`, `not_applicable` → `n/a`)
  * `adaptAlerts(raw)` → `[{ id, title, severity, riskScore, status, timestamp, breakdown, events, summary, steps }]` (uppercase `severity`, factor list with weights `0.30/0.25/0.20/0.15/0.10`)
  * `adaptTraffic(raw)` → `{ totalRequests, botShare, costImpact, timeline: [{ time, requests, cpu, cost, cumulativeCost }], patterns: [{ endpoint, requests, ip, userAgent, bot, confidence }] }` (`botShare` as `0.0–1.0` ratio)
  * `adaptRecommendations(raw)` → `[{ id, resourceId, category, title, action, estimatedSavings, confidence, state }]` (map string confidence `"high"|"medium"|"low"` → `0.9|0.7|0.5`)
* [ ] Update `frontend/src/services/api.js` so `VITE_USE_MOCK=false` routes backend responses through `adapters.js` while leaving `VITE_USE_MOCK=true` unchanged.
* **Verify:** `node --test frontend/src/services/adapters.test.mjs` and `npm run build --prefix frontend` pass cleanly.

---

## Task 5: System Analysis, Design Diagrams & Runbook Documentation
**Files:** `docs/system-analysis-and-design.md`, `README.md`

* [ ] Create `docs/system-analysis-and-design.md` covering formal engineering deliverables:
  * Functional and non-functional requirements and stakeholder/role scope.
  * Mermaid diagrams: System Architecture, Data Flow Diagram (DFD), Sequence Diagram (telemetry ingestion → ML/correlation → risk scoring → alert/recommendation), and Entity-Relationship Diagram (ERD) matching `cloud_resources`, `telemetry_metrics`, `security_alerts`, and `recommendations` in `backend/app/models/entities.py`.
  * Methodology documentation explaining `IsolationForest` input features, time-window correlation rules in `correlator.py`, and the 5-factor composite risk formula.
* [ ] Update `README.md` with verified local setup, database initialization, `pytest`, `uvicorn`, and Vite (`npm ci`, `npm run dev`, `npm run build`, `VITE_USE_MOCK`) instructions.
* **Verify:** Confirm all file paths, table columns, and commands match the live repository.
