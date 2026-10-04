"""Serving-side feature construction.

Feature engineering lives in `ml/src/rainml/features` and inference-time
assembly in `ml/src/rainml/inference/preprocessing.py`. This module is the thin
backend adapter: it converts the API's dataclass history into the shape
`rainml` expects and returns the model's feature frame.

The engineering logic is deliberately **not** reimplemented here. Two copies of
rolling-window arithmetic drift apart, and a drift that only shows up in
production is exactly the failure this design avoids. The shared
`FEATURE_COLUMNS` contract is asserted by the ML test suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

try:  # installed as an editable package in every environment
    from rainml.inference.preprocessing import (
        FEATURE_COLUMNS,
        build_feature_frame,
    )
    from rainml.inference.preprocessing import (
        DistrictHistory as RainmlDistrictHistory,
    )
except ModuleNotFoundError:  # running from a source checkout without install
    import sys
    from pathlib import Path

    _ML_SRC = Path(__file__).resolve().parents[3] / "ml" / "src"
    if _ML_SRC.exists() and str(_ML_SRC) not in sys.path:
        sys.path.insert(0, str(_ML_SRC))
    from rainml.inference.preprocessing import (  # type: ignore[no-redef]
        FEATURE_COLUMNS,
        build_feature_frame,
    )
    from rainml.inference.preprocessing import (
        DistrictHistory as RainmlDistrictHistory,
    )

__all__ = ["FEATURE_COLUMNS", "DistrictHistory", "build_features"]


@dataclass(frozen=True)
class DistrictHistory:
    """Rolling daily rainfall for one district, newest last."""

    district_id: int
    latitude: float
    longitude: float
    daily_rainfall: dict[datetime, float]


def build_features(
    rows: list[DistrictHistory],
    issue_time: datetime,
    horizon_hours: int = 24,
) -> pd.DataFrame:
    """Assemble the feature frame the persisted model expects.

    The model was trained at daily resolution, so the target day is always the
    day after the issue date. `horizon_hours` is accepted for call-site clarity
    and must be a whole number of days; longer horizons are not supported by
    this model and are rejected rather than silently approximated.
    """
    if horizon_hours % 24:
        raise ValueError(
            f"horizon_hours must be a whole number of days for this model, got {horizon_hours}"
        )
    histories = [
        RainmlDistrictHistory(
            district_id=row.district_id,
            latitude=row.latitude,
            longitude=row.longitude,
            daily_rainfall_mm={
                _as_day(key): float(value) for key, value in row.daily_rainfall.items()
            },
        )
        for row in rows
    ]
    return build_feature_frame(histories, _as_day(issue_time))


def _as_day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()
