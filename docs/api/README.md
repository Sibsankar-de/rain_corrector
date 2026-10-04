# API reference

Base URL: `http://localhost:8000`
Version prefix: `/api/v1`
Interactive docs: <http://localhost:8000/docs> · ReDoc: `/redoc` · Schema: `/openapi.json`

The authoritative contract is the generated OpenAPI document. This file
explains the conventions and the intent behind each group.

## Conventions

**Timestamps** are ISO 8601 with an explicit UTC offset.

**Pagination.** Collections accept `page` (≥1, default 1) and `page_size`
(1–200, default 20) and return:

```json
{
  "items": [],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 0,
    "total_pages": 0,
    "has_next": false,
    "has_previous": false
  }
}
```

A page past the end returns an empty `items` array, not an error.

**Errors.** Every non-2xx response has the same shape:

```json
{
  "error": {
    "code": "not_found",
    "message": "Forecast 999 does not exist.",
    "details": null
  },
  "request_id": "6f2a1c...",
  "timestamp": "2026-09-28T20:00:00Z"
}
```

| Code | Status | Meaning |
| --- | --- | --- |
| `validation_error` | 422 | Query or body failed validation; `details` lists the fields |
| `not_found` | 404 | Resource does not exist |
| `conflict` | 409 | Conflicts with current state, e.g. a refused promotion |
| `unauthorized` | 401 | Missing, invalid or expired API key |
| `model_unavailable` | 503 | No model loaded for inference |
| `provider_error` | 502 | Upstream data provider failed |
| `internal_error` | 500 | Unexpected; quote `request_id` |

`message` is safe to display. Stack traces and ORM messages are never returned.

**Headers.** Every response carries `X-Request-ID` and `X-Process-Time`. Send
`X-Request-ID` yourself to correlate a request across services.

**Authentication.** Off by default. With `ENABLE_API_KEY_AUTH=true`, send
`X-API-Key: <key>` (or `Authorization: Bearer <key>`) on data routes. Health and
documentation stay public.

---

## Health

### `GET /api/v1/health`

Liveness. Always 200 while the process is up.

### `GET /api/v1/health/ready`

Readiness. Returns 503 when the database is unreachable or no model is loaded,
so orchestration restarts the instance.

```json
{
  "status": "ready",
  "app": "Rain Corrector",
  "environment": "development",
  "version": "v1",
  "checked_at": "2026-09-28T20:00:00Z",
  "database": "ok",
  "model_loaded": true,
  "model_version": "v001",
  "available_model_versions": ["v001"]
}
```

---

## Locations

### `GET /api/v1/locations/regions`

All regions.

### `GET /api/v1/locations/districts`

Paginated districts.

| Parameter | Type | Notes |
| --- | --- | --- |
| `page`, `page_size` | int | Pagination |
| `region_id` | int | Filter by region |
| `search` | str | Case-insensitive name match, 2–64 chars |
| `min_lat`, `max_lat` | float | −90…90 |
| `min_lon`, `max_lon` | float | −180…180 |

The bounding-box parameters are a four-clause range predicate on the district
centroid. Combined bounds are ANDed; any subset is allowed.

### `GET /api/v1/locations/districts/{district_id}`

District detail including its region and active station count. 404 if unknown.

### `GET /api/v1/locations/stations`

Stations, optionally filtered by `district_id`, active only by default.

### `POST /api/v1/locations/stations`

Register a station. 201 on success.

```json
{
  "code": "MH-MUM-ST04",
  "name": "Mumbai Gauge 4",
  "district_id": 1,
  "latitude": 19.22,
  "longitude": 72.98,
  "elevation_m": 14
}
```

`code` must match `^[A-Za-z0-9_-]+$` and be unique. `name` must not be blank.

---

## Observations

### `POST /api/v1/observations/ingest`

Batch ingestion. Idempotent: a row matching an existing
`(station_id, observed_at, window_minutes)` is a duplicate and skipped.

```json
{
  "observations": [
    {
      "station_id": 1,
      "observed_at": "2026-09-28T00:00:00Z",
      "window_minutes": 1440,
      "rainfall_mm": 12.5,
      "temperature_c": 27.4,
      "relative_humidity": 82.0,
      "wind_speed_kmph": 9.1,
      "pressure_hpa": 1004.2,
      "origin": "observed",
      "source": "gauge-feed"
    }
  ],
  "recompute_aggregates": true
}
```

- Max 5000 observations per request.
- `rainfall_mm` must be 0–2000; `observed_at` cannot be in the future.
- Validation is all-or-nothing: a rejected request writes nothing.
- `recompute_aggregates` recomputes daily district aggregates for the affected
  districts.

```json
{ "accepted": 1, "duplicates": 0, "aggregates_updated": 1 }
```

### `GET /api/v1/observations/district/{district_id}`

Station observations for a district. `start` and `end` are required; `limit`
caps the response (default 1000, max 10000).

### `GET /api/v1/observations/aggregates`

Daily district aggregates. `district_id` required; optional `start`, `end`,
`limit`.

This is the endpoint the verification service and the model features read from.

---

## Forecasts

### `GET /api/v1/forecasts`

Paginated forecasts with the broadest filter set.

| Parameter | Type | Notes |
| --- | --- | --- |
| `page`, `page_size` | int | Pagination |
| `district_id` | int[] | Repeatable |
| `region_id` | int | |
| `model_version` | str | Exact version match |
| `min_rainfall_mm` | float | ≥0 |
| `severity` | str | `none`…`extreme` |
| `issued_from`, `issued_to` | datetime | When the run was issued |
| `target_from`, `target_to` | datetime | When the forecast applies |
| `min_lat`, `min_lon`, `max_lat`, `max_lon` | float | District centroid box |

```json
{
  "id": 2129,
  "run_id": 134,
  "district_id": 33,
  "target_time": "2026-09-28T00:00:00Z",
  "lead_time_hours": 24.0,
  "predicted_rainfall_mm": 2.1,
  "lower_bound_mm": 0.0,
  "upper_bound_mm": 13.2,
  "severity": "light",
  "status": "verified",
  "issued_at": "2026-09-27T00:00:00Z",
  "model_version": "v001",
  "district": { "id": 33, "code": "MH-MUM", "name": "Mumbai Suburban", "...": "..." }
}
```

### `GET /api/v1/forecasts/map`

The latest run, or a specific `run_uid`, optionally bounded and filtered by
`min_rainfall_mm`. Not paginated: it is bounded to one run, which is at most one
row per district. Designed for map markers.

### `GET /api/v1/forecasts/legend`

The severity scale, contiguous and ordered. The map reads this rather than
hard-coding colours, so the legend cannot drift from the alert rules.

```json
[
  { "label": "no_rain", "severity": "none", "color": "#e2e8f0", "min_mm": 0.0, "max_mm": 0.1 },
  { "label": "light", "severity": "light", "color": "#60a5fa", "min_mm": 0.1, "max_mm": 2.5 }
]
```

### `GET /api/v1/forecasts/runs`

Issuance history, paginated, with `forecast_count` per run.

### `GET /api/v1/forecasts/runs/{run_uid}`

One run. 404 if unknown.

### `GET /api/v1/forecasts/{forecast_id}`

Detail including the per-lead-time `values` rows and the stored
`feature_inputs`. Use this when the horizon is subdivided.

### `POST /api/v1/forecasts/generate`

Issue and persist a run with the active model, then derive alerts. 201 on
success.

```json
{
  "model_version": "v001",
  "issued_at": "2026-09-28T00:00:00Z",
  "horizon_hours": 24,
  "step_hours": 24,
  "district_ids": [1, 2, 3]
}
```

All fields optional; defaults are the active model, now, `DEFAULT_FORECAST_HORIZON_HOURS`
and every district. `issued_at` cannot be in the future (422 with code
`invalid_issue_time`).

Returns the `run_uid` and the count created.

---

## Verification

### `GET /api/v1/verification/results`

Scored forecasts, paginated. Filters: `model_version`, `district_id` (repeatable),
`status` (`verified`, `missing_observation`, `pending_observation`), `page`,
`page_size`.

```json
{
  "forecast_id": 2129,
  "status": "verified",
  "observed_rainfall_mm": 0.07,
  "forecast_rainfall_mm": 2.1,
  "error_mm": -2.03,
  "absolute_error_mm": 2.03,
  "bias_mm": 2.03,
  "nash_sutcliffe": null,
  "brier_score": 0.018,
  "hit": false,
  "false_alarm": false,
  "missed": false,
  "correct_negatives": true,
  "observed_at": "2026-09-27T00:00:00Z",
  "verified_at": "2026-09-28T02:00:00Z"
}
```

`nash_sutcliffe` is `null` for a single forecast, because a one-sample score is
undefined.

### `GET /api/v1/verification/metrics`

Aggregated skill over verified rows. Filters: `model_version`, `district_id`,
`start`, `end`.

Returns continuous scores, categorical scores, and `by_lead_bucket` and
`by_severity` breakdowns. A metric with an empty denominator is `null`, never
`0.0`.

### `GET /api/v1/verification/forecast/{forecast_id}`

The score for one forecast. 404 if the forecast is unknown **or** has not been
verified; check `/verification/results` to distinguish.

### `GET /api/v1/verification/batches`

Verification job history, most recent first. Each record shows
`candidates_considered`, `forecasts_verified`, `forecasts_pending` and a metrics
snapshot.

### `POST /api/v1/verification/run`

Score forecasts whose target period has passed the grace period.

```json
{ "model_version": "v001", "district_ids": [1], "lookback_days": 14, "force": false }
```

`force: true` re-scores forecasts that already have a result. Forecasts without a
matching observation are recorded as `missing_observation` and stay pending.

---

## Models

### `GET /api/v1/models/versions`

The registry. Filter by `status`
(`candidate`, `validated`, `active`, `archived`, `rejected`).

Each version carries `features`, `hyperparameters`, `metrics`, the training data
range and `trained_at`.

### `GET /api/v1/models/versions/{version}`

The model card, plus `artifact_path` and `training_run_id`.

### `GET /api/v1/models/active`

The version the database flags as active, or `null`.

### `GET /api/v1/models/training-runs`

Training history, most recent first, with baseline and candidate metrics.

### `GET /api/v1/models/policies`

Supported promotion policies.

### `POST /api/v1/models/promote`

Activate a version. Requires an API key when auth is enabled.

```json
{ "target_version": "v002", "policy": "auto_promote_if_better", "notes": "beat v001 on verified MAE" }
```

| Policy | Behaviour |
| --- | --- |
| `auto_promote_if_better` | Default. 409 unless lower verified MAE with at least as many scored forecasts |
| `manual_only` | Records the request; does not activate |
| `force` | Activates unconditionally, including an archived version |

The incumbent is archived in the same transaction. The process-local registry is
reloaded; `reloaded` in the response reports whether that succeeded.

### `POST /api/v1/models/reload`

Re-read the database-active version into the serving process. Use after a
promotion on a replica, or when a new artifact has been written.

---

## Alerts

### `GET /api/v1/alerts`

Paginated alerts. Filters: `status` (`open`, `acknowledged`, `resolved`),
`severity` (`info`, `warning`, `severe`, `critical`), `district_id`, `valid_at`
(only alerts whose window contains that instant).

Alerts are derived from forecast severity, not from observations. They are not
auto-resolved on expiry: an unacknowledged alert for a window that has passed is
still an outstanding operational item.

### `GET /api/v1/alerts/summary`

Open counts by severity: `{"warning": 3, "critical": 1}`.

### `GET /api/v1/alerts/{alert_id}`

Alert detail including `district_name`.

### `PATCH /api/v1/alerts/{alert_id}`

Acknowledge or resolve. Requires an API key when auth is enabled.

```json
{ "status": "acknowledged" }
```

---

## Dashboard

### `GET /api/v1/dashboard/overview`

One aggregate payload for the dashboard: `lookback_days` (1–90, default 7).

```json
{
  "generated_at": "2026-09-28T20:00:00Z",
  "active_model_version": "v001",
  "model_loaded_version": "v001",
  "latest_forecast_run": "fr_v001_20260928T0000Z",
  "latest_forecast_issued_at": "2026-09-28T00:00:00Z",
  "status": {
    "forecasts_issued": 976,
    "forecasts_verified": 480,
    "forecasts_pending": 0,
    "latest_observation": "2026-09-28T00:00:00Z",
    "evaluated_at": "2026-09-28T20:00:00Z"
  },
  "summary": { "forecasts_last_7d": 96, "districts_at_risk": 3, "open_alerts": 3, "observed_rainfall_mm_7d": 930.16 },
  "verification": { "sample_size": 480, "mae_mm": 5.7, "...": "..." },
  "severity_distribution": [],
  "top_risk_districts": [],
  "observed_rainfall_series": [],
  "forecast_vs_observed_series": [],
  "alerts": [],
  "legend": [],
  "models": []
}
```

It exists so every number on the dashboard comes from one consistent snapshot.
Without it the client would issue six requests and correlate them, and the
figures could disagree.

`status` reports pipeline state (how far forecasts have progressed through
verification); `summary` reports the current situation (districts at risk, open
alerts, observed totals). No figure appears in both.

`top_risk_districts` is the highest predicted rainfall in the latest run, not
filtered to heavy forecasts: on a dry day "nothing at risk" is the correct
answer, and an empty list is the honest report.
