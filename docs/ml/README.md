# Machine learning

How the model is built, trained, evaluated and served. The system design is in
[ARCHITECTURE.md](../ARCHITECTURE.md); this file is the operational reference.

## Library layout

```text
ml/src/rainml/
├── data/
│   ├── loaders.py          CSV/JSONL/Parquet/PostgreSQL, coordinate join
│   ├── cleaning.py         impossible values, duplicates, gap imputation
│   └── validation.py       gates and the chronological split
├── features/
│   ├── engineering.py      feature construction + leakage guards
│   └── selection.py        f_regression selection, preprocessor
├── models/
│   ├── baseline.py         persistence, rolling mean, climatology, global mean
│   ├── forecasting.py      candidate specs and pipeline construction
│   └── registry.py         artifact layout, versioning, checksums
├── training/
│   ├── configuration.py    TrainingConfig, YAML loading, seeding
│   └── trainer.py          the reproducible pipeline
├── evaluation/
│   ├── metrics.py          continuous and categorical scores
│   └── evaluator.py        comparison and selection
└── inference/
    ├── preprocessing.py    serving-time feature assembly
    └── predictor.py        artifact loading and typed predictions
```

`rainml` never imports `app`. The backend depends on `rainml`; notebooks call
`rainml`; nothing depends on the backend.

## Running a training run

```bash
ml/.venv/bin/python scripts/run_training.py
```

| Flag | Effect |
| --- | --- |
| `--observations`, `--districts` | Input paths (default: `data/processed/`) |
| `--artifact-root` | Where versions are written (default: `ml/artifacts`) |
| `--config` | YAML or JSON configuration |
| `--version` | Explicit version label (default: next `vNNN`) |
| `--seed` | Override `random_seed` |
| `--no-register` | Skip the database records |
| `--promote` | Promote after registering, using the `force` policy |
| `--json` | Emit the full report as JSON |

A run prints its progress and returns a `TrainingReport`:

```text
run_id           : run_20260928T190151_d31bbc
status           : succeeded
dataset rows     : 17520
selected model   : gradient_boosting
version          : v001
artifact         : .../ml/artifacts/v001
duration         : 15.3s
  test global_mean            MAE=5.2069 RMSE=8.2429 CSI=0.0
  test persistence            MAE=4.8634 RMSE=9.5601 CSI=0.0
  test rolling_mean_7d        MAE=5.4396 RMSE=8.6807 CSI=0.000856
  test seasonal_climatology   MAE=5.32   RMSE=8.2107 CSI=0.0
  test ridge                  MAE=5.3366 RMSE=8.1522 CSI=0.0
  test hist_gradient_boosting MAE=5.3355 RMSE=8.1756 CSI=0.0
  test random_forest          MAE=5.4977 RMSE=8.2604 CSI=0.000285
  test gradient_boosting      MAE=4.7816 RMSE=8.2766 CSI=0.0
```

**These numbers describe a synthetic dataset.** They are a working demonstration
of the pipeline, not real forecast skill.

## Configuration

`ml/configs/training.yaml`:

```yaml
model_name: district_daily_rainfall
target_column: target_rainfall_mm
horizon_days: 1
random_seed: 42          # same dataset + config + seed => same artifact
event_threshold_mm: 15.0 # heavy-event definition
max_features: 14
valid_fraction: 0.2
test_fraction: 0.2
candidate_names: [ridge, hist_gradient_boosting, random_forest, gradient_boosting]
quantile_alphas: [0.1, 0.9]
fit_interval_models: true
register_in_database: true
promote: false           # a candidate never replaces the active model
```

Unknown keys are rejected rather than ignored, so a typo fails the run instead
of silently changing behaviour.

## Pipeline stages

| Stage | Module | What it guarantees |
| --- | --- | --- |
| Load | `data.loaders` | Required columns present; districts resolve to coordinates |
| Validate | `data.validation` | Row, district and day minimums; no negatives, no impossible maxima |
| Clean | `data.cleaning` | Impossible values dropped, real extremes kept and flagged, gaps imputed as 0 mm |
| Engineer | `features.engineering` | Windows use `shift(1)`; the issue day is never an input |
| Leak check | `features.engineering.assert_no_leakage` | The antecedent term is not mirroring the target |
| Split | `data.validation.chronological_split` | Partitions are disjoint in time, cut on date boundaries |
| Baselines | `models.baseline` | Four references the candidate must beat |
| Candidates | `models.forecasting` | Four models, each with a documented rationale |
| Select | `evaluation.evaluator` | Lowest validation MAE, ties broken by name |
| Test | `evaluation.evaluator` | Rescored on the slice nothing was selected on |
| Interval | `models.forecasting.make_quantile_pipeline` | 10th/90th percentile models for the served band |
| Persist | `models.registry.save_artifact` | Immutable directory, checksum, model card |
| Record | `training.trainer` | `training_runs` and `model_versions` rows |

A failed stage returns `status="failed"` with `error` set rather than raising, so
the caller can record the failure.

## Model card

`ml/artifacts/<version>/metadata.json`:

```json
{
  "model_name": "district_daily_rainfall",
  "version": "v001",
  "trained_at": "2026-09-28T19:02:39Z",
  "training_data_start": "2023-09-29T00:00:00",
  "training_data_end": "2026-09-27T00:00:00",
  "training_data_range": "2023-09-29 .. 2026-09-27",
  "features": ["doy_cos", "regional_mean_rain_7d_mm", "..."],
  "target_column": "target_rainfall_mm",
  "hyperparameters": { "loss": "huber", "n_estimators": 300, "...": "..." },
  "metrics": { "validation": {}, "test": {}, "beats_baseline": true },
  "framework": "scikit-learn",
  "framework_version": "scikit-learn==1.6.0",
  "dataset_path": "data/processed/observations.csv",
  "dataset_rows": 17520,
  "event_threshold_mm": 15.0,
  "selected_model": "gradient_boosting",
  "status": "candidate"
}
```

`metrics.json` holds the full split metrics for every baseline and candidate, so
a selection decision can be re-examined without re-running anything.

## Serving

```python
from rainml.inference.predictor import RainfallPredictor
from rainml.inference.preprocessing import DistrictHistory
from datetime import date

predictor = RainfallPredictor.from_artifact_root("ml/artifacts", "v001")

histories = [
    DistrictHistory(
        district_id=1,
        latitude=19.2183,
        longitude=72.9781,
        daily_rainfall_mm={date(2026, 9, 27): 4.2, date(2026, 9, 26): 12.0},
    )
]

for prediction in predictor.predict_districts(histories, issue_date=date(2026, 9, 28)):
    print(prediction.as_dict())
```

The predictor verifies the artifact checksum before loading, validates that the
input frame carries every expected feature, and clips predictions at zero. Bounds
are clamped so `lower ≤ point ≤ upper` always holds, even when independent
quantile fits cross.

## Leakage prevention

The single most important property of this codebase. Daily rainfall is strongly
autocorrelated, so a pipeline that leaks looks excellent and generalises badly.

Three layers:

1. **Construction.** Rolling windows are computed on `shift(1)` series, so the
   issue day is never an input. The day-of-year term uses the *target* date,
   which is known when the forecast is issued, and using the target date is what
   keeps training and serving identical.
2. **Assertion.** `assert_no_leakage(frame)` fails the run when the antecedent
   feature starts mirroring the target. `validate_split(train, valid, test)` fails
   when partitions overlap in time.
3. **Parity test.** `ml/tests/test_features.py` builds the same feature vector
   through the training path and the serving path and compares every column.

That third layer earned its place during development. It caught the seasonal
term being computed from the issue date instead of the target date, and a
standard deviation computed with `ddof=0` against pandas' rolling `ddof=1`. Both
would have been invisible in a score.

A worked demonstration is in `ml/tests/test_data.py`:

```python
def test_persistence_skill_depends_on_the_split(self, demo_observations_path):
    ...
    # The random split looks better precisely because it leaks.
    assert leaky < honest
```

## Metric definitions

**Continuous** (millimetres)

| Metric | Formula | Notes |
| --- | --- | --- |
| MAE | `mean(observed − forecast)` | |
| RMSE | `sqrt(mean((observed − forecast)²))` | |
| Bias | `mean(forecast − observed)` | Positive means over-forecasting |
| NSE | `1 − SS_res / SS_tot` | `null` when the observations have no variance |

**Categorical** at the 15 mm event threshold

| Metric | Formula | Notes |
| --- | --- | --- |
| POD | `hits / (hits + misses)` | `null` when no events occurred |
| FAR | `false_alarms / (hits + false_alarms)` | `null` when nothing was forecast |
| CSI | `hits / total` | |
| Brier | `mean((clip(forecast/15, 0, 1) − event)²)` | |

An undefined ratio is `None`, not `0.0`. Reporting zero for an empty denominator
is a claim about skill the sample cannot support.

Both families are computed because rainfall is intermittent: continuous scores
are dominated by dry days, so the event scores carry the information an alert
consumer actually needs.

## Verification methodology

```text
forecast issued at T, targeting T + 24h
        ↓
wait until the target period has elapsed plus VERIFICATION_GRACE_PERIOD_HOURS
        ↓
find the district aggregate whose window contains the target time
        ↓
none  → status = missing_observation (stays pending, never scored as zero)
mismatch → _assert_no_leakage raises; the run fails
match  → score and store, with issued_at, observed_at and verified_at
```

The grace period exists because an accumulation window is still open immediately
after it ends. The window-membership check exists because an aggregate for the
wrong day would produce a plausible score for the wrong period.

## Replacing the demo dataset

The bundled data is synthetic. To use a real source:

1. Produce a CSV with `district_id, observed_at, rainfall_mm, lat, lon`, where
   `district_id` is either the numeric id from your district table or the district
   code.
2. Produce `districts.csv` with `id, code, name, region, centroid_lat,
   centroid_lon, population`.
3. Point `ML_TRAINING_DATA_PATH` at the directory and re-run
   `scripts/run_training.py`.
4. Ingest into the API with `POST /api/v1/observations/ingest`, then run
   verification.

No code changes. The loaders, the feature pipeline and the training config all
read the same schema.

## Tests

```bash
cd ml && .venv/bin/python -m pytest tests/ -q
```

| File | Covers |
| --- | --- |
| `test_data.py` | Loading, cleaning, validation, the split, and the leakage justification |
| `test_features.py` | Feature construction, the leakage guards, selection, training/serving parity |
| `test_models_and_training.py` | Baselines, candidates, the artifact registry, the full pipeline, reproducibility |
| `test_evaluation.py` | Metric definitions, ranking, comparison, selection |
| `test_inference.py` | Serving features, prediction, interval ordering, checksum verification |

Tests that need the dataset or a trained artifact skip cleanly when those are
absent, so the suite runs on a fresh checkout.
