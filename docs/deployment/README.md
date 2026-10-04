# Deployment

## Local development

```bash
./scripts/setup.sh
cd backend && .venv/bin/uvicorn app.main:app --reload
cd frontend && npm run dev
```

## Docker Compose

```bash
cp .env.example .env
docker compose up -d db
docker compose --profile app up -d backend frontend
```

Training, on demand:

```bash
docker compose --profile ml run --rm ml python scripts/run_training.py
```

The `ml` service is a one-shot environment, not a long-running process. The
backend mounts `ml/artifacts` read-only, so a model trained on the host is served
unchanged.

## Images

| Service | Base | Contents |
| --- | --- | --- |
| `db` | `postgres:16-alpine` | Healthcheck-gated |
| `backend` | `python:3.12-slim` | API only. No training code. Non-root (uid 10001) |
| `frontend` | `node:22-alpine` | Multi-stage; standalone Next output. Non-root (uid 10001) |
| `ml` | `python:3.12-slim` | Training and notebooks. Batch only |

## Configuration

Every variable is documented in [`.env.example`](../../.env.example). Before any
deployment that is reachable by anyone else:

| Variable | Requirement |
| --- | --- |
| `SECRET_KEY` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENABLE_API_KEY_AUTH` | `true`, and distribute keys out of band |
| `POSTGRES_PASSWORD` | Not the development default |
| `ENVIRONMENT` | `production` |
| `CORS_ORIGINS` | The real frontend origin, not `*` |
| `NEXT_PUBLIC_API_BASE_URL` | The public API URL. Baked in at build time |
| `NEXT_PUBLIC_MAP_TILE_URL` | A provider whose usage policy permits the traffic |
| `NEXT_PUBLIC_MAP_ATTRIBUTION` | The attribution that provider requires |
| `DATABASE_URL`, `ASYNC_DATABASE_URL` | The production database, with TLS if applicable |

`NEXT_PUBLIC_*` values are inlined during `npm run build`. Changing one requires
a rebuild, not a restart.

## Database migrations

```bash
docker compose run --rm backend alembic -c /app/database/alembic.ini upgrade head
```

Run migrations as a separate step before the new application version starts.
Alembic reads the URL from settings, so the same environment drives the app and
the migration.

## Health and readiness

| Endpoint | Use |
| --- | --- |
| `/api/v1/health` | Liveness. 200 while the process is up |
| `/api/v1/health/ready` | Readiness. 503 when the database is down or no model is loaded |

Both container healthchecks use the endpoints above. `/health/ready` is the one
to gate traffic on, because an instance with no model loaded will return 503 on
every forecast request.

## Model deployment

1. Train: `python scripts/run_training.py` → a new `ml/artifacts/vNNN/`.
2. Register: the run writes a `model_versions` row with status `candidate`.
3. Verify: the candidate needs scored forecasts before it can be judged.
4. Promote: `POST /api/v1/models/promote`.
5. Converge replicas: `POST /api/v1/models/reload` on each instance, or restart
   them, or set `MODEL_VERSION` so they load the right version on boot.

Step 5 is the one manual step. The model cache is per-process by design, so
correctness is preserved by restarting rather than by invalidating caches on
every request.

To pin a version regardless of the database flag:

```bash
MODEL_VERSION=v002
```

That is what an evaluation or canary deployment does.

## Rollback

```bash
curl -X POST localhost:8000/api/v1/models/promote \
  -H 'Content-Type: application/json' \
  -d '{"target_version": "v001", "policy": "force"}'
```

The `force` policy activates an archived version. Artifacts are never deleted, so
rollback is always possible as long as the directory exists. If it does not, the
version can be retrained from the same dataset and seed.

## Scheduled jobs

`scripts/run_jobs.sh` is idempotent and safe to run on a timer.

```cron
17 * * * *  cd /srv/rain-corrector && ./scripts/run_jobs.sh forecast
43 3 * * 0  cd /srv/rain-corrector && ./scripts/run_jobs.sh retrain
```

The `retrain` job registers a candidate and does not promote. Promotion stays a
deliberate act, so an automated schedule cannot quietly change what the API
serves. `RETRAINING_MIN_INTERVAL_HOURS` guards against retraining on every tick.

## Scaling

Ordered by when they become a problem:

1. **Forecast generation** is O(districts) in one batched `predict`. Hundreds is
   fine; tens of thousands need chunking.
2. **Verification** issues per-forecast queries. Thousands per run is fine;
   beyond that, batch the aggregate lookup and score in memory.
3. **The dashboard aggregate** is the heaviest read. It is already one payload;
   beyond a few thousand forecasts, precompute per-district daily rollups.
4. **The model cache is per replica.** Promotion needs a restart, a reload, or
   `MODEL_VERSION`. This is deliberate: correctness over cache invalidation.

Horizontal scaling of the API is otherwise straightforward. It is stateless apart
from the model cache, so add replicas behind a load balancer and make sure each
is reloaded after a promotion.

## What is deliberately not automated

- **Promotion.** A schedule registers candidates; a human or a policy
  evaluation activates them.
- **Artifact deletion.** Old versions are kept, because rollback depends on them.
- **Migrations on startup.** They are a separate step so a deploy failure is
  attributable.

## Production checklist

- [ ] `SECRET_KEY` regenerated and stored in a secret manager
- [ ] `ENABLE_API_KEY_AUTH=true`, keys distributed out of band
- [ ] Database credentials rotated; TLS enabled if the database is remote
- [ ] `CORS_ORIGINS` set to the real frontend origin
- [ ] `NEXT_PUBLIC_MAP_TILE_URL` points at a provider that permits the traffic
- [ ] `NEXT_PUBLIC_MAP_ATTRIBUTION` matches that provider
- [ ] Migrations run as an explicit deploy step
- [ ] A model is trained, registered and promoted; `/health/ready` returns 200
- [ ] Backups configured for PostgreSQL, with a restore rehearsed
- [ ] Log shipping configured, and `LOG_FORMAT=json` in production
- [ ] Alerting on `/health/ready` failures and on verification batches that
      verify nothing for several days

## Observability

Structured logs (`LOG_FORMAT=json` in production) cover startup, model loads,
forecast generation, ingestion, verification batches, training runs and API
errors. Every line within a request carries `request_id`, which is also returned
in error bodies and in the `X-Request-ID` response header.

Two signals deserve alerting:

- `/health/ready` returning 503 for more than a few minutes
- A verification batch reporting `forecasts_verified: 0` across several
  consecutive runs, which usually means ingestion has stopped rather than that
  the model is wrong
