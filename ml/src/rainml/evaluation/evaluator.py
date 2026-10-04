"""Model comparison and selection.

Selection is deterministic: candidates are ranked by MAE on the validation
split, ties broken by name, and a candidate is only accepted if it beats the
best baseline on the test split. Both gates are recorded in the run metadata so
the decision is auditable after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from rainml.evaluation.metrics import DEFAULT_EVENT_THRESHOLD_MM, evaluate, skill_score


@dataclass
class ComparisonResult:
    baselines: dict[str, dict] = field(default_factory=dict)
    candidates: dict[str, dict] = field(default_factory=dict)
    best_baseline: str | None = None
    best_candidate: str | None = None
    test_scores: dict[str, dict] = field(default_factory=dict)
    skill_vs_baseline: dict[str, float | None] = field(default_factory=dict)
    beats_baseline: bool = False

    def to_dict(self) -> dict:
        return {
            "baselines": self.baselines,
            "candidates": self.candidates,
            "best_baseline": self.best_baseline,
            "best_candidate": self.best_candidate,
            "test_scores": self.test_scores,
            "skill_vs_best_baseline": self.skill_vs_baseline,
            "beats_baseline": self.beats_baseline,
        }


def rank(scores: dict[str, dict], metric: str = "mae_mm") -> str | None:
    """Best (lowest) MAE, ties resolved alphabetically for reproducibility."""
    usable = {name: s for name, s in scores.items() if s.get(metric) is not None}
    if not usable:
        return None
    return sorted(usable, key=lambda name: (usable[name][metric], name))[0]


def compare(
    validation_scores: dict[str, dict],
    test_scores: dict[str, dict],
    baseline_names: set[str],
    threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM,
    max_test_samples: int = 20000,
) -> ComparisonResult:
    baselines = {k: v for k, v in validation_scores.items() if k in baseline_names}
    candidates = {k: v for k, v in validation_scores.items() if k not in baseline_names}

    best_baseline = rank(baselines)
    best_candidate = rank(candidates)

    result = ComparisonResult(
        baselines=baselines,
        candidates=candidates,
        best_baseline=best_baseline,
        best_candidate=best_candidate,
    )

    for name in (best_baseline, best_candidate):
        if name and name in test_scores:
            result.test_scores[name] = test_scores[name]

    if best_baseline and best_candidate:
        baseline_mae = test_scores.get(best_baseline, {}).get("mae_mm")
        candidate_mae = test_scores.get(best_candidate, {}).get("mae_mm")
        if baseline_mae is not None and candidate_mae is not None:
            result.skill_vs_baseline[best_candidate] = skill_score(candidate_mae, baseline_mae)
            result.beats_baseline = candidate_mae < baseline_mae
    return result


def score_predictions(
    predictions: np.ndarray,
    targets: np.ndarray,
    threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM,
    cap: int | None = 20000,
) -> dict:
    """Score with an optional cap for speed on very large test partitions."""
    predictions = np.asarray(predictions, dtype=float)
    targets = np.asarray(targets, dtype=float)
    if cap is not None and predictions.size > cap:
        step = max(predictions.size // cap, 1)
        predictions = predictions[::step]
        targets = targets[::step]
    return evaluate(predictions, targets, threshold_mm)


def predictions_frame(
    frame: pd.DataFrame,
    predictions: np.ndarray,
    forecast_column: str = "prediction",
) -> pd.DataFrame:
    result = frame.copy()
    result[forecast_column] = np.asarray(predictions, dtype=float)
    return result
