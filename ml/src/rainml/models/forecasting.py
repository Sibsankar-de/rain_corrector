"""Candidate forecasting models and their persisted pipeline shape.

`build_pipeline` returns a single sklearn Pipeline of
`preprocessor -> feature_selector -> regressor`. The whole object is what gets
serialised, so inference reproduces training-time transformations exactly,
including quantile regressors used for the prediction interval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sklearn.base import RegressorMixin
from sklearn.ensemble import (
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import QuantileRegressor, Ridge
from sklearn.pipeline import Pipeline

from rainml.features.selection import build_feature_selector, build_preprocessor

QUANTILE_ALPHAS = (0.1, 0.9)


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    family: str
    params: dict[str, Any]
    rationale: str


CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec(
        name="ridge",
        family="linear",
        params={"alpha": 1.0, "random_state": 0},
        rationale=(
            "Linear baseline on rainfall features; strong with few districts "
            "and a short history."
        ),
    ),
    CandidateSpec(
        name="hist_gradient_boosting",
        family="boosting",
        params={
            "loss": "squared_error",
            "learning_rate": 0.06,
            "max_iter": 400,
            "max_depth": 4,
            "min_samples_leaf": 40,
            "l2_regularization": 1.0,
            "random_state": 0,
        },
        rationale="Tree boosting captures the threshold behaviour of monsoon onset and decay.",
    ),
    CandidateSpec(
        name="random_forest",
        family="ensemble",
        params={
            "n_estimators": 300,
            "max_depth": 12,
            "min_samples_leaf": 5,
            "n_jobs": -1,
            "random_state": 0,
        },
        rationale="Variance reduction on noisy rainfall targets without assuming linearity.",
    ),
    CandidateSpec(
        name="gradient_boosting",
        family="boosting",
        params={
            "loss": "huber",
            "n_estimators": 300,
            "learning_rate": 0.05,
            "max_depth": 3,
            "random_state": 0,
        },
        rationale="Huber loss limits the influence of extreme rainfall days during fitting.",
    ),
)


def make_regressor(spec: CandidateSpec) -> RegressorMixin:
    if spec.name == "ridge":
        return Ridge(**spec.params)
    if spec.name == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(**spec.params)
    if spec.name == "random_forest":
        return RandomForestRegressor(**spec.params)
    if spec.name == "gradient_boosting":
        return GradientBoostingRegressor(**spec.params)
    raise KeyError(f"No regressor registered for '{spec.name}'")


def build_pipeline(
    spec: CandidateSpec,
    features: list[str],
    max_features: int = 14,
    with_selector: bool = True,
) -> Pipeline:
    steps: list[tuple[str, Any]] = [("preprocessor", build_preprocessor(features))]
    if with_selector and len(features) > max_features:
        steps.append(("selector", build_feature_selector(features, max_features)))
    steps.append(("regressor", make_regressor(spec)))
    return Pipeline(steps)


def make_quantile_pipeline(spec: CandidateSpec, features: list[str], alpha: float) -> Pipeline:
    """Quantile variant used to derive the 10th/90th percentile forecast band."""
    pipeline = build_pipeline(spec, features, with_selector=False)
    pipeline.steps[-1] = (
        "regressor",
        QuantileRegressor(quantile=alpha, alpha=spec.params.get("alpha", 1.0), solver="highs"),
    )
    return pipeline
