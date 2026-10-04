"""Feature selection and preprocessor construction.

The fitted `ColumnTransformer` is persisted next to the model so inference uses
the identical transformation; selecting features only at inference time would
silently change the model's input contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_selection import SelectKBest, f_regression
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from rainml.features.engineering import FEATURE_COLUMNS, TARGET_COLUMN

MAX_FEATURES = 14


@dataclass
class SelectionReport:
    selected: list[str]
    dropped: list[str]
    scores: dict[str, float] = field(default_factory=dict)
    constant: list[str] = field(default_factory=list)


def analyse_features(
    frame: pd.DataFrame,
    features: Sequence[str] = FEATURE_COLUMNS,
    target: str = TARGET_COLUMN,
    max_features: int = MAX_FEATURES,
) -> SelectionReport:
    x = frame[list(features)]
    y = frame[target].to_numpy(dtype=float)

    constant = [c for c in x.columns if float(np.nanstd(x[c].to_numpy(dtype=float))) == 0.0]
    usable = [c for c in x.columns if c not in constant]
    scores, selected, dropped = {}, [], []

    if usable:
        matrix = SimpleImputer(strategy="median").fit_transform(x[usable])
        f_values, _ = f_regression(matrix, y)
        f_values = np.nan_to_num(f_values, nan=0.0, posinf=0.0)
        scores = dict(zip(usable, (float(v) for v in f_values), strict=False))
        ordered = sorted(scores, key=lambda c: scores[c], reverse=True)
        selected = ordered[:max_features]
        dropped = [c for c in usable if c not in selected]

    return SelectionReport(selected=selected, dropped=dropped, scores=scores, constant=constant)


def build_preprocessor(features: Sequence[str]) -> ColumnTransformer:
    """Median imputation plus robust scaling.

    RobustScaler is used over StandardScaler because rainfall features are
    strongly right skewed and heavy outliers are physically real, not errors.
    """
    numeric = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", RobustScaler(quantile_range=(5.0, 95.0))),
        ]
    )
    return ColumnTransformer(
        transformers=[("numeric", numeric, list(features))],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def build_feature_selector(
    features: Sequence[str], max_features: int = MAX_FEATURES
) -> SelectKBest:
    return SelectKBest(score_func=f_regression, k=min(max_features, len(features)))
