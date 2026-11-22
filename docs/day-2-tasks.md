# Day 2 Tasks

5 independent tasks building on the Day 1 modules. Each targets separate files and verifies standalone so all 5 can run in parallel without merge conflicts or blocking dependencies.

---

## Task 1: ML Anomaly Detector, Risk Scorer & AI Explainer
**Files:** `backend/app/services/ml_detector.py`, `backend/app/services/risk_scorer.py`, `backend/app/services/ai_explainer.py`, `backend/tests/test_ml_ai.py`

* [ ] Implement `ml_detector.py`:
  * Train Scikit-learn `IsolationForest` on normal baseline numeric feature vectors `[cpu_utilization, network_in_bytes, network_out_bytes, request_count]`.
  * Expose `score_metrics(baseline_rows, target_rows) -> list[float]` returning normalized `0.0–1.0` anomaly scores (higher = more anomalous).
* [ ] Implement `risk_scorer.py`:
  * Compute weighted overall risk (`0.0–100.0`) and severity (`low | medium | high | critical`) using factor weights: `ml_score` (`0.30`), `iam_risk` (`0.25`), `resource_impact` (`0.20`), `cost_impact` (`0.15`), `traffic_anomaly` (`0.10`).
* [ ] Implement `ai_explainer.py`:
  * Accept an incident dict (title, signals, resource IDs, cost delta, risk breakdown) and return `{ "summary": str, "recommended_actions": list[str] }`.
  * Support calling an LLM API when `LLM_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` is set in env, with a deterministic template fallback when no key is configured.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_ml_ai.py -v` passes with inline baseline and anomalous samples (both with fallback and mocked LLM call).

---

## Task 2: Database Repository & Mock Seeder
**Files:** `backend/app/services/repository.py`, `backend/tests/test_repository.py`

* [ ] Using `app.core.database`, `app.models.entities`, and `app.services.mock_generator.MockTelemetryProvider` (read-only imports, do not edit those files):
  * Implement `seed_database(session, provider=None, force=False) -> dict[str, int]` to populate `CloudResource`, `TelemetryMetric`, `SecurityAlert`, and `Recommendation` idempotently.
  * Implement query and state helpers:
    * `list_resources(session, resource_type=None, region=None, backup_status=None)`
    * `list_alerts(session, severity=None, status=None)`
    * `list_recommendations(session, category=None, state=None)`
    * `update_recommendation_state(session, recommendation_id, new_state)` (supporting `pending`, `approved`, `dismissed`)
    * `save_alert(session, alert_data)`
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_repository.py -v` passes against a temporary SQLite database (`tmp_path`).

---

## Task 3: Resource/Cost Auditor & Simulation Endpoint
**Files:** `backend/app/services/auditor.py`, `backend/app/api/simulate.py`, `backend/tests/test_auditor_and_simulate.py`

* [ ] Implement `auditor.py` operating on raw resource/metric/traffic/cost dicts:
  * `audit_resources(resources, metrics) -> list[dict]` flagging underutilized EC2s (`utilization_pct < 15.0`), unattached EBS volumes (`status == "available"` and `attached is False`), and missing/outdated backups (`backup_status in {"missing", "outdated"}`) with estimated monthly savings.
  * `summarize_traffic_impact(traffic_logs) -> dict` aggregating total requests, bot share percentage, flagged endpoints, and estimated daily/monthly cost impact.
* [ ] Implement `backend/app/api/simulate.py` (`APIRouter(prefix="/api/v1", tags=["simulate"])`, do not edit `main.py` yet):
  * `POST /api/v1/simulate` accepting `{ "scenario": "iam_breach" | "bot_traffic" | "resource_waste" }` and returning generated signals, correlated incident (via `app.services.correlator.correlate_signals`), and generated recommendations.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auditor_and_simulate.py -v` passes using a local FastAPI app wrapping `simulate.router`.

---

## Task 4: Frontend Backend-to-UI Schema Adapters
**Files:** `frontend/src/services/adapters.js`, `frontend/src/services/api.js`, `frontend/src/services/adapters.test.mjs`

* [ ] Bridge the schema differences between FastAPI (`/api/v1/*` snake_case wrapped payloads) and the React page shapes (`frontend/src/mock/*` camelCase structures):
  * `adaptOverview(raw)` → `{ healthScore, riskLevel, monthlySavings, activeAlerts: { CRITICAL, HIGH, MEDIUM, LOW }, trend: [{ date, expected, cost, cpu }] }`
  * `adaptResources(raw)` → array of `{ id, name, type, region, status, cpu, backup, lastBackup, monthlyCost, finding }` (map `outdated`→`stale`, `not_applicable`→`n/a`)
  * `adaptAlerts(raw)` → array of `{ id, title, severity, riskScore, status, timestamp, breakdown, events, summary, steps }`
  * `adaptTraffic(raw)` → `{ totalRequests, botShare, costImpact, timeline: [{ time, requests, cpu, cost, cumulativeCost }], patterns: [{ endpoint, requests, ip, userAgent, bot, confidence }] }` (`botShare` as `0.0–1.0` ratio)
  * `adaptRecommendations(raw)` → array of `{ id, resourceId, category, title, action, estimatedSavings, confidence, state }` (converting string confidence `"high"|"medium"|"low"` to `0.9|0.7|0.5`)
* [ ] Update `frontend/src/services/api.js` so live HTTP responses (`VITE_USE_MOCK=false`) pass through `adapters.js` and local mock mode remains unchanged.
* **Verify:** `node --test frontend/src/services/adapters.test.mjs` and `npm run build` inside `frontend/` pass with zero errors.

---

## Task 5: Live Simulation Drawer & Resource/Export Controls
**Files:** `frontend/src/components/SimulatePanel.jsx`, `frontend/src/components/Layout.jsx`, `frontend/src/pages/Resources.jsx`

* [ ] Create `SimulatePanel.jsx` (self-contained component, no changes to `services/api.js`):
  * Modal/drawer triggered from the top bar to pick a scenario (`IAM Breach`, `Bot Traffic`, `Resource Waste`), call `POST ${VITE_API_URL}/simulate` when `VITE_USE_MOCK=false` (or display an immediate local simulated preview when `VITE_USE_MOCK=true`), and show the resulting risk score and findings.
* [ ] Update `Layout.jsx`:
  * Add a `"Simulate Incident"` button in the header opening `SimulatePanel` and a `"Refresh"` control triggering a page reload/re-fetch event.
* [ ] Update `Resources.jsx`:
  * Add a `"Backup Gaps Only"` quick toggle alongside existing filters and a client-side `"Export CSV"` button for the currently filtered resource table.
* **Verify:** `npm run build` inside `frontend/` completes cleanly and all interactive controls work in `npm run dev`.
