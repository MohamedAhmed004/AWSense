# AWSense Task 4 QA Walkthrough & Verification Report

- **Date:** 2026-11-26
- **Branch:** `feat/task-4-live-refresh-alert-status`
- **Base Commit Hash:** `37c519f` (`Add combined Day 5/6 implementation plan`)
- **Author/Verifier:** Antigravity Agent

---

## 1. Test & Build Executions

### 1.1 Unit Tests (`adapters.test.mjs`)
Command:
```powershell
node --test frontend/src/services/adapters.test.mjs
```
Output:
```text
✔ adaptOverview maps KPIs, 4-key activeAlerts, and median expected trend (102.0055ms)
✔ adaptOverview handles empty/null input safely (0.798ms)
✔ adaptResources maps backup statuses, storage cpu nulling, timestamps, and findings (3.682ms)
✔ adaptAlerts builds 5-factor breakdown with exact weights and inferred events (0.9762ms)
✔ adaptTraffic normalizes botShare ratio, proportional timeline cost, and endpoint patterns (0.7934ms)
✔ adaptRecommendations and adaptRecommendationAction map confidence strings and unwrap POST responses (0.227ms)
ℹ tests 6
ℹ suites 0
ℹ pass 6
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 245.2716
```

### 1.2 Frontend Production Build
Command:
```powershell
npm run build --prefix frontend
```
Output:
```text
> awsense-frontend@0.1.0 build
> vite build

vite v5.4.21 building for production...
transforming...
✓ 2192 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.67 kB │ gzip:   0.38 kB
dist/assets/index-Bbs4JdVH.css   15.44 kB │ gzip:   3.79 kB
dist/assets/index-CBXHJw49.js   631.13 kB │ gzip: 180.86 kB
✓ built in 8.83s
```

---

## 2. Server Startup Commands

### 2.1 Backend Server (Live Mode)
Command:
```powershell
Set-Location "backend"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Output:
```text
INFO:     Started server process [9932]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### 2.2 Frontend Server (Live Mode)
Command:
```powershell
Set-Location "frontend"
$env:VITE_USE_MOCK="false"
$env:VITE_API_URL="http://localhost:8000/api/v1"
npm run dev
```
Output:
```text
  VITE v5.4.21  ready in 635 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

### 2.3 Frontend Server (Mock Mode)
Command:
```powershell
Set-Location "frontend"
$env:VITE_USE_MOCK="true"
npm run dev
```

---

## 3. Walkthrough Verification Matrix

| Check | Feature / Area | Mode | Status | Observed Behavior | Notes |
|---|---|---|---|---|---|
| **a** | **Overview Page** (`/`) | Live | **PASS** | Page loads with HTTP 200, zero console errors. Top header badge displays **"Live data"**. Displays Cloud Health `0/100`, Active Alerts `3` (2 critical, 1 high), Monthly savings available `$2,190`, Risk level `Critical`, plus 30-day cost/CPU charts and severity breakdown. | Matches backend `/overview` response exactly. |
| **b** | **Recommendations Page** (`/recommendations`) | Live | **PASS** | Page loads with "Live data" badge and 5 pending recommendations. Clicking **Approve** on `rec_0001` calls `POST /api/v1/recommendations/rec_0001/action` (200 OK); badge updates to "Approved", "Undo" button appears, pending count updates to 4. Clicking top-bar **Refresh** retains the "Approved" status. Clicking **Undo** reverts the recommendation to pending. | Backend state persistence and optimistic/live UI synchronization fully functional. |
| **c.1** | **Security Page (Alert Status)** (`/security`) | Live | **BLOCKED** *(by Task 2)* | Selected alert `alert_inc_0002` displays buttons `Investigating`, `Resolve`, `Dismiss`. Clicking `Investigating` calls `POST http://localhost:5173/api/v1/alerts/alert_inc_0002/status`, returning `404 Not Found` (endpoint not implemented in backend). Inline error with `role="alert"` displays: `"Request to /alerts/alert_inc_0002/status failed (404): Not Found"`. Status stays `Open`, buttons re-enable. | Backend endpoint `POST /api/v1/alerts/{alert_id}/status` is missing from `backend/app/api/alerts.py` (unmerged Task 2). Frontend failure handling, inline alert display, and button re-enablement work as required. |
| **c.2** | **Security Page (Alert Status)** (`/security`) | Mock | **PASS** | Top header displays "Sample data". On `ALT-1042` (open): clicking `Investigating` updates badge to `investigating` and shows `Resolve`, `Dismiss`, `Reopen`. Clicking `Resolve` updates badge to `resolved` and shows `Reopen`. Clicking `Reopen` updates badge to `open` and shows `Investigating`, `Resolve`, `Dismiss`. `ALT-1039` defaults to `investigating` with appropriate action buttons. | Full state machine verified in mock mode. |
| **d.1** | **Resources Page (Backup Gaps Filter)** (`/resources`) | Live | **PASS** | Initial inventory shows 14 resources with banner: *"10 resources have a backup gap."* Clicking **Backup Gaps Only** filters the table down to 10 rows. Toggling off restores all 14 rows. | In the live backend database, 10 resources have backup gaps and 4 are protected (contrast to mock data which has 4 gaps). |
| **d.2** | **Resources Page (Backup Gaps Filter)** (`/resources`) | Mock | **PASS** | Initial inventory shows 11 resources with banner: *"4 resources have a backup gap."* Clicking **Backup Gaps Only** filters table down to exactly 4 items (`old-reports-vol`, `scratch-vol`, `orders-prod`, `logs-archive`). | Matches mock specification of 4 backup gap items. |
| **d.3** | **Resources Page (Export CSV)** (`/resources`) | Live | **PASS** | Clicking **Export CSV** initiates an immediate client-side download of `awsense-resources-2026-11-26.csv` (1,206 bytes) containing filtered resource rows with headers and formatted values. | Clean CSV generation with no server dependency. |
| **e** | **Simulate Incident Drawer & Live Refresh** | Live | **PASS** | Drawer opens via top-bar "Simulate Incident" button. Scenario tests:<br>1. **IAM Breach:** `POST /simulate` returns risk score `96` (Critical), title *"Potential IAM Security Breach"*, 4 findings, remediation guidance.<br>2. **Bot Traffic:** `POST /simulate` returns risk score `92` (Critical), title *"Abnormal Bot Traffic Detected"*, 7 findings, remediation guidance.<br>3. **Resource Waste:** `POST /simulate` returns risk score `78` (High), title *"Cloud Resource Waste Detected"*, 12 findings, remediation guidance.<br>Closing the drawer triggers `onSimulated` which increments `refreshKey` in `Layout.jsx` and re-fetches live data for the active view. | Drawer execution and layout refresh integration fully verified. |
| **f** | **Traffic Page** (`/traffic`) | Live | **PASS** | Page loads with "Live data" badge. Displays KPI cards (2.4M requests, 89% bot share, $138 extra cost), request volume chart, and endpoint pattern table with 3 flagged bot endpoints without errors. | Charting and anomaly displays function cleanly. |

---

## 4. Observed Gaps, Bugs & Unhandled Cases

1. **Backend Missing Alert Status Route (Task 2 Blocker):**
   - File: `backend/app/api/alerts.py`
   - Issue: The route `POST /api/v1/alerts/{alert_id}/status` does not exist in the current backend branch. Any attempt to update alert status in live mode returns `404 Not Found`.
   - Frontend behavior: Gracefully handled. The error detail is captured and rendered inline in `Security.jsx` next to the alert action buttons with `role="alert"`, and the status remains unchanged.

2. **Repetitive Remediation Items in Live Simulation Output:**
   - Endpoint: `POST /api/v1/simulate` with `resource_waste`
   - Issue: The backend simulation engine generates 10 identical recommendations: *"Resource backup status is 'missing'."* in the `recommendations` array.
   - Frontend behavior: The drawer displays all returned recommendations in order as received from the API without deduplication.

3. **Status Badge Vocabulary:**
   - In `Layout.jsx`, the mock status indicator is labeled `"Sample data"` rather than `"Mock data"`. Live mode displays `"Live data"`. Both indicators correctly reflect `VITE_USE_MOCK`.

4. **Resource Gaps Count Difference Between Environments:**
   - Mock environment has 11 total resources, of which 4 have backup gaps.
   - Live SQLite seed database has 14 total resources, of which 10 have backup gaps (4 are protected). Both correctly filter and display their respective gap counts when "Backup Gaps Only" is clicked.
