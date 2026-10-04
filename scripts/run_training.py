"""Training run CLI.

Usage
-----
    python scripts/run_training.py
    python scripts/run_training.py --config ml/configs/training.yaml --promote
    python scripts/run_training.py --observations path/to/obs.csv --years 5

Loads the dataset, runs the reproducible pipeline, writes the versioned
artifact and (when the database is reachable) records a `training_runs` row plus
a `model_versions` row in `candidate` status.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ML_SRC = REPO_ROOT / "ml" / "src"
if str(ML_SRC) not in sys.path:
    sys.path.insert(0, str(ML_SRC))

from rainml.training.configuration import load_config  # noqa: E402
from rainml.training.trainer import run_training  # noqa: E402

DEFAULT_OBSERVATIONS = REPO_ROOT / "data" / "processed" / "observations.csv"
DEFAULT_DISTRICTS = REPO_ROOT / "data" / "processed" / "districts.csv"
DEFAULT_ARTIFACTS = REPO_ROOT / "ml" / "artifacts"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the rainfall forecasting model.")
    parser.add_argument("--observations", default=str(DEFAULT_OBSERVATIONS))
    parser.add_argument("--districts", default=str(DEFAULT_DISTRICTS))
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACTS))
    parser.add_argument("--config", default=None, help="Path to a training YAML/JSON config.")
    parser.add_argument("--version", default=None, help="Explicit version label. Defaults to the next vNNN.")
    parser.add_argument("--seed", type=int, default=None, help="Overrides the config random seed.")
    parser.add_argument(
        "--register",
        action="store_true",
        default=True,
        help="Record the run in the database (default).",
    )
    parser.add_argument("--no-register", dest="register", action="store_false")
    parser.add_argument(
        "--promote",
        action="store_true",
        default=False,
        help="Promote the new version to active if the promotion policy allows it.",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return parser.parse_args(argv)


def build_recorder(enabled: bool):
    if not enabled:
        return None

    backend = REPO_ROOT / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    try:
        from app.core.database import async_session_factory
        from app.repositories.model_repository import ModelRepository
    except ImportError as exc:
        print(f"[warn] database registration unavailable: {exc}", file=sys.stderr)
        return None

    import asyncio

    def recorder(**payload):
        run_id = payload.get("run_id")
        if not run_id:
            return

        async def _write():
            async with async_session_factory() as session:
                models = ModelRepository(session)
                existing = await models.get_training_run(run_id)
                if existing is None:
                    existing = await models.create_training_run(
                        {
                            "run_id": run_id,
                            "status": payload.get("status", "pending"),
                            "config": payload.get("config", {}),
                            "dataset_path": payload.get("dataset_path"),
                            "dataset_rows": payload.get("dataset_rows"),
                        }
                    )
                existing.status = payload.get("status", existing.status)
                existing.candidate_results = payload.get("candidate_results", existing.candidate_results or {})
                existing.best_model_name = payload.get("best_model_name") or existing.best_model_name
                existing.best_metrics = payload.get("best_metrics", existing.best_metrics or {})
                existing.baseline_metrics = payload.get("baseline_metrics", existing.baseline_metrics or {})
                existing.created_model_version = (
                    payload.get("created_model_version") or existing.created_model_version
                )
                if payload.get("error_message"):
                    existing.error_message = payload["error_message"]
                if payload.get("finished_at"):
                    existing.finished_at = payload["finished_at"]
                    if existing.started_at:
                        existing.duration_seconds = payload.get("duration_seconds")
                await session.commit()
                return existing.id

        try:
            return asyncio.run(_write())
        except Exception as exc:
            print(f"[warn] could not record training run: {exc}", file=sys.stderr)
            return None

    return recorder


def register_model_version(artifact_dir: Path, status: str = "candidate") -> None:
    from rainml.models.registry import load_metadata

    backend = REPO_ROOT / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    import asyncio

    from app.core.database import async_session_factory
    from app.repositories.model_repository import ModelRepository

    metadata = load_metadata(artifact_dir.parent, artifact_dir.name)

    async def _write():
        async with async_session_factory() as session:
            models = ModelRepository(session)
            existing = await models.get_by_version(metadata["version"])
            if existing is not None:
                print(f"[info] model version {metadata['version']} already registered")
                return
            await models.create_version(
                {
                    "model_name": metadata["model_name"],
                    "version": metadata["version"],
                    "status": status,
                    "artifact_path": str(artifact_dir),
                    "framework_version": metadata["framework_version"],
                    "hyperparameters": metadata.get("hyperparameters", {}),
                    "features": metadata.get("features", []),
                    "metrics": metadata.get("metrics", {}),
                    "notes": metadata.get("notes"),
                }
            )
            await session.commit()
            print(f"[info] registered model version {metadata['version']} as {status}")

    asyncio.run(_write())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    if args.seed is not None:
        config.random_seed = args.seed
    if args.promote:
        config.promote = True

    report = run_training(
        observations_path=args.observations,
        districts_path=args.districts,
        artifact_root=args.artifact_root,
        config=config,
        register_run=build_recorder(args.register),
        version=args.version,
        progress=lambda message: print(f"  {message}"),
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print()
        print(f"run_id           : {report.run_id}")
        print(f"status           : {report.status}")
        if report.error:
            print(f"error            : {report.error}")
        print(f"dataset rows     : {report.dataset_rows}")
        print(f"selected model   : {report.selected_model}")
        print(f"version          : {report.version}")
        print(f"artifact         : {report.artifact_path}")
        print(f"duration         : {report.duration_seconds}s")
        if report.metrics.get("test"):
            for name, scores in report.metrics["test"].items():
                print(f"  test {name:<22} MAE={scores['mae_mm']} RMSE={scores['rmse_mm']} CSI={scores.get('csi')}")

    if report.status != "succeeded" or not report.artifact_path:
        return 1

    if args.register:
        try:
            register_model_version(Path(report.artifact_path))
        except Exception as exc:
            print(f"[warn] model version registration skipped: {exc}", file=sys.stderr)

    if args.promote:
        promote(report.version)
    return 0


def promote(version: str | None) -> None:
    if not version:
        return
    backend = REPO_ROOT / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    import asyncio

    from app.core.database import async_session_factory
    from app.schemas.forecast import ModelPromotionRequest
    from app.services.model_service import ModelService

    async def _promote():
        async with async_session_factory() as session:
            result = await ModelService(session).promote(
                ModelPromotionRequest(target_version=version, policy="force")
            )
            print(f"[info] promoted {result.activated_version} (was {result.previous_version})")

    try:
        asyncio.run(_promote())
    except Exception as exc:
        print(f"[warn] promotion skipped: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
