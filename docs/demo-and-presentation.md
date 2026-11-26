# AWSense — Live Demo Script & Presentation Guide

**Target Duration:** 5–7 minutes presentation + live demo (plus Q&A)  
**Scope:** End-to-end engineering pitch, rubric-aligned slide deck outline, live click-through script, offline fallback playbook, and Q&A defense notes.

---

## 1. Time Budget (6 Minutes Target)

| Segment | Target Time | Slides / Screens | Goal |
|---|---:|---|---|
| **1. Problem & Value Proposition** | 1:00 | Slides 1–2 | Frame siloed CSPM + FinOps telemetry and alert fatigue |
| **2. Architecture & Technical Depth** | 1:30 | Slides 3–4 | Show 4-layer architecture, `IsolationForest` ML, correlator, 5-factor scoring, `Boto3TelemetryProvider` |
| **3. Live Product Walkthrough** | 2:30 | Browser (`:5173`) | Demonstrate Overview -> Resources (Filter + CSV) -> Security -> Traffic -> Recommendations -> Simulate Incident |
| **4. Testing, Honest Scope & Wrap-up** | 1:00 | Slides 5–6 | Present verified benchmarks (`ml_eval.py`, `pytest`, `node --test`), read-only AWS safety, and roadmap |

---

## 2. 5–7 Minute Slide Outline (Aligned to Grading Rubric)

### Slide 1 — Title & Elevator Pitch *(0:25)*
* **Rubric Alignment:** *Problem Clarity & Project Identity*
* **Slide Content:**
  * Title: **AWSense — Unified Cloud Security Posture (CSPM) & FinOps Platform**
  * Subtitle: *Turning disconnected AWS logs, metrics, and billing spikes into explainable incidents and cost-saving actions.*
  * Key Tagline: "See the breach behind the CPU spike, and the dollar cost behind the bot flood."
* **Speaker Note:** Introduce AWSense as a single dashboard for SecOps, FinOps, and SRE teams that correlates security, utilization, traffic, and cost signals instead of treating them as isolated alerts.

### Slide 2 — The Problem: Siloed Cloud Telemetry *(0:35)*
* **Rubric Alignment:** *Problem Significance & Domain Understanding*
* **Slide Content (3-column contrast):**
  1. **CloudWatch** sees high CPU (`> 85%`) — looks like normal scaling unless linked to IAM.
  2. **CloudTrail / IAM** logs a role assumption from `ap-southeast-1` (`RunInstances` x8) — buried in audit logs.
  3. **Cost Explorer & ALB/WAF** show sudden egress/compute cost spikes (`$92/day` vs `$8` expected, `2.4M` requests / `89%` bot traffic) — often noticed only on the monthly bill.
* **Speaker Note:** Explain why native point tools create alert fatigue: they report symptoms separately rather than connecting root cause, blast radius, and dollar impact.

### Slide 3 — Architecture & Design Choices *(0:45)*
* **Rubric Alignment:** *Software Architecture, Modularity & Abstraction*
* **Visual:** Simplified 4-tier flow diagram (`TelemetryProvider` -> Analytics Engine -> FastAPI + SQLAlchemy -> React Dashboard).
* **Slide Bullets:**
  * **Swappable Ingestion (`TelemetryProvider`):** `DATA_SOURCE=mock` (deterministic 14-resource synthetic generator) or `DATA_SOURCE=aws` (`Boto3TelemetryProvider` read-only collectors across EC2, EBS, RDS, S3, CloudWatch, CloudTrail, Cost Explorer).
  * **Single Relational Store:** SQLAlchemy ORM (`cloud_resources`, `telemetry_metrics`, `security_alerts`, `recommendations`) with `JSON` breakdown/metadata columns, running on zero-config SQLite locally or PostgreSQL in production (`DATABASE_URL`).
  * **Human-in-the-Loop Safety:** Actions (`pending` -> `approved` / `dismissed`) require explicit operator confirmation and never auto-terminate resources silently.

### Slide 4 — Detection Algorithms & AI Synthesis *(0:45)*
* **Rubric Alignment:** *AI/ML Depth & Algorithmic Rigor*
* **Slide Bullets:**
  * **Unsupervised ML (`ml_detector.py`):** `log1p` transform -> `StandardScaler` -> `IsolationForest(n_estimators=200, contamination=0.05)` over `[cpu_utilization, network_in_bytes, network_out_bytes, request_count]`, calibrated via sigmoid to `[0.0, 1.0]` (`>= 0.70` flagged).
  * **Temporal Correlator (`correlator.py`):** 60-minute sliding window grouping CloudTrail, metric spikes, and cost deltas by `resource_id`, IAM `principal`, or `region`.
  * **Explainable Risk Scoring (`risk_scorer.py`):** Weighted 5-factor formula (`30%` ML, `25%` IAM, `20%` Resource, `15%` Cost, `10%` Traffic).
  * **AI Incident Explainer (`ai_explainer.py`):** Prompt-hardened OpenAI (`gpt-4o-mini`) or Gemini integration returning JSON summaries + numbered response steps, with deterministic template fallback when offline.

### Slide 5 — Live System Demo Transition *(2:30 on app)*
* **Rubric Alignment:** *Working Software, UI/UX Quality & End-to-End Integration*
* **On-Screen Cue:** Keep this single slide visible for 5 seconds while switching cleanly to the already-open browser tab at `http://localhost:5173`. (Follow **Section 4** click-through script.)

### Slide 6 — Verification, Benchmarks & Engineering Quality *(0:40)*
* **Rubric Alignment:** *Testing, Benchmarking & Engineering Rigor*
* **Measured Evidence (directly verified via repo commands):**
  * **ML Evaluation (`python -m app.services.ml_eval`):** `120` baseline rows / `144` evaluation rows -> **`100%` precision (`1.0`), `100%` recall (`1.0`), `0%` false positive rate** (`tp=25, tn=119, fp=0, fn=0`), median score separation **`0.626`** (`0.181` normal vs `0.807` anomaly), **`13.2 ms`** total inference (`0.092 ms/row`).
  * **Automated Tests:** Backend `pytest` suite (`54+` tests including `botocore.stub.Stubber` AWS collector tests and FastAPI integration tests) + Frontend `node --test src/services/adapters.test.mjs` (`6/6` pass) + clean `vite build`.
  * **Security Hygiene:** Read-only AWS API design, no committed secrets (`.env.example`), formula-injection sanitized CSV export (`\uFEFF` BOM + `= + - @ \t \r` quoting).

### Slide 7 — Limitations & Next Steps *(0:20)*
* **Rubric Alignment:** *Honest Self-Assessment & Production Readiness*
* **Slide Bullets:**
  * Mock baseline benchmarks are evaluated against deterministic synthetic data; production thresholds should be tuned on live VPC/CloudTrail telemetry.
  * Future milestones: automated scheduled polling workers (EventBridge/Lambda), multi-account AWS Organizations assume-role support, and stricter CORS allowlist for production deployment.

---

## 3. Pre-Demo Startup Checklist (Live 2-Server Mode)

Run these commands **5 minutes before presenting** so both servers are warm and seeded:

### Terminal 1 — FastAPI Backend (`:8000`)
```powershell
cd backend
.venv\Scripts\Activate.ps1
# Optional: remove stale awsense.db if you want a clean seed baseline before the demo
# Remove-Item awsense.db -ErrorAction SilentlyContinue
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Quick verify in browser or PowerShell: `GET http://127.0.0.1:8000/api/v1/health` returns `{"status": "healthy"}`.

### Terminal 2 — Vite + React Frontend (`:5173`)
```powershell
cd frontend
$env:VITE_USE_MOCK = "false"
$env:VITE_API_URL = "http://localhost:8000/api/v1"
npm run dev
```
*(Linux/macOS equivalent: `VITE_USE_MOCK=false VITE_API_URL=http://localhost:8000/api/v1 npm run dev`)*

### Pre-Flight Browser Check
Open `http://localhost:5173` and verify:
* Top-right pill badge reads **`Live data`** (not `Sample data`).
* Browser DevTools Console has zero red errors.
* Zoom browser to `100%` or `110%` for projector legibility.

---

## 4. Exact Live Demo Click-Through Order (~2:30)

Follow this exact sequence to show every requirement without hunting through menus:

### Step 1 — Overview (`/`, ~25s)
1. Start on **Overview** (`http://localhost:5173`).
2. **Point out:**
   * Header pill says **`Live data`** (confirming live FastAPI + SQLite communication).
   * Top KPI cards: **Cloud health** (`0/100` under seeded active critical alerts), **Active alerts** (`3`: `2 critical, 1 high`), **Monthly savings available** (`$2,190`), **Risk level** (`Critical`).
   * **Daily cost and CPU, last 30 days** dual-axis chart comparing actual cost vs expected baseline and average CPU spike.
   * **Alerts by severity** bar distribution on the right.

### Step 2 — Resources: Inventory, Backup Gaps & CSV Export (`/resources`, ~25s)
1. Click **Resources** in the left sidebar.
2. **Point out:** The amber warning banner at the top (`10 resources have a backup gap. Back them up before changing or deleting them.`) and `Resource inventory (14)`.
3. Click the **`Backup Gaps Only`** toggle button -> table immediately filters down to only the unprotected/outdated resources (`10` in live DB).
4. Click **`Export CSV`** -> browser downloads `awsense-resources-YYYY-MM-DD.csv` cleanly client-side (mention formula-injection protection and UTF-8 BOM).
5. Click **`Backup Gaps Only`** again to clear the filter.

### Step 3 — Security: Correlated Incident & 5-Factor Breakdown (`/security`, ~30s)
1. Click **Security** in the left sidebar.
2. **Point out:** The **Alert feed** on the left shows correlated incidents and standalone alerts (e.g., compromised IAM role launching 8 EC2 instances, bot traffic cost spike, unprotected production RDS).
3. Click the critical IAM incident card -> highlight:
   * Large **Risk score** display + severity badge.
   * **5-factor risk score breakdown** bars with transparent weights (`30%` ML, `25%` IAM, `20%` Resource, `15%` Cost, `10%` Traffic).
   * **AI incident summary** & numbered **What to do** checklist.
   * **Correlated events** timeline tying CloudTrail, CloudWatch, and Cost events together.
   * *(If Task 2+Task 4 status workflow is merged on demo branch: click **`Investigating`** -> show badge transitions cleanly.)*

### Step 4 — Traffic: Bot Cost Attribution (`/traffic`, ~20s)
1. Click **Traffic** in the left sidebar.
2. **Point out:** **`2.4M`** Requests in 24 hours, **`89%`** Share from bots, and **Extra cost from bot load** (`$138`).
3. Scroll briefly to **Request volume against CPU and cost** chart and **Endpoint patterns** table showing flagged scraper endpoints vs normal user endpoints.

### Step 5 — Recommendations: Human-in-the-Loop Approval (`/recommendations`, ~20s)
1. Click **Recommendations** in the left sidebar.
2. Point out `5 pending, worth $2,190 a month.`
3. Click **`Approve`** on the top card -> card badge turns **`Approved`**, button becomes **`Undo`**, and remaining pending savings total decreases immediately.
4. Click **`Refresh`** in the top header -> confirm the **`Approved`** state persists in SQLite across reload.
5. Click **`Undo`** so the database returns cleanly to its baseline state.

### Step 6 — Simulate Incident Drawer (`/`, ~30s)
1. Click **`Simulate Incident`** (blue accent button in the top-right header) from **Security** or **Overview**.
2. Keep **IAM Breach** selected and click **`Run simulation`**.
3. **Point out:**
   * **`POST /api/v1/simulate`** runs the scenario engine, scores the incident (`96` / `Critical`), lists correlated **Findings** and **What to do** steps in the `aria-live` drawer, and persists the simulated alert (`sim_alert_iam_breach`).
4. Switch radio to **Bot Traffic** (or **Resource Waste**) -> click **`Run simulation`** -> show cost/waste findings updating cleanly.
5. Click **`X`** (**Close**) to close the drawer. *(With Task 4's `onSimulated` callback merged, the underlying Security/Overview views already refreshed automatically without clicking Refresh.)*

---

## 5. Offline & Degradation Fallback Playbook

If anything breaks on stage (Wi-Fi drops, Python environment issue, LLM API rate limit, or no AWS credentials), use these zero-panic fallbacks:

### Fallback 1 — Backend Down or Port Conflict -> Frontend Sample Mode (`VITE_USE_MOCK=true`)
* **When to use:** `uvicorn` won't start, SQLite file is locked, or live backend shows a red error banner.
* **Action (10 seconds):**
  ```powershell
  cd frontend
  $env:VITE_USE_MOCK = "true"
  npm run dev
  ```
  *(Or edit `frontend/.env` to set `VITE_USE_MOCK=true` and reload `http://localhost:5173`.)*
* **What changes visibly:**
  * Header badge changes from `Live data` to **`Sample data`**.
  * All 5 pages (**Overview** `72/100`, **Resources** `11` rows with `4` backup gaps, **Security**, **Traffic**, **Recommendations** `$1,842/mo`) and **`Simulate Incident`** previews (`94` Critical, `78` High, `41` Medium with `"Local preview. Nothing was sent to the backend."`) remain 100% interactive with zero network calls.
* **What to say to judges:** *"We designed AWSense with strict dual-mode parity via our `api.js` and `adapters.js` layers, so you're seeing the exact same UI contracts backed by local deterministic fixtures."*

### Fallback 2 — LLM API Unavailable or Rate-Limited -> Deterministic Template Fallback
* **When to use:** Live demo machine has no internet access or `OPENAI_API_KEY` / `GEMINI_API_KEY` quota is exhausted.
* **Action:** Leave `OPENAI_API_KEY`, `LLM_API_KEY`, and `GEMINI_API_KEY` unset/blank in `backend/.env` and restart `uvicorn`.
* **Behavior:** `explain_incident()` in `backend/app/services/ai_explainer.py` detects no active key and immediately generates a structured deterministic summary + 3 numbered remediation steps without throwing HTTP 500 or blocking `/alerts` or `/simulate`.

### Fallback 3 — No Live AWS Sandbox Credentials -> `DATA_SOURCE=mock` + Stubber Proof
* **When to use:** Presenting without live AWS IAM credentials configured.
* **Action:** Keep `DATA_SOURCE=mock` in `backend/.env`.
* **Proof Point:** Open `backend/app/services/telemetry_provider.py` or run:
  ```powershell
  backend\.venv\Scripts\python.exe -m pytest backend\tests\test_telemetry_provider.py -v
  ```
  to show `Boto3TelemetryProvider` executes real EC2/EBS/RDS/S3/CloudWatch/CloudTrail/Cost Explorer SDK calls verified offline via `botocore.stub.Stubber`.

---

## 6. Q&A Defense Notes

### Q1: Why use unsupervised `IsolationForest` instead of simple static CPU/cost thresholds?
> **Answer:** Static thresholds (like `CPU > 80%`) miss multi-feature combinations and produce noisy false alarms across diverse instance sizes. Our `MLDetector` transforms 4 correlated telemetry dimensions (`cpu_utilization`, `network_in_bytes`, `network_out_bytes`, `request_count`) with `np.log1p` (to handle heavy-tailed byte/request distributions), normalizes with `StandardScaler`, and scores joint multivariate anomalies using `IsolationForest(n_estimators=200, contamination=0.05)` calibrated via sigmoid (`>= 0.70`). In `ml_eval.py`, it achieved `100%` precision and recall across 144 evaluation points in `13.2 ms`.

### Q2: Why correlate events across a time window before raising alerts?
> **Answer:** Security and FinOps teams suffer from alert fatigue when a single root cause generates 15 separate notifications. `correlator.py` clusters CloudTrail, metric spikes, and billing deltas chronologically within a configurable 60-minute window using priority matching (`resource_id` -> IAM `principal` + compatible region -> shared region for unscoped events). An IAM compromise plus 8 rogue instances plus a billing surge becomes **one actionable incident** instead of a flood of disconnected alerts.

### Q3: Why store telemetry and JSON breakdowns in a single SQLAlchemy database instead of adding Elasticsearch/MongoDB?
> **Answer:** A single relational schema (SQLite for zero-setup development, PostgreSQL via `DATABASE_URL` for deployment) keeps foreign keys, cascade rules, recommendation workflows, and JSON columns (`correlated_event_ids`, `signal_breakdown`, `recommended_actions`, `metadata_json`) in one transactional store. That eliminates cross-database sync bugs and simplifies setup (`uvicorn app.main:app` auto-creates tables and seeds idempotently).

### Q4: How would this connect to a real AWS account safely?
> **Answer:** Through the `TelemetryProvider` abstraction (`DATA_SOURCE=aws`). `Boto3TelemetryProvider` uses strictly read-only AWS SDK APIs (`DescribeInstances`, `DescribeVolumes`, `DescribeDBInstances`, `ListBuckets`, `GetMetricData`, `ListMetrics`, `LookupEvents`, `GetCostAndUsage`) scoped by `AWS_REGION` and optional `AWS_PROFILE`, never executing mutating AWS calls automatically. Even remediation actions in the UI only persist operator workflow state (`approved` / `dismissed`) in our database unless an explicit human-approved runbook step is executed.

### Q5: How do you protect against LLM failures or prompt injection from untrusted log strings?
> **Answer:** First, `ai_explainer.py` puts an explicit system boundary in the prompt instructing the model to treat incident JSON as untrusted evidence only and never follow embedded instructions. Second, all outputs are strictly schema-validated (non-empty `summary` string and non-empty list of action strings). Third, if no API key is configured, AWSense gracefully falls back to a deterministic template so `/alerts` and `/simulate` always stay available.

### Q6: How do you prevent security vulnerabilities in client-side CSV exports?
> **Answer:** In `frontend/src/pages/Resources.jsx`, `formatCsvCell()` neutralizes spreadsheet formula injection by prefixing values starting with `=`, `+`, `-`, `@`, `\t`, or `\r` with a leading single quote `'`, properly escapes quotes/newlines, and prepends a UTF-8 BOM (`\uFEFF`) for clean Excel rendering.
