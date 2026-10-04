# AGENT.md

Primary guide for anyone working on this repository, human or automated.
Read this before changing code.

## 1. What this project is

Rain Corrector forecasts district-level daily rainfall, stores every issuance,
scores matured forecasts against observations, and serves the result through a
dashboard with an OpenStreetMap-based map.

Three parts, each independently runnable and deployable:

| Directory | Runs as | Owns |
| --- | --- | --- |
| `frontend/` | Next.js app server | Presentation, client state, map |
| `backend/` | FastAPI server | API contracts, orchestration, verification, inference |
| `ml/` | Batch jobs and notebooks | Data, features, training, evaluation, artifacts |

Authoritative real-world telemetry datasets from the Central Water Commission (CWC)
and Central Pollution Control Board (CPCB) are integrated for Maharashtra State and the
Godavari Basin (2021–2025). Full provenance and schema details are in DATASETS.md.

## 2. Directory responsibilities

### `backend/app/`

| Path | Responsibility | Must not contain |
| --- | --- | --- |
| `api/routes/` | HTTP concerns: parsing, status codes, OpenAPI metadata | Business logic, SQL, model calls |
| `schemas/` | Pydantic request/response contracts | Database models, queries |
| `services/` | Business logic and orchestration | Raw SQL, HTTP types |
| `repositories/` | All database access | Business rules, HTTP concerns |
| `models/` | SQLAlchemy ORM definitions | Query logic, business rules |
| `ml/` | Inference: artifact registry, predictor, serving features | Training, data access beyond history reads |
| `core/` | Config, engine, logging, security, exceptions | Feature logic |
| `utils/` | Small stateless helpers | Anything with dependencies on services |
| `data/providers/` | External data source abstraction | Direct provider SDK calls elsewhere |

Layering is one-directional: `api → services → repositories → database`.
Services may call `ml/`; repositories never call `ml/`.

### `frontend/`

| Path | Responsibility |
| --- | --- |
| `app/` | Routes only; server components fetch nothing directly |
| `features/<name>/components/` | Feature UI |
| `features/<name>/hooks/` | Feature data hooks wrapping TanStack Query |
| `components/` | Reusable UI shared across features |
| `services/` | The only place `fetch` appears |
| `lib/` | Config, formatters, severity tokens, query keys |
| `hooks/` | Cross-feature hooks |
| `types/` | Types mirroring the API contract |

### `ml/src/rainml/`

| Module | Responsibility |
| --- | --- |
| `data/` | Loading, cleaning, validation, the chronological split |
| `features/` | Feature engineering, selection, preprocessing |
| `models/` | Baselines, candidates, artifact registry |
| `training/` | Configuration and the reproducible pipeline |
| `evaluation/` | Metrics, comparison, selection |
| `inference/` | Serving-side preprocessing and prediction |

`rainml` must not import from `backend`. The backend adapts to `rainml`, not the
other way round.

## 3. How the parts communicate

```text
Frontend  ──HTTP (JSON, /api/v1)──>  FastAPI routes
                                          │
                                          ▼
                                       Services
                                     ┌────┴────┐
                                     ▼         ▼
                                Repositories   ml/ (inference)
                                     │         │
                                     ▼         ▼
                                PostgreSQL   ml/artifacts/<version>/
```

- The frontend calls only the API. It never imports `rainml`, never opens a
  database connection, and never calls an external provider directly.
- The backend calls a model only through `app/ml/registry.py`, which caches the
  active artifact in-process and reloads it only when the version changes.
- Training reads the dataset, writes an artifact directory, and records rows.
  It does not serve traffic.

## 4. How training works

`rainml.training.trainer.run_training` runs the whole pipeline:

```text
load → validate → clean → engineer features → assert no leakage
     → chronological split → fit baselines → fit candidates
     → score on validation → select → rescore on test
     → fit quantile models → write artifact → record run
```

Invoked by:

- `scripts/run_training.py` (CLI, used by setup and by Docker)
- `ml/notebooks/04_model_training.ipynb` (same function, for inspection)

It takes `(observations_path, districts_path, artifact_root, config,
register_run)` and returns a `TrainingReport`. It raises nothing for a failed
run; it returns `status="failed"` with `error` set, so the caller can record the
failure.

### Artifacts

One directory per version under `ml/artifacts/<version>/`:

```text
model.joblib            fitted pipeline (preprocessor + regressor)
lower_model.joblib      10th percentile pipeline
upper_model.joblib      90th percentile pipeline
preprocessor.joblib     fitted ColumnTransformer
feature_columns.json    exact training-time feature order
metadata.json           model card
metrics.json            split metrics for every baseline and candidate
checksum.txt            sha256 of model.joblib
```

Versions are immutable. A retraining run writes a new directory; `save_artifact`
raises `FileExistsError` rather than overwriting, because the database still
references the old artifact.

## 5. Model lifecycle and promotion

`model_versions.status` is the single source of truth for what the API serves.

```text
candidate ──promote──> validated ──promote──> active ──> archived
                                                    (replaced by a newer active)
```

Policies, selected by `DEFAULT_PROMOTATION_POLICY` or a request override:

| Policy | Behaviour |
| --- | --- |
| `auto_promote_if_better` | Default. Requires the candidate to have a lower verified MAE **and** at least as many scored forecasts as the incumbent. |
| `manual_only` | Records the intent but never activates. Use for review gates. |
| `force` | Activates unconditionally, including an archived version. |

Promotion is never automatic. Training registers a `candidate`; only
`POST /api/v1/models/promote` changes what is served. A promotion reloads the
process-local registry and reports whether the reload succeeded.

`MODEL_VERSION` in the environment pins a version and overrides the database
flag, which is what a reproducible evaluation deployment does.

## 6. Forecast verification

The contract, enforced in `VerificationService`:

1. A forecast has `issued_at` and `target_time`.
2. Nothing is scored until `target_time` is older than
   `VERIFICATION_GRACE_PERIOD_HOURS`. The grace period exists because an
   accumulation window is still open immediately after it ends.
3. Scoring requires a `district_aggregates` row whose window *contains* the
   target time and was computed no earlier than that window closed.
   `_assert_no_leakage` raises if the window is misplaced.
4. A forecast with no matching observation is recorded as
   `missing_observation` and stays pending. It is never scored as zero and never
   silently dropped.
5. Both timestamps are stored (`issued_at`, `verified_at`, `observed_at`) so the
   ordering is auditable afterwards.

Leakage prevention is a hard requirement, not a preference:

- `build_training_frame` computes every rolling window from `shift(1)` series,
  so the issue day is never an input.
- `chronological_split` cuts on **date boundaries**. Every district shares an
  issue date, so a row-count split would slice through a date. `validate_split`
  re-checks the three partitions and fails the run on overlap.
- `assert_no_leakage` compares the antecedent feature against the target and
  fails if they mirror each other.
- `ml/tests/test_features.py` asserts that serving-time features equal
  training-time features for the same day. This test has already caught two real
  train/serve mismatches; do not weaken it.

## 7. Database

PostgreSQL, normalised, migrated by Alembic. Never modify a live schema without
a migration.

| Table | Purpose |
| --- | --- |
| `regions`, `districts`, `stations` | Geography; `districts` is the spatial unit |
| `observations` | Station readings per window |
| `district_aggregates` | Daily district rainfall derived from stations |
| `forecast_runs` | One model issuance at one base time |
| `forecasts` | District forecast within a run |
| `forecast_values` | Per-lead-time steps |
| `verification_results` | Scores for one forecast; unique on `forecast_id` |
| `verification_batches` | Audit record of one verification job |
| `model_versions` | Artifact registry and promotion state |
| `training_runs` | Training execution history |
| `alerts` | Heavy rainfall alerts |
| `users`, `api_keys` | Optional API key auth |

Conventions:

- Timestamps are `TIMESTAMP WITH TIME ZONE` and always UTC-aware in Python.
- Both `observed_at` (when it happened) and `recorded_at` (when we learned it)
  are stored where the distinction matters.
- Enums are Python `StrEnum` in `app/core/enums.py`, mirrored by PostgreSQL
  `Enum` types. Adding a value requires a migration.
- Indexes exist on the columns the API actually filters: `district_id`,
  `target_time`, `observed_at`, `status`, `version`.
- `origin` (`observed` / `synthetic` / `external`) marks provenance on every
  measurement row.

Schema changes:

```bash
backend/.venv/bin/alembic -c database/alembic.ini revision --autogenerate -m "add x"
backend/.venv/bin/alembic -c database/alembic.ini upgrade head
```

Read the generated migration before committing. `alembic.ini` takes its URL from
settings, never from the file.

## 8. Environment variables

Backend and ML read from the repository root `.env`. Full list in
[`.env.example`](.env.example).

| Variable | Default | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `DEBUG` | `true` | |
| `ASYNC_DATABASE_URL` | localhost:55432 | async driver, used at runtime |
| `DATABASE_URL` | localhost:55432 | sync driver, used by Alembic |
| `CORS_ORIGINS` | `http://localhost:3000` | comma separated |
| `SECRET_KEY` | insecure default | **HMAC pepper for API keys. Must be changed.** |
| `ENABLE_API_KEY_AUTH` | `false` | when true, data routes need `X-API-Key` |
| `MODEL_ARTIFACT_PATH` | `ml/artifacts` | |
| `MODEL_VERSION` | unset | pins a version, overrides the DB flag |
| `MODEL_LOAD_ON_STARTUP` | `true` | |
| `ML_RANDOM_SEED` | `42` | |
| `VERIFICATION_GRACE_PERIOD_HOURS` | `6` | |
| `DEFAULT_FORECAST_HORIZON_HOURS` | `24` | |
| `DEFAULT_PROMOTION_POLICY` | `auto_promote_if_better` | |
| `RETRAINING_MIN_INTERVAL_HOURS` | `168` | |
| `ENABLE_EXTERNAL_INGESTION` | `false` | |
| `DATA_PROVIDER` | `local_csv` | `local_csv` or `open_meteo` |
| `NEXT_PUBLIC_API_BASE_URL` | localhost:8000/api/v1 | baked into the bundle |
| `NEXT_PUBLIC_MAP_TILE_URL` | OSM standard | `{z}/{x}/{y}` template |
| `NEXT_PUBLIC_MAP_ATTRIBUTION` | OSM attribution | provider-required text |

Frontend variables prefixed `NEXT_PUBLIC_` are visible to the browser. Nothing
secret may use that prefix.

## 9. Commands

### Local development

```bash
./scripts/setup.sh                                  # full first-time setup
backend/.venv/bin/uvicorn app.main:app --reload     # API
cd frontend && npm run dev                          # UI
ml/.venv/bin/jupyter lab ml/notebooks               # notebooks
./scripts/serve_backend.sh                          # API in the background
```

### Database

Migrations live in `database/` at the repository root, not under `backend/`,
because they describe the whole system. They can be run from anywhere.

```bash
backend/.venv/bin/alembic -c database/alembic.ini upgrade head
backend/.venv/bin/alembic -c database/alembic.ini revision --autogenerate -m "msg"
backend/.venv/bin/python scripts/seed_data.py
```

### Data and models

```bash
ml/.venv/bin/python scripts/generate_demo_dataset.py
ml/.venv/bin/python scripts/run_training.py
./scripts/run_jobs.sh forecast      # issue a run, then verify matured ones
./scripts/run_jobs.sh retrain       # train and register a candidate
```

### Tests

```bash
cd backend  && .venv/bin/python -m pytest tests/ -q
cd ml       && .venv/bin/python -m pytest tests/ -q
cd frontend && npm test
```

### Linting, formatting, typing

```bash
cd backend  && .venv/bin/ruff check app tests && .venv/bin/black --check app tests && .venv/bin/mypy app
cd ml       && .venv/bin/ruff check src tests && .venv/bin/black --check src tests && .venv/bin/mypy src
cd frontend && npm run lint && npm run format:check && npm run typecheck
```

### Build and deploy

```bash
cd frontend && npm run build
docker compose --profile app up -d
```

## 10. Conventions

### Naming

| Kind | Convention | Example |
| --- | --- | --- |
| Python module | `snake_case` | `verification_service.py` |
| Python class | `PascalCase` | `VerificationService` |
| Python function/method | `snake_case`, verb-first | `run_verification` |
| Python constant | `UPPER_SNAKE` | `HISTORY_DAYS` |
| TypeScript component | `PascalCase` | `ForecastExplorer` |
| TypeScript hook | `useThing` | `useMapForecasts` |
| TypeScript type | `PascalCase`, no `I` prefix | `ForecastDetail` |
| API path | plural, kebab | `/forecast-runs` → `/forecasts/runs` |
| Database table | plural `snake_case` | `district_aggregates` |
| Test | `test_<behaviour>` | `test_leakage_is_detected` |

### Python

- Type hints on every public function. `mypy` runs in strict-enough mode; do not
  silence errors with `# type: ignore` unless a third-party stub is genuinely
  wrong, and say so in a comment.
- No bare `except Exception` outside service boundaries. Catch the specific
  error and let the service layer translate it.
- Async all the way down. `await` every repository call.
- No module-level mutable state except the model registry, which is
  thread-safe by design and reset by a test fixture.

### TypeScript

- `strict: true` plus `noUncheckedIndexedAccess`. No `any` without a comment
  explaining why.
- `import type` for type-only imports.
- Components return JSX; no logic beyond view composition in a component file.
- Shared components live in `components/`; feature-specific ones stay in the
  feature.

### API

- Versioned under `/api/v1`. A breaking change gets `/api/v2`.
- Routes declare `response_model`, `summary` and `description`; every operation
  is covered by a test that asserts no operation is undocumented.
- Collections accept `page` and `page_size` and return
  `{"items": [...], "meta": {...}}`.
- Errors return
  `{"error": {"code", "message", "details"}, "request_id", "timestamp"}`.
  Never a stack trace, never an ORM message.
- Input is validated by Pydantic. Validation errors list the offending field.
- Every response carries `X-Request-ID` and `X-Process-Time`.

### Comments

Only where a future maintainer genuinely needs the reasoning:

- a non-obvious algorithmic decision
- a mathematical formula
- a library limitation and the workaround
- a business rule
- a security consideration
- a temporal or data-leakage constraint

Never restate what the code does. No "this function handles", "we use X
because", "here we", "robust implementation", or any mention of AI authorship.
If a comment could be deleted without information loss, delete it.

### Git

- Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`,
  `chore:`, `perf:`.
- One logical change per commit.
- Update `ARCHITECTURE.md` in the same commit as any architectural change.
- Update `AGENT.md` when a command, convention or invariant changes.

## 11. Rules for AI/Coding Agents

### Hard rules

1. **No new feature without the data behind it.** Every number in the UI must
   come from a persisted fact. Never fabricate a metric, a chart series or a
   placeholder response to make a screen look finished.
2. **The frontend talks only to the API.** No direct database access, no direct
   `rainml` import, no direct call to an external provider. Add a service layer
   entry point instead.
3. **Never train a model in a request handler.** Inference loads a versioned
   artifact; training is a batch job.
4. **Never weaken a leakage guard.** `assert_no_leakage`, `validate_split` and
   `_assert_no_leakage` exist because the failure is invisible in the score. If
   a guard fires, fix the code that trips it.
5. **Never use a random train/test split for time series.** Use
   `chronological_split`.
6. **Artifacts are immutable.** Train a new version. Do not overwrite a
   directory that `model_versions` may reference.
7. **Never promote a model implicitly.** Training creates a `candidate`.
8. **No secrets in source or in `.env`.** Read from settings. API keys are stored
   as HMAC-SHA256 digests and never logged.
9. **No `TODO`, `FIXME`, `NotImplementedError`, or stubbed-out logic in merged
   code.** If an external dependency is genuinely unavailable, define a provider
   interface, implement the parts that are possible, and document the integration
   point in `docs/`.
10. **No `TODO` disguised as a comment.** A comment explaining why something is
    not done yet belongs in an issue, not the code.
11. **A failing test blocks a commit.** If a test is wrong, fix it in its own
    commit with the reasoning in the message.
12. **Every new endpoint needs a test** covering the success path, at least one
    failure path, and the response contract.
13. **Schema changes require a migration**, generated with Alembic and reviewed
    before committing.

### Before you finish

Run all of these and make them pass:

```bash
cd backend  && .venv/bin/ruff check app tests database && .venv/bin/python -m pytest tests/ -q && .venv/bin/mypy app
cd ml       && .venv/bin/ruff check src tests && .venv/bin/python -m pytest tests/ -q && .venv/bin/mypy src
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

Then verify, by reading rather than assuming:

- [ ] No secrets, tokens or real credentials anywhere
- [ ] No `fetch` outside `frontend/services/`
- [ ] No SQL outside `backend/app/repositories/`
- [ ] No business logic in `backend/app/api/routes/`
- [ ] No `from app...` import anywhere in `ml/`
- [ ] No duplicated implementation of a feature that already exists elsewhere
- [ ] No AI-style comments
- [ ] `ARCHITECTURE.md` still matches the code
- [ ] Every metric shown in the UI traces to a database column

## 12. Do not change without architectural review

| Item | Why it is load-bearing |
| --- | --- |
| `Base.metadata` naming convention | Renaming an index changes migration output and invalidates existing migrations |
| The severity bands in `app/services/severity.py` | The map legend, alert thresholds and stored `severity` values all derive from them. Changing them invalidates historical rows |
| The `FEATURE_COLUMNS` contract | The persisted preprocessor is fitted to that exact order |
| `chronological_split` semantics | Every reported score depends on it |
| The verification grace period | Lowering it can score forecasts against open accumulation windows |
| `model_versions.status` values | The registry and the promotion policy key off them |
| The API error envelope shape | The frontend `ApiError` parses it |
| `MODEL_ARTIFACT_PATH` layout | Both `rainml` and the backend registry depend on the directory shape |
| CORS and the versioned prefix | A proxy or gateway in front of the API depends on them |

If one of these genuinely must change, update `ARCHITECTURE.md`, add a
migration where it touches stored data, and call it out explicitly in the pull
request description.
