"""Model artifact loading, interval clamping and version handling."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import ModelUnavailableError
from app.ml.base import ModelArtifact
from app.ml.registry import ModelRegistry


def _frame(columns: list[str], rows: int = 3) -> pd.DataFrame:
    return pd.DataFrame([{column: float(i + 1) for column in columns} for i in range(rows)])


class ConstantRegressor:
    """Stand-in for a fitted sklearn pipeline."""

    def __init__(self, value: float = 5.0) -> None:
        self.value = value

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.full(len(frame), self.value)


def _artifact(lower: object = None, upper: object = None) -> ModelArtifact:
    return ModelArtifact(
        model_name="test",
        version="v001",
        pipeline=ConstantRegressor(),
        metadata={"version": "v001"},
        feature_columns=["a", "b"],
        lower_pipeline=lower,
        upper_pipeline=upper,
    )


class TestModelArtifact:
    def test_point_prediction(self) -> None:
        artifact = _artifact()
        assert artifact.predict(_frame(["a", "b"])).tolist() == [5.0, 5.0, 5.0]

    def test_missing_features_fail_loudly(self) -> None:
        # Silently predicting on a partial frame would corrupt forecasts instead
        # of surfacing a contract violation.
        with pytest.raises(Exception, match="missing"):
            _artifact().predict(_frame(["a"]))

    def test_intervals_fall_back_to_the_point_forecast(self) -> None:
        artifact = _artifact()
        point, lower, upper = artifact.predict_interval(_frame(["a", "b"]))
        assert lower.tolist() == point.tolist()
        assert upper.tolist() == point.tolist()
        assert artifact.supports_intervals is False

    def test_crossed_interval_is_collapsed_onto_the_point_forecast(self) -> None:
        # Independent quantile fits can cross; the served band must not.
        artifact = _artifact(lower=ConstantRegressor(9.0), upper=ConstantRegressor(1.0))
        point, lower, upper = artifact.predict_interval(_frame(["a", "b"]))
        assert lower.tolist() == point.tolist()
        assert upper.tolist() == point.tolist()

    def test_interval_lower_above_the_point_is_clamped_down(self) -> None:
        artifact = _artifact(lower=ConstantRegressor(9.0), upper=ConstantRegressor(12.0))
        point, lower, upper = artifact.predict_interval(_frame(["a", "b"]))
        assert lower.tolist() == [5.0, 5.0, 5.0]
        assert upper.tolist() == [12.0, 12.0, 12.0]
        assert np.all(lower <= point) and np.all(point <= upper)

    def test_interval_upper_below_the_point_is_clamped_up(self) -> None:
        artifact = _artifact(lower=ConstantRegressor(1.0), upper=ConstantRegressor(2.0))
        point, lower, upper = artifact.predict_interval(_frame(["a", "b"]))
        assert lower.tolist() == [1.0, 1.0, 1.0]
        assert upper.tolist() == [5.0, 5.0, 5.0]
        assert np.all(lower <= point) and np.all(point <= upper)

    def test_wide_interval_is_preserved(self) -> None:
        artifact = _artifact(lower=ConstantRegressor(1.0), upper=ConstantRegressor(9.0))
        _, lower, upper = artifact.predict_interval(_frame(["a", "b"]))
        assert lower.tolist() == [1.0, 1.0, 1.0]
        assert upper.tolist() == [9.0, 9.0, 9.0]


class TestModelRegistry:
    def test_lists_versions_with_metadata(self, artifact_root: Path) -> None:
        registry = ModelRegistry(artifact_root)
        versions = registry.available_versions()
        assert versions
        for version in versions:
            assert (artifact_root / version / "metadata.json").exists()

    def test_loads_a_trained_artifact(self, trained_artifact: Path) -> None:
        registry = ModelRegistry(trained_artifact.parent)
        artifact = registry.load_version(trained_artifact.name)

        assert artifact.version == trained_artifact.name
        assert artifact.feature_columns
        assert artifact.pipeline is not None
        assert artifact.loaded_at is not None

    def test_missing_version_raises_a_typed_error(self, artifact_root: Path) -> None:
        registry = ModelRegistry(artifact_root)
        with pytest.raises(ModelUnavailableError):
            registry.load_version("v999")

    def test_get_active_raises_before_anything_is_loaded(self, artifact_root: Path) -> None:
        registry = ModelRegistry(artifact_root)
        with pytest.raises(ModelUnavailableError):
            registry.get_active()

    def test_set_active_populates_the_cache(self, trained_artifact: Path) -> None:
        registry = ModelRegistry(trained_artifact.parent)
        registry.set_active(trained_artifact.name)
        assert registry.active_version == trained_artifact.name
        assert registry.get_active().version == trained_artifact.name

    def test_reload_if_needed_skips_a_redundant_load(self, trained_artifact: Path) -> None:
        registry = ModelRegistry(trained_artifact.parent)
        first = registry.set_active(trained_artifact.name)
        second = registry.reload_if_needed(trained_artifact.name)
        assert first is second

    def test_reload_if_needed_swaps_a_different_version(self, artifact_root: Path) -> None:
        versions = sorted(p.name for p in artifact_root.iterdir() if (p / "metadata.json").exists())
        if len(versions) < 2:
            pytest.skip("needs at least two artifact versions to test a swap")

        registry = ModelRegistry(artifact_root)
        registry.set_active(versions[0])
        registry.reload_if_needed(versions[1])
        assert registry.active_version == versions[1]

    def test_set_active_none_clears_the_cache(self, trained_artifact: Path) -> None:
        registry = ModelRegistry(trained_artifact.parent)
        registry.set_active(trained_artifact.name)
        registry.set_active(None)
        assert registry.active_version is None

    def test_nonexistent_root_reports_no_versions(self, tmp_path: Path) -> None:
        assert ModelRegistry(tmp_path / "absent").available_versions() == []


def test_artifact_checksum_matches_the_model_file(trained_artifact: Path) -> None:
    import hashlib

    checksum_file = trained_artifact / "checksum.txt"
    if not checksum_file.exists():
        pytest.skip("artifact predates checksum support")

    expected = checksum_file.read_text().split()[0]
    actual = hashlib.sha256((trained_artifact / "model.joblib").read_bytes()).hexdigest()
    assert actual == expected
