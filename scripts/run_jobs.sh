#!/usr/bin/env bash
# Scheduled jobs. Each job is idempotent and safe to run on a timer or by hand.
#
#   ./scripts/run_jobs.sh forecast     # issue a forecast run for every district
#   ./scripts/run_jobs.sh verify       # score matured forecasts
#   ./scripts/run_jobs.sh retrain      # train a candidate and register it
#   ./scripts/run_jobs.sh all
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-backend/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo "backend virtualenv missing; run scripts/setup.sh first" >&2
  exit 1
fi

run_forecast() {
  echo "==> generating a forecast run"
  "$PYTHON" - <<'PY'
import asyncio
import sys

sys.path.insert(0, "backend")
sys.path.insert(0, "ml/src")

from app.core.database import async_session_factory
from app.ml.predictor import ForecastGenerator
from app.ml.registry import model_registry
from app.repositories.model_repository import ModelRepository
from app.services.alert_service import AlertService
from app.services.dashboard_service import DashboardService
from app.services.verification_service import VerificationService
from sqlalchemy import select
from app.models import Forecast, ForecastRun


async def main() -> None:
    async with async_session_factory() as session:
        active = await ModelRepository(session).get_active()
        if active is None:
            print("no active model; run scripts/run_training.py first", file=sys.stderr)
            raise SystemExit(1)

        artifact = model_registry.set_active(active.version)
        generator = ForecastGenerator(session)
        run, predictions, _ = await generator.generate(
            artifact=artifact, horizon_hours=24, step_hours=24
        )
        await session.commit()

        stored = (
            (
                await session.execute(
                    select(Forecast).where(Forecast.run_id == run.id)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        created = await AlertService(session).evaluate_forecasts(list(stored))

        batch = await VerificationService(session).run_verification(
            model_version=active.version, lookback_days=30, triggered_by="scheduled_job"
        )
        await session.commit()

        print(f"run {run.run_uid}: {len(predictions)} forecasts, {created} alerts")
        print(f"verification {batch.batch_uid}: {batch.forecasts_verified} scored")


asyncio.run(main())
PY
}

run_retrain() {
  echo "==> training a candidate model"
  ml/.venv/bin/python scripts/run_training.py
  echo "candidate registered; promote it deliberately:"
  echo "  curl -X POST localhost:8000/api/v1/models/promote -H 'Content-Type: application/json' \\"
  echo "       -d '{\"target_version\": \"vNNN\"}'"
}

case "${1:-all}" in
  forecast) run_forecast ;;
  verify) run_forecast ;;   # verification is part of the same cycle
  retrain) run_retrain ;;
  all) run_forecast; run_retrain ;;
  *) echo "usage: $0 {forecast|verify|retrain|all}" >&2; exit 2 ;;
esac
