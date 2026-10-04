# Rain Corrector

District-level daily rainfall forecasting with built-in forecast verification.

The system issues a rainfall forecast for every district from a versioned model
artifact, stores each issuance for later scoring, and compares matured forecasts
against observations to produce skill metrics that are displayed on the
dashboard. Forecasts, observations, verification results, model versions and
training runs are all persisted in PostgreSQL.

> **Data provenance.** The system is trained on **authoritative real-world telemetry datasets**
> from the **Central Water Commission (CWC)** and **Central Pollution Control Board (CPCB)**,
> acquired from the **National Water Data Portal (NWDP)** for Maharashtra State and the Godavari
> River Basin (2021–2025, 217.63 MB raw size, $\le 1$ GB budget). All models and forecast evaluations
> reflect measured observations. Full acquisition details, quality control, and schema specifications
> are documented in [DATASETS.md](DATASETS.md) and machine-readable [data/metadata/datasets.json](data/metadata/datasets.json).

---

## Features

- **Forecasting** — a scikit-learn gradient boosting model predicts 24 h
  accumulation per district, with 10th/90th percentile bounds from fitted
  quantile regressors.
- **Versioned models** — every training run writes an immutable artifact
  directory plus a model card; a database flag selects which version is served.
- **Verification** — forecasts are scored only after the target period has
  elapsed, using continuous (MAE, RMSE, bias, NSE) and categorical (POD, FAR,
  CSI, Brier) metrics, broken down by lead time and severity.
- **Interactive map** — OpenStreetMap tiles with severity-coloured district
  markers, a run selector, severity filters, popups and a legend.
- **Alerts** — heavy-rain forecasts raise alerts that operators can acknowledge.
- **Model registry** — inspect version metadata, training history and promote a
  candidate under a configurable policy.
- **Reproducible training** — a fixed seed, a chronological split and a
  persisted pipeline mean the same dataset and config give the same artifact.

## Architecture

```text
frontend (Next.js)  ──HTTP──>  backend (FastAPI)  ──>  PostgreSQL
                                        │
                                        └──>  ml/artifacts/<version>/
                                             (preprocessor + regressor)
```

Three deployable parts, no shared runtime:

| Part | Stack | Responsibility |
| --- | --- | --- |
| `frontend/` | Next.js, React, TypeScript, TanStack Query, Recharts, Leaflet | Dashboard, map, charts, alerts |
| `backend/` | FastAPI, SQLAlchemy, Alembic, Pydantic | API, orchestration, verification, inference |
| `ml/` | scikit-learn, pandas, Jupyter | Feature engineering, training, evaluation, artifacts |

The frontend never talks to the database or to a model artifact. Training never
runs inside an API request.

Full detail, including sequence diagrams and the promotion policy, is in
[ARCHITECTURE.md](ARCHITECTURE.md). Conventions for coding agents are in
[AGENT.md](AGENT.md).

## Tech stack

**Frontend** — Next.js 15 (App Router), React 19, TypeScript (strict), Tailwind
CSS, TanStack Query, Zod, Recharts, Leaflet + React Leaflet, Vitest, Testing
Library, ESLint, Prettier.

**Backend** — Python 3.12, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy
2.0 (async), asyncpg, Alembic, structlog, pytest, pytest-asyncio, Ruff, Black,
mypy.

**ML** — Python 3.12, scikit-learn, pandas, NumPy, JupyterLab, joblib, pytest,
Ruff, Black, mypy.

**Infrastructure** — PostgreSQL 16, Docker, Docker Compose.

## Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 14+ (16 recommended), either local or via Docker
- Optional: Docker for the containerised stack

## Installation

```bash
git clone <repository-url> rain-corrector
cd rain-corrector
./scripts/setup.sh
```

`setup.sh` creates both virtualenvs, installs dependencies, copies `.env.example`
to `.env`, waits for PostgreSQL, runs migrations, generates the demo dataset,
trains the first model and seeds the database.

Skip steps with `./scripts/setup.sh --skip-train` or `--skip-frontend`.

### Environment setup

```bash
cp .env.example .env
```

Every variable is documented inline in [`.env.example`](.env.example). The ones
that usually need changing:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Where the database is |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Database credentials |
| `DATABASE_URL`, `ASYNC_DATABASE_URL` | Full URLs; derived if omitted |
| `CORS_ORIGINS` | Comma separated allowed frontend origins |
| `SECRET_KEY` | HMAC pepper for API keys — **must** be changed for deployment |
| `MODEL_ARTIFACT_PATH` | Where versioned artifacts live |
| `MODEL_VERSION` | Pin a specific version, overriding the database flag |
| `NEXT_PUBLIC_API_BASE_URL` | API base URL the browser uses |
| `NEXT_PUBLIC_MAP_TILE_URL` | OpenStreetMap-compatible tile template |
| `NEXT_PUBLIC_MAP_ATTRIBUTION` | Attribution required by the tile provider |

`SECRET_KEY` is the only value that is unsafe to leave at its default.

### Database setup

The database must exist before migrations run:

```bash
docker run -d --name rain_corrector_db \
  -e POSTGRES_USER=rain -e POSTGRES_PASSWORD=rain_dev_password \
  -e POSTGRES_DB=rain_corrector \
  -p 55432:5432 postgres:16-alpine

backend/.venv/bin/alembic -c database/alembic.ini upgrade head
```

`scripts/seed_data.py` populates geography, observations, the active model, a
backfill of forecast runs, alerts and verification results. It is idempotent.

### Running the backend

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- API docs: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI: <http://localhost:8000/openapi.json>
- Readiness: <http://localhost:8000/api/v1/health/ready>

### Running the frontend

```bash
cd frontend
npm run dev
```

Dashboard at <http://localhost:3000>. The frontend reads
`NEXT_PUBLIC_API_BASE_URL`, so it must point at the running backend.

### Running the notebooks

```bash
cd ml
.venv/bin/jupyter lab notebooks
```

The notebooks call `rainml` for all real work; they orchestrate and visualise
rather than reimplement. They resolve paths from the repository root, so they run
from any working directory. To execute them headlessly:

```bash
cd ml/notebooks
../.venv/bin/python -m jupyter nbconvert --to notebook --execute \
  01_data_exploration.ipynb --output 01_data_exploration.executed.ipynb
```

| Notebook | Question it answers |
| --- | --- |
| `01_data_exploration` | Coverage, distribution, seasonality, provenance |
| `02_data_preprocessing` | What cleaning removes, keeps and imputes |
| `03_feature_engineering` | Feature construction and the leakage checks |
| `04_model_training` | Pipeline run, baseline comparison, reproducibility |
| `05_model_evaluation` | Error distribution, event detection, skill, interval coverage |
| `06_forecasting_and_verification` | Serving-shaped inference and rolling verification |

### Data acquisition, preprocessing & pipeline

```bash
# 1. Download official telemetry from Central Water Commission & CPCB (NWDP)
ml/.venv/bin/python scripts/download_data.py

# 2. Enforce dataset storage limits (<= 1 GB preferred, <= 5 GB hard max)
ml/.venv/bin/python scripts/validate_data.py --fail-on-missing

# 3. Clean telemetry, impute short gaps (<= 6h), and build zero-leakage features
ml/.venv/bin/python scripts/preprocess_data.py

# 4. Train baseline and candidate models on real data
ml/.venv/bin/python scripts/train.py --promote

# 5. Evaluate model holdout metrics (MAE, RMSE, NSE, POD, FAR, CSI)
ml/.venv/bin/python scripts/evaluate.py

# 6. Issue real-time district forecasts with prediction intervals
ml/.venv/bin/python scripts/predict.py --districts MH-NAS,MH-JAL,MH-KOL
```

### Training models

```bash
ml/.venv/bin/python scripts/run_training.py
```

Options: `--config`, `--version`, `--seed`, `--no-register`, `--promote`,
`--json`. The run trains, compares against four baselines, selects the best
candidate on the validation split, rescores on the untouched test split, writes
`ml/artifacts/<version>/` and records a `training_runs` row plus a
`model_versions` row in `candidate` status.

A candidate does **not** become the served model until it is promoted:

```bash
curl -X POST localhost:8000/api/v1/models/promote \
  -H 'Content-Type: application/json' \
  -d '{"target_version": "v002"}'
```

With the default `auto_promote_if_better` policy the request is refused unless
the candidate beats the active model on verified MAE with at least as many
scored forecasts.

## Running tests

```bash
# Backend — needs PostgreSQL, truncates between tests
cd backend && .venv/bin/python -m pytest tests/ -q

# ML — some tests use the demo dataset and a trained artifact
cd ml && .venv/bin/python -m pytest tests/ -q

# Frontend
cd frontend && npm test
```

## Linting and formatting

```bash
cd backend
.venv/bin/ruff check app tests database
.venv/bin/black --check app tests database
.venv/bin/mypy app

cd ml
.venv/bin/ruff check src tests
.venv/bin/black --check src tests
.venv/bin/mypy src

cd frontend
npm run lint
npm run format:check
npm run typecheck
```

## Build

```bash
# Frontend production bundle (static prerender plus client islands)
cd frontend && npm run build

# Model artifacts are produced by the training pipeline, not a build step
ml/.venv/bin/python scripts/run_training.py
```

## Docker setup

```bash
cp .env.example .env
docker compose up -d db
docker compose --profile app up -d backend frontend
docker compose --profile ml run --rm ml python scripts/run_training.py
```

The backend container mounts `ml/artifacts` read-only, so a model trained on the
host is served unchanged. The `ml` service is a one-shot training environment, not
a long-running process.

## Project structure

```text
rain-corrector/
├── AGENT.md                  conventions and rules for coding agents
├── ARCHITECTURE.md           system design, diagrams, decisions
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── app/
│   │   ├── api/routes/       HTTP layer, versioned
│   │   ├── core/             config, database, logging, security, errors
│   │   ├── models/           SQLAlchemy ORM
│   │   ├── schemas/          Pydantic request/response contracts
│   │   ├── services/         business logic
│   │   ├── repositories/     data access
│   │   ├── ml/               inference: registry, predictor, features
│   │   └── data/providers/   external data source abstraction
│   └── tests/
├── frontend/
│   ├── app/                  routes (App Router)
│   ├── components/           shared UI
│   ├── features/             dashboard, map, forecast, verification, alerts, models
│   ├── hooks/ lib/ services/ types/
│   └── tests/
├── ml/
│   ├── src/rainml/           data, features, models, training, evaluation, inference
│   ├── notebooks/            six notebooks
│   ├── configs/              training.yaml
│   ├── artifacts/            versioned model artifacts
│   └── tests/
├── database/                 alembic.ini, migrations, seeds
├── data/{raw,processed,external}/
├── docs/{api,ml,deployment,diagrams}/
└── scripts/                  setup, seed, training, jobs
```

## API documentation

Interactive docs at `/docs`. Endpoint-by-endpoint reference in
[`docs/api/README.md`](docs/api/README.md).

| Group | Prefix | Purpose |
| --- | --- | --- |
| health | `/api/v1/health` | Liveness and readiness |
| locations | `/api/v1/locations` | Regions, districts, stations |
| observations | `/api/v1/observations` | Ingestion and district aggregates |
| forecasts | `/api/v1/forecasts` | Query, issuance, map, detail |
| verification | `/api/v1/verification` | Results, metrics, job runs |
| models | `/api/v1/models` | Registry, training history, promotion |
| alerts | `/api/v1/alerts` | Heavy rainfall alerts |
| dashboard | `/api/v1/dashboard` | Aggregated dashboard payload |

## Troubleshooting

**`ModelUnavailableError` on startup** — no artifact matches the active model.
Run `ml/.venv/bin/python scripts/run_training.py`, then
`POST /api/v1/models/promote` or set `MODEL_VERSION`. Check
`GET /api/v1/health/ready` for which versions exist on disk.

**Frontend shows "Could not reach the API"** — the backend is not running or
`NEXT_PUBLIC_API_BASE_URL` is wrong. `NEXT_PUBLIC_*` values are baked in at build
time, so restart `npm run dev` after changing them.

**Dashboard is empty** — the database has no forecasts. Run
`backend/.venv/bin/python scripts/seed_data.py`.

**Backend tests fail to connect** — `ASYNC_DATABASE_URL` must point at a running
PostgreSQL instance. The suite truncates tables between tests; point it at a
disposable database.

**`the number of query arguments cannot exceed 32767`** — an insert batch is
larger than one asyncpg statement allows. Ingestion chunks inserts internally;
if you write a new bulk writer, chunk it too.

**Port already in use** — change `POSTGRES_PORT`, `BACKEND_PORT` or
`FRONTEND_PORT`; the defaults (55432, 8000, 3000) avoid the common clashes.

**OSM tiles do not load** — `NEXT_PUBLIC_MAP_TILE_URL` must contain `{z}`, `{x}`
and `{y}`. Respect the provider's usage policy; the bundled default is fine for
development, not for heavy production traffic.

## License

Provided as an engineering reference implementation. Add a LICENSE file before
any redistribution.
