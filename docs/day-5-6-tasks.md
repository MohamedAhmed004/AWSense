# Day 5/6 Tasks (Final Combined Plan)

5 independent tracks combining remaining code fixes, live integration polish, benchmark documentation, verification, and demo prep into a single day. Each track owns separate files with zero overlap.

---

## Task 1: Resilient AI Explainer & ML Benchmark Docs
**Files:** `backend/app/services/ai_explainer.py`, `backend/tests/test_ml_ai.py`, `docs/system-analysis-and-design.md`

* [ ] Wrap OpenAI/Gemini HTTP calls (`_post_json`) and JSON parsing in `explain_incident()` with exception handling (`URLError`, `HTTPError`, `TimeoutError`, `json.JSONDecodeError`, `KeyError`, `ValueError`), logging a warning and falling back to the deterministic template instead of raising HTTP 500.
* [ ] Add tests in `test_ml_ai.py` covering network failures, HTTP errors, and malformed LLM JSON responses.
* [ ] Run `backend\.venv\Scripts\python.exe -m app.services.ml_eval` from `backend/` and record observed `precision`, `recall`, `f1`, `false_positive_rate`, confusion matrix, `score_separation`, and `inference_ms_total` in `docs/system-analysis-and-design.md`.
* [ ] Sync §3–§11 of `docs/system-analysis-and-design.md` to remove resolved gaps (`Boto3TelemetryProvider` stub claims, stateless `/simulate`, uncaught LLM errors, missing `score_risk()` wiring).
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_ml_ai.py backend\tests\test_ml_eval.py -v` passes.

---

## Task 2: Risk Scorer Wiring, Alert Status API & `README.md` Sync
**Files:** `backend/app/api/alerts.py`, `backend/tests/test_api_routes.py`, `README.md`

* [ ] Wire `app.services.risk_scorer.score_risk` into `alerts.py` (using `ml_score` plus `SignalBreakdown` inputs) while keeping SQLite `severity` filter behavior consistent.
* [ ] Add `POST /api/v1/alerts/{alert_id}/status` accepting `{"status": "open" | "investigating" | "resolved" | "dismissed"}`, persisting in DB and returning `404` on unknown `alert_id`.
* [ ] Add tests in `test_api_routes.py` for alert status transitions, DB persistence, `404`, and `422` validation.
* [ ] Update `README.md` to match the final codebase (implemented `Boto3TelemetryProvider` collectors, persistent `/simulate`, `score_risk()`, `ml_eval.py`, alert status endpoint, updated test counts, and verified 2-terminal startup steps).
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_routes.py -v` passes.

---

## Task 3: Simulation 5-Factor Breakdown, Idempotency & Architecture Sync
**Files:** `backend/app/api/simulate.py`, `backend/tests/test_auditor_and_simulate.py`, `docs/architecture-and-codebase.md`, `.gitignore`

* [ ] Replace hardcoded scenario `risk_score` constants in `simulate.py` with `score_risk()` inputs and store full 5-factor `signal_breakdown` keys (`iam_risk`, `resource_impact`, `cost_impact`, `traffic_anomaly`, `ml_score`, `total_cost_delta_usd`) plus `correlated_event_ids` on `sim_alert_{scenario}`.
* [ ] Make simulated `Recommendation` persistence idempotent per scenario (replace existing `sim_` recommendations for that simulated `resource_id` instead of stacking duplicates on repeated clicks).
* [ ] Update `test_auditor_and_simulate.py` to assert full `signal_breakdown` factor keys and idempotent recommendation counts across repeated runs.
* [ ] Update `docs/architecture-and-codebase.md` so all Days 2–5 modules (`ml_detector.py`, `risk_scorer.py`, `ai_explainer.py`, `auditor.py`, `ml_eval.py`, `repository.py`, `simulate.py`, `Boto3TelemetryProvider` collectors, `adapters.js`, `SimulatePanel.jsx`) reflect **Implemented**, and verify `.gitignore` excludes local DB/env/build artifacts.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_auditor_and_simulate.py -v` passes.

---

## Task 4: Frontend Live Refresh, Alert Status UI & QA Walkthrough
**Files:** `frontend/src/components/Layout.jsx`, `frontend/src/components/SimulatePanel.jsx`, `frontend/src/pages/Security.jsx`, `frontend/src/services/api.js`, `docs/verification-report.md`

* [ ] Pass an `onSimulated` callback from `Layout.jsx` into `SimulatePanel.jsx` to bump `refreshKey` after a live simulation completes so Overview, Security, and Recommendations refresh automatically.
* [ ] Add `updateAlertStatus(id, status)` in `api.js` (handling both mock mode and `POST /alerts/{id}/status`) and add alert status buttons (`Investigating`, `Resolve`, `Dismiss`, `Reopen`) in `Security.jsx` with inline error handling.
* [ ] Run a live 2-server walkthrough (`uvicorn app.main:app --port 8000` + `VITE_USE_MOCK=false npm run dev`) across all 5 pages, `Approve`/`Dismiss`/`Undo`, alert status toggles, `Backup Gaps Only` + CSV export, and `Simulate Incident`, recording results in `docs/verification-report.md`.
* **Verify:** `node --test frontend/src/services/adapters.test.mjs` and `npm run build --prefix frontend` pass cleanly.

---

## Task 5: Env Templates, Smoke Tests & Live Demo / Presentation Script
**Files:** `backend/.env.example`, `frontend/.env.example`, `backend/tests/test_codebase_smoke.py`, `docs/demo-and-presentation.md`

* [ ] Document all active backend env vars in `backend/.env.example` (`DATABASE_URL`, `SQL_ECHO`, `DATA_SOURCE=mock`, `AWS_REGION`, `AWS_PROFILE`, `LLM_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL`, `GEMINI_MODEL`) and clarify `VITE_USE_MOCK=true|false` in `frontend/.env.example`.
* [ ] Expand `test_codebase_smoke.py` to smoke-check `ml_eval.evaluate_ml()`, `get_telemetry_provider("aws")`, and `POST /api/v1/simulate` compatibility with `SimulatePanel.jsx`.
* [ ] Create `docs/demo-and-presentation.md` with a 5–7 minute slide outline aligned to the grading rubric, exact live demo click-through order, offline fallback steps (`VITE_USE_MOCK=true` / template AI fallback), and Q&A defense notes.
* **Verify:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_codebase_smoke.py -v` passes.
