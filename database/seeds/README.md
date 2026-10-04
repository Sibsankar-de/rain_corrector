# Database seeds

Seed data is produced by `scripts/seed_data.py` rather than stored as SQL here,
because it is derived from the demo dataset and a trained artifact. The script is
idempotent, so it is safe to re-run.

```bash
backend/.venv/bin/python scripts/seed_data.py
backend/.venv/bin/python scripts/seed_data.py --reset   # truncate first
```

What it writes:

| Table | Contents |
| --- | --- |
| `regions`, `districts`, `stations` | Geography from `data/processed/districts.csv`, three gauges per district |
| `observations` | The daily series split across gauges, with per-gauge multiplicative error |
| `district_aggregates` | Daily district totals, the junction for training and verification |
| `users` | The `system` service account |
| `model_versions` | The newest on-disk artifact, activated |
| `forecast_runs`, `forecasts`, `forecast_values` | A backfill of daily runs |
| `alerts` | Derived from forecast severity |
| `verification_results`, `verification_batches` | Scores for every matured backfilled forecast |

Every measurement row carries `origin = 'synthetic'`, so demo data is never
mistaken for observed data.

## Raw SQL

Prefer Alembic migrations for anything schema-related. Use this directory for
seed data that is genuinely fixed and small. A `seed.sql` should be idempotent
(`ON CONFLICT DO NOTHING`) and must never truncate a table.
