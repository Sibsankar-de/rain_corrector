"""Training configuration.

Configuration is a plain dataclass loaded from YAML so a training run is fully
described by (dataset, config, seed). Nothing is read from a notebook's
namespace.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "training.yaml"


@dataclass
class TrainingConfig:
    model_name: str = "district_daily_rainfall"
    target_column: str = "target_rainfall_mm"
    horizon_days: int = 1
    random_seed: int = 42
    event_threshold_mm: float = 15.0
    max_features: int = 14
    valid_fraction: float = 0.2
    test_fraction: float = 0.2
    candidate_names: list[str] = field(
        default_factory=lambda: [
            "ridge",
            "hist_gradient_boosting",
            "random_forest",
            "gradient_boosting",
        ]
    )
    quantile_alphas: tuple[float, float] = (0.1, 0.9)
    fit_interval_models: bool = True
    register_in_database: bool = True
    promote: bool = False
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = {k: v for k, v in self.to_dict().items() if k != "notes"}
        return json.dumps(payload, sort_keys=True, default=str)


def load_config(path: str | Path | None = None) -> TrainingConfig:
    source = Path(path) if path else DEFAULT_CONFIG_PATH
    if not source.exists():
        return TrainingConfig()
    if source.suffix.lower() in (".yaml", ".yml"):
        import yaml

        raw = yaml.safe_load(source.read_text()) or {}
    else:
        raw = json.loads(source.read_text())

    known = {f.name for f in fields(TrainingConfig)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Unknown configuration keys in {source}: {sorted(unknown)}")
    if "quantile_alphas" in raw:
        raw["quantile_alphas"] = tuple(raw["quantile_alphas"])
    return TrainingConfig(**raw)


def set_global_seed(seed: int) -> None:
    import numpy as np

    random.seed(seed)
    np.random.seed(seed)
    try:
        import sklearn

        sklearn.set_seed(seed)
    except (ImportError, AttributeError):
        pass
