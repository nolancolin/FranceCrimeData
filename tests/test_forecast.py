import numpy as np
import pandas as pd
import pytest

from delinquance.forecast import (
    baselines,
    build_panel,
    features_for_year,
    predict_year,
    training_set,
)
from delinquance.scrub import independent_indicators


@pytest.fixture(scope="module")
def panel(cleaned):
    return build_panel(cleaned[cleaned["indicator"].isin(independent_indicators(cleaned))])


def scramble_from(panel: pd.DataFrame, year: int) -> pd.DataFrame:
    """Replace every value from `year` on with noise."""
    future = panel.copy()
    cols = [c for c in future.columns if c >= year]
    future[cols] = np.random.default_rng(1).normal(size=(len(future), len(cols)))
    return future


def test_features_ignore_target_and_future_years(panel):
    scrambled = scramble_from(panel, 2023)
    pd.testing.assert_frame_equal(
        features_for_year(panel, 2023), features_for_year(scrambled, 2023)
    )


def test_training_targets_stop_before_test_year(panel):
    x, y = training_set(panel, 2022)
    x2, y2 = training_set(scramble_from(panel, 2023), 2022)
    pd.testing.assert_series_equal(y, y2)
    assert len(y) == len(panel) * (2022 - 2019 + 1)


def test_prediction_does_not_leak(panel):
    original = predict_year(panel, 2023)
    scrambled = predict_year(scramble_from(panel, 2023), 2023)
    for col in ["naive", "trend", "gbm"]:
        assert np.allclose(original[col], scrambled[col])


def test_prediction_is_reproducible(panel):
    first, second = predict_year(panel, 2024), predict_year(panel, 2024)
    assert np.array_equal(first["gbm"], second["gbm"])


def test_baselines_on_a_straight_line():
    f = pd.DataFrame({"lag1": [3.0], "lag2": [2.0], "lag3": [1.0]})
    out = baselines(f)
    assert out.loc[0, "naive"] == 3.0
    assert out.loc[0, "trend"] == 4.0
