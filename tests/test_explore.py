import numpy as np
import pandas as pd

from delinquance.explore import changes, department_spread, national_rates, spread_labels


def test_national_rate_uses_each_indicator_denominator(cleaned):
    national = national_rates(cleaned).set_index(["indicator", "year"])["rate"]
    rows = cleaned[(cleaned["indicator"] == "Cambriolages de logement") & (cleaned["year"] == 2025)]
    expected = rows["count"].sum() / rows["housing"].sum() * 1000
    assert np.isclose(national[("Cambriolages de logement", 2025)], expected)


def test_changes_and_spread_cover_every_indicator(cleaned):
    national = national_rates(cleaned)
    assert len(changes(national)) == cleaned["indicator"].nunique()
    spread = department_spread(cleaned, 2025)
    assert (spread["p90"] >= spread["p10"]).all()


def test_spread_labels_keeps_a_minimum_gap():
    out = spread_labels(pd.Series({"a": 80.0, "b": 81.0, "c": 120.0}), gap=7)
    assert out["b"] - out["a"] == 7
    assert out["c"] == 120.0
