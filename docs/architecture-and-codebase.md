# AWSense — Architecture & Codebase Reference

Comprehensive technical guide covering the project vision, current codebase implementation, planned modules, data schemas, local setup, and engineering conventions. Written for both human contributors and AI coding agents.

---

## 1. Project Purpose & Core Problem

**AWSense** is an AI-assisted AWS cloud security posture (CSPM) and cost optimization (FinOps) platform delivered as a standalone web application.

### The Core Problem
AWS environments emit telemetry across disconnected services:
- **CloudWatch** reports compute/network metrics (e.g., CPU spikes).
- **CloudTrail / IAM** logs API calls, logins, and configuration changes.
- **Traffic / ALB / WAF logs** record request volume and endpoint patterns.
- **AWS Backup / Snapshots** track resource protection status.
- **Cost Explorer** reports daily and monthly spend.

Analyzed separately, isolated alerts produce noise. Correlated together, they expose high-value incidents—such as compromised IAM credentials spinning up compute instances in an unused region, or automated scraper bots inflating EC2 CPU and bandwidth bills.

### Core Objectives
1. Detect underutilized EC2 instances, unattached EBS volumes, and unprotected resources missing recent backups.
2. Baseline IAM principal and resource behavior, scoring deviations with unsupervised ML (`IsolationForest`).
3. Detect automated/bot traffic impacts on compute utilization and cloud spend.
4. Correlate security, utilization, traffic, and cost signals into unified incidents with an overall risk score.
5. Generate human-readable AI incident explanations and remediation actions with human-in-the-loop approval (`pending` / `approved` / `dismissed`).

---

## 2. Implementation Status Snapshot

Keep this distinction strict when reading or modifying the repository:

| Area | Status | Notes |
|---|---|---|
| Repo layout & docs (`README.md`, `docs/*`) | **Implemented** | Architecture, role matrix, Day 1 plan, starter API contract |
| Python environment & tooling (`backend/.venv`, `requirements.txt`, `pyrightconfig.json`, `pytest.ini`) | **Implemented** | Python 3.12+ wheel-compatible pins installed and verified |
| Database connection & ORM schema (`core/database.py`, `models/entities.py`) | **Implemented & Tested** | 4 tables, enums, FKs, cascade rules (`4 passed` in pytest) |
| FastAPI bootstrap (`app/main.py`) | **Minimal Stub** | Exposes `GET /` and `GET /api/v1/health` only; `create_tables()` not yet wired |
| Telemetry Provider & Mock Generator (`services/telemetry_provider.py`, `mock_generator.py`) | **Planned** | Interface + synthetic scenarios + `boto3` adapter |
| Event Correlator (`services/correlator.py`) | **Planned** | Rule-based multi-signal correlation |
| ML & AI Layer (`services/ml_detector.py`, `risk_scorer.py`, `ai_explainer.py`) | **Planned** | `IsolationForest`, weighted risk scoring, LLM summary + fallback |
| Domain API Routers (`app/api/*.py`) | **Planned** | `/overview`, `/resources`, `/alerts`, `/traffic`, `/recommendations` |
| Frontend Dashboard (`frontend/`) | **Placeholder Only** | Contains `frontend/init.txt` only; Vite + React + Tailwind app planned |

---

## 3. System Architecture

Because live AWS sandbox credentials are not yet provisioned and initial delivery targets a rapid MVP timeline, the architecture uses a **single-process FastAPI monolith**, **one relational database** (SQLite default for zero-setup dev; PostgreSQL via `DATABASE_URL`), and a **swappable telemetry provider**.

```text
   AWS Environment (Future)              Local Mock Scenarios (Default)
   CloudTrail / CloudWatch / IAM         Synthetic Baseline + Injected
   EC2 / EBS / RDS / S3 / Cost           Waste, Breach & Bot Scenarios
                │                                      │
                └──────────────┬───────────────────────┘
                               ▼
                 TelemetryProvider Interface
                  (DATA_SOURCE=mock | aws)
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
   Rule Correlator       ML Detector           Resource / Backup
   (correlator.py)     (IsolationForest)         Auditor
         └─────────────────────┼─────────────────────┘
                               ▼
                    Unified Risk Scorer
                     (risk_scorer.py)
                               │
                               ▼
                  AI Incident Explainer
              (LLM API + Template Fallback)
                               │
                               ▼
              SQLAlchemy ORM (SQLite / PostgreSQL)
        cloud_resources │ telemetry_metrics │ security_alerts │ recommendations
                               │
                               ▼
                 FastAPI REST API (/api/v1/*)
                               │
                               ▼
            Standalone React Dashboard (frontend/)
```

### Key Architectural Choices
- **Standalone Web App vs. Native AWS Console:** Built as an independent SPA so correlation views, custom risk breakdowns, and AI explanations are not constrained by CloudWatch/Security Hub UIs.
- **Single Relational DB (`JSON` columns over dual Postgres + Elasticsearch/MongoDB):** Structured entities and JSON payloads (correlated event IDs, signal breakdowns, resource metadata) live in one SQLAlchemy schema, avoiding multi-database sync overhead.
- **Provider Abstraction:** Upstream ML, correlation, API routes, and UI never call `boto3` directly; they read normalized telemetry through a `TelemetryProvider` contract.
- **Safe Remediation:** Recommendations transition through human-approved states (`pending` → `approved` / `dismissed`) rather than auto-terminating infrastructure unprompted.

---

## 4. Repository Structure

### Current Files
```text
AWSense/
├── .gitignore                        # Python, venv, *.db/*.sqlite*, pytest cache, Node/Next ignores
├── pyrightconfig.json                # Binds IDE Python analyzer to backend/.venv and backend/ root
├── README.md                         # High-level project overview and architecture
├── docs/
│   ├── api-contract.json             # Starter API contract (GET /api/v1/alerts example)
│   ├── architecture-and-codebase.md  # This reference document
│   ├── day-1-tasks.md                # 5 isolated Day 1 workstreams
│   └── task-distribution.md          # 5-role engineering responsibility matrix (pre/post-AWS)
├── frontend/
│   └── init.txt                      # Placeholder prior to Vite/React scaffold
└── backend/
    ├── .env.example                  # Sample DATABASE_URL and SQL_ECHO settings
    ├── pytest.ini                    # Sets pythonpath=. and testpaths=tests
    ├── requirements.txt              # Python 3.12+ binary-wheel-compatible dependencies
    ├── app/
    │   ├── __init__.py
    │   ├── main.py                   # FastAPI app, permissive CORS, / and /api/v1/health
    │   ├── api/                      # (Empty) Target for domain APIRouter modules
    │   ├── core/
    │   │   ├── __init__.py
    │   │   └── database.py           # Engine factory, Base, SessionLocal, create_tables(), get_db()
    │   ├── models/
    │   │   ├── __init__.py           # Re-exports all ORM classes and enums
    │   │   └── entities.py           # CloudResource, TelemetryMetric, SecurityAlert, Recommendation
    │   └── services/                 # (Empty) Target for telemetry, correlation, ML, and AI modules
    └── tests/
        └── test_database.py          # 4 pytest tests verifying DB config, schema, FKs, and get_db()
```

### Planned Module Targets
- `backend/app/services/telemetry_provider.py` — `TelemetryProvider` base interface + `Boto3TelemetryProvider` stub
- `backend/app/services/mock_generator.py` — `MockTelemetryProvider` & scenario generator
- `backend/app/services/correlator.py` — multi-signal time-window event correlation
- `backend/app/services/ml_detector.py` — Scikit-learn `IsolationForest` anomaly scorer
- `backend/app/services/risk_scorer.py` — weighted composite risk scoring (`0–100`)
- `backend/app/services/ai_explainer.py` — LLM explanation generator with deterministic template fallback
- `backend/app/api/{overview,resources,alerts,traffic,recommendations}.py` — FastAPI routers registered in `app/main.py`
- `frontend/` — Vite + React + Tailwind CSS + Recharts dashboard application

---

## 5. Implemented Codebase Reference

### 5.1 Database Configuration (`backend/app/core/database.py`)
Imports `load_dotenv` against `backend/.env` and configures SQLAlchemy 2.0:
- `DEFAULT_SQLITE_URL`: `sqlite:///<repo>/backend/awsense.db` (POSIX path).
- `get_database_url() -> str`: Returns `os.getenv("DATABASE_URL") or DEFAULT_SQLITE_URL`.
- `Base(DeclarativeBase)`: Shared declarative base for all ORM models.
- `build_engine(database_url: str | None = None) -> Engine`:
  - Reads `SQL_ECHO` (`"true"` enables SQL query logging).
  - For SQLite URLs: sets `connect_args={"check_same_thread": False}` and attaches a `"connect"` listener executing `PRAGMA foreign_keys=ON`.
  - For non-SQLite URLs (e.g., PostgreSQL): enables `pool_pre_ping=True`.
- `engine: Engine`: Module-level engine built from `get_database_url()`.
- `SessionLocal`: `sessionmaker(autocommit=False, autoflush=False, bind=engine)`.
- `create_tables(target_engine: Engine | None = None) -> None`: Imports `app.models.entities` so metadata is registered, then runs `Base.metadata.create_all(bind=target_engine or engine)`.
- `get_db() -> Generator[Session, None, None]`: FastAPI dependency yielding a `Session` and closing it in `finally`.

### 5.2 ORM Models & Enums (`backend/app/models/entities.py`)
All enums inherit from `StrEnum` and are stored via `SqlEnum(..., native_enum=False)` using string values so schemas migrate cleanly between SQLite and PostgreSQL without native enum DDL conflicts.

#### Enums
- `ResourceType`: `ec2` | `ebs` | `rds` | `s3`
- `BackupStatus`: `protected` | `missing` | `outdated` | `not_applicable`
- `AlertSeverity`: `low` | `medium` | `high` | `critical`
- `AlertStatus`: `open` | `investigating` | `resolved` | `dismissed`
- `RecommendationCategory`: `cost` | `security` | `backup`
- `RecommendationState`: `pending` | `approved` | `dismissed`

#### Table: `cloud_resources` (`CloudResource`)
| Column | Type | Constraints / Default | Purpose |
|---|---|---|---|
| `resource_id` | `String(128)` | PK | AWS resource identifier (e.g., `i-0abcd...`, `vol-...`) |
| `name` | `String(255)` | Nullable | Friendly tag or display name |
| `resource_type` | `ResourceType` | Not null, indexed | `ec2`, `ebs`, `rds`, or `s3` |
| `region` | `String(64)` | Not null, indexed | AWS region (e.g., `us-east-1`) |
| `status` | `String(32)` | Not null | Operational state (`running`, `available`, `idle`, etc.) |
| `utilization_pct` | `Float` | Not null, default `0.0` | Current/average utilization percentage |
| `backup_status` | `BackupStatus` | Not null, default `not_applicable` | Backup protection state |
| `last_backup_at` | `DateTime(timezone=True)` | Nullable | Timestamp of most recent snapshot/backup |
| `monthly_cost_usd` | `Float` | Not null, default `0.0` | Estimated monthly resource spend |
| `metadata_json` | `JSON` | Not null, default `dict` | Extra tags, instance type, volume size, etc. |
| `updated_at` | `DateTime(timezone=True)` | Not null, UTC now, `onupdate` | Last record update |

Relationships: `metrics` (`cascade="all, delete-orphan"`), `alerts`, `recommendations` (`cascade="all, delete-orphan"`).

#### Table: `telemetry_metrics` (`TelemetryMetric`)
| Column | Type | Constraints / Default | Purpose |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Row ID |
| `resource_id` | `String(128)` | FK → `cloud_resources.resource_id` (`CASCADE`), indexed | Parent resource |
| `timestamp` | `DateTime(timezone=True)` | Not null, indexed | Sample timestamp |
| `cpu_utilization` | `Float` | Not null, default `0.0` | CPU percentage (`0–100`) |
| `network_in_bytes` | `Float` | Not null, default `0.0` | Inbound network bytes |
| `network_out_bytes` | `Float` | Not null, default `0.0` | Outbound network bytes |
| `request_count` | `Integer` | Not null, default `0` | Request volume in window |
| `anomaly_score` | `Float` | Nullable | Normalized `0.0–1.0` ML anomaly score |

#### Table: `security_alerts` (`SecurityAlert`)
| Column | Type | Constraints / Default | Purpose |
|---|---|---|---|
| `alert_id` | `String(64)` | PK | Alert identifier |
| `resource_id` | `String(128)` | FK → `cloud_resources.resource_id` (`SET NULL`), nullable, indexed | Associated resource if applicable |
| `alert_type` | `String(64)` | Not null, indexed | Category (`behavioral_anomaly`, `bot_traffic`, etc.) |
| `severity` | `AlertSeverity` | Not null, indexed | `low`, `medium`, `high`, or `critical` |
| `risk_score` | `Float` | Not null, default `0.0` | Composite risk score (`0–100`) |
| `title` | `String(255)` | Not null | Short incident headline |
| `correlated_event_ids` | `JSON` (`list[str]`) | Not null, default `list` | Linked CloudTrail/CloudWatch/Billing IDs |
| `signal_breakdown` | `JSON` (`dict[str, Any]`) | Not null, default `dict` | Factor scores (`ml_score`, `iam_risk`, etc.) |
| `ai_summary` | `Text` | Nullable | Human-readable AI incident summary |
| `recommended_actions` | `JSON` (`list[str]`) | Not null, default `list` | Ordered remediation checklist |
| `status` | `AlertStatus` | Not null, default `open`, indexed | Workflow state |
| `created_at` | `DateTime(timezone=True)` | Not null, UTC now, indexed | Alert creation timestamp |

#### Table: `recommendations` (`Recommendation`)
| Column | Type | Constraints / Default | Purpose |
|---|---|---|---|
| `recommendation_id` | `String(64)` | PK | Recommendation identifier |
| `resource_id` | `String(128)` | FK → `cloud_resources.resource_id` (`CASCADE`), indexed | Target resource |
| `category` | `RecommendationCategory` | Not null, indexed | `cost`, `security`, or `backup` |
| `title` | `String(255)` | Not null | Short summary |
| `action` | `Text` | Not null | Specific suggested action |
| `rationale` | `Text` | Nullable | Supporting utilization/risk evidence |
| `estimated_monthly_savings_usd` | `Float` | Not null, default `0.0` | Projected monthly savings |
| `confidence` | `String(16)` | Not null, default `"high"` | Recommendation confidence |
| `state` | `RecommendationState` | Not null, default `pending`, indexed | Approval state (`pending`, `approved`, `dismissed`) |
| `created_at` | `DateTime(timezone=True)` | Not null, UTC now | Creation timestamp |
| `updated_at` | `DateTime(timezone=True)` | Not null, UTC now, `onupdate` | Last state change |

### 5.3 FastAPI Entry Point (`backend/app/main.py`)
- Instantiates `app = FastAPI(title="AWSense API", version="1.0.0")`.
- Enables permissive `CORSMiddleware` (`allow_origins=["*"]` for local dev).
- Exposes `GET /` (`{"status": "ok", "message": "Welcome to AWSense API"}`) and `GET /api/v1/health` (`{"status": "healthy"}`).

### 5.4 Dependencies & Configuration
- `backend/requirements.txt`: Lower-bounded `<next-major` ranges ensuring Python 3.12+ binary wheel installation:
  `fastapi>=0.115.0,<1.0`, `uvicorn>=0.30.0,<1.0`, `pydantic>=2.9.0,<3.0`, `boto3>=1.35.0,<2.0`, `scikit-learn>=1.5.0,<2.0`, `pandas>=2.2.2,<3.0`, `sqlalchemy>=2.0.35,<3.0`, `python-dotenv>=1.0.0,<2.0`, `pytest>=8.0.0,<9.0`, `httpx>=0.27.0,<1.0`.
- `pyrightconfig.json`: Sets `"include": ["backend"]`, `"extraPaths": ["backend"]`, `"venvPath": "backend"`, `"venv": ".venv"` so Pylance/Pyright resolves both third-party packages and `app.*` imports across OSes.
- `backend/pytest.ini`: Sets `pythonpath = .` and `testpaths = tests`.
- `backend/.env.example`: Defaults `DATABASE_URL=sqlite:///./awsense.db`, `SQL_ECHO=false`, with commented PostgreSQL example.

### 5.5 Existing Tests (`backend/tests/test_database.py`)
Currently verified (`4 passed`):
1. `test_get_database_url_fallback_and_override` — checks SQLite fallback and `DATABASE_URL` env override.
2. `test_create_tables_and_roundtrip` — calls `create_tables()`, inserts 1 row into all 4 tables, verifies reads, JSON columns, enums, and ORM relationships.
3. `test_sqlite_foreign_keys_and_delete_behaviors` — confirms missing FK raises `IntegrityError`, deleting `CloudResource` cascades to `TelemetryMetric` and `Recommendation`, and sets `SecurityAlert.resource_id = None`.
4. `test_get_db_dependency_yields_and_closes` — checks `get_db()` generator lifecycle.

---

## 6. Planned Subsystems & Core Scenarios

### Core Detection Scenarios
1. **Resource Waste & Backup Gaps:**
   - EC2 instances averaging low CPU (e.g., ~7%) → downsize/schedule recommendation.
   - Unattached EBS volumes → snapshot & delete recommendation.
   - Critical RDS instances without recent backups/snapshots → backup protection alert (`backup_status = missing`).
2. **IAM Breach + Compute Surge:**
   - Unusual IAM login (off-hours / unseen region) + multiple new EC2 launches + security group change + network traffic jump + daily cost spike → correlated high-risk security & cost incident.
3. **Automated Bot / Scraper Traffic:**
   - High-frequency repetitive requests on specific endpoints → correlated EC2 CPU spike, high network out, and higher daily spend → WAF/rate-limit/caching recommendations.

### Planned Service Responsibilities
- **Telemetry Ingestion (`telemetry_provider.py`, `mock_generator.py`):** Exposes `get_resources()`, `get_metrics()`, `get_cloudtrail_events()`, `get_traffic_logs()`, and `get_cost_usage()`. Default implementation returns deterministic baseline + anomaly scenarios; `Boto3TelemetryProvider` implements the same interface when AWS sandbox credentials exist.
- **ML Anomaly Detection (`ml_detector.py`):** Trains/runs Scikit-learn `IsolationForest` on `[cpu_utilization, network_in_bytes, network_out_bytes, request_count]` vectors and normalizes output to `0.0–1.0`.
- **Event Correlation (`correlator.py`):** Groups IAM/CloudTrail events, metric spikes, traffic anomalies, and billing jumps within a time window into linked `correlated_event_ids`.
- **Unified Risk Scoring (`risk_scorer.py`):** Combines `ml_score`, `iam_risk`, `resource_impact`, `cost_impact`, and `traffic_anomaly` into a `0–100` score and `low|medium|high|critical` severity.
- **AI Explainer (`ai_explainer.py`):** Formats correlated signals into an LLM prompt to produce `ai_summary` and `recommended_actions`, with a deterministic template fallback when no LLM API key is configured.

### Planned API Endpoints (`/api/v1`)
- `GET /api/v1/overview` — Global health score, active incident summary, total estimated monthly savings, metric/cost trend series.
- `GET /api/v1/resources` — Resource inventory (`CloudResource`), utilization, and backup status.
- `GET /api/v1/alerts` — Correlated `SecurityAlert` feed with `signal_breakdown` and `ai_summary` (starter shape documented in `docs/api-contract.json`).
- `GET /api/v1/traffic` — Request volume time-series, flagged endpoint patterns, and resource/cost impact.
- `GET /api/v1/recommendations` — Prioritized cost/security/backup `Recommendation` list.
- `POST /api/v1/recommendations/{id}/action` — Transition recommendation `state` (`approved` / `dismissed`).
- `POST /api/v1/simulate` — Injects a live breach or bot scenario for demonstration.

### Planned Frontend Views (`frontend/`)
Vite + React + Tailwind CSS + Recharts dark-mode SPA with 5 navigation pages:
1. **Overview** — KPI stat cards, risk indicator, correlated telemetry charts.
2. **Resources & Backups** — Filterable inventory table with utilization & backup warnings.
3. **Security & Correlation** — Alert feed, risk factor breakdown, AI incident explanation panel.
4. **Traffic & Bots** — Request rate vs. CPU/cost charts and bot pattern flags.
5. **Recommendations** — Action cards with savings estimates and `Approve` / `Dismiss` controls.

---

## 7. Local Setup & Verification Commands

### Environment Setup (Windows PowerShell)
Using `uv` with Python 3.12 and prebuilt wheels only (avoids C++ source builds on Windows):
```powershell
uv venv backend\.venv --python 3.12
uv pip install --python backend\.venv\Scripts\python.exe --only-binary :all: -r backend\requirements.txt
```
*(Fallback with standard `venv`/`pip`: `python -m venv backend\.venv` then `backend\.venv\Scripts\pip install -r backend\requirements.txt`.)*

Optional environment file:
```powershell
Copy-Item backend\.env.example backend\.env
```

### Running Tests
From repository root:
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -v
```
*(Or inside `backend/`: `.\.venv\Scripts\python.exe -m pytest -v`.)*

### Running the Backend Server
From `backend/`:
```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```
Interactive OpenAPI docs are served at `http://localhost:8000/docs`.

---

## 8. Design Decisions & Known Caveats

1. **PostgreSQL Driver Not Installed by Default:** `DATABASE_URL` supports PostgreSQL URLs in `build_engine()`, but `psycopg2-binary` (or `psycopg`) is not yet in `backend/requirements.txt`. Add it before connecting to a live Postgres server.
2. **No Schema Migrations (Alembic):** Tables are created via `Base.metadata.create_all()` (`create_tables()`). Modifying columns on existing models requires deleting and recreating local `awsense.db` (or dropping/recreating tables in Postgres).
3. **`create_tables()` Startup Wiring:** `backend/app/main.py` does not call `create_tables()` yet; wire it into FastAPI lifespan/startup once the API routers are integrated.
4. **SQLite Timezone Stripping:** `DateTime(timezone=True)` works across both engines, but SQLite returns naive `datetime` instances on read while PostgreSQL returns timezone-aware `datetime` instances. Normalize `tzinfo` before comparing timestamps in Python.
5. **FastAPI `TestClient` / `httpx` Warning:** Starlette 1.10 logs a `StarletteDeprecationWarning` preferring `httpx2` over `httpx` when importing `TestClient`. Note also that `TestClient` spawns an internal AnyIO portal socketpair that can hang inside restricted Windows sandboxes; run HTTP-level tests in a normal terminal.
6. **IDE Analyzer Alignment:** If VS Code / Antigravity IDE flags imports after pulling or recreating `.venv`, run **Python: Restart Language Server** so it reloads `pyrightconfig.json`.
