import numpy as np
import pandas as pd
import pytest

from delinquance.scrub import build_report, clean, load_raw


def test_no_row_lost(raw, cleaned):
    assert len(cleaned) == len(raw)
    assert (cleaned["dep"].to_numpy() == raw["dep"].to_numpy()).all()


def test_burglary_rate_is_per_thousand_dwellings(cleaned):
    denominators = cleaned.groupby("indicator")["denominator"].first()
    assert denominators["Cambriolages de logement"] == "housing"
    assert (denominators.drop("Cambriolages de logement") == "population").all()


def test_published_rates_match_their_denominator(cleaned):
    base = np.where(cleaned["denominator"] == "housing", cleaned["housing"], cleaned["population"])
    assert np.allclose(cleaned["rate"], cleaned["count"] / base * 1000, rtol=1e-4)
    assert not cleaned["flags"].str.contains("rate_mismatch").any()


def test_large_departments_are_kept_as_is(raw, cleaned):
    published = pd.to_numeric(raw.loc[raw["dep"] == "75", "population"])
    assert cleaned.loc[cleaned["dep"] == "75", "population"].max() == published.max()


def test_anomalies_are_flagged_not_removed(raw):
    broken = pd.concat([raw, raw.iloc[[0]]], ignore_index=True)
    broken.loc[len(broken) - 1, "count"] = "n/a"
    broken.loc[1, "dep"] = "999"
    out = clean(broken)
    assert len(out) == len(broken)
    assert "unparsable_number" in out["flags"].iloc[-1]
    assert "duplicate_key" in out["flags"].iloc[0]
    assert "bad_dep_code" in out["flags"].iloc[1]


def test_stale_population_flagged_for_mayotte_only(cleaned):
    flagged = cleaned[cleaned["flags"].str.contains("stale_population")]
    assert set(flagged["dep"]) == {"976"}


def test_report_counts(cleaned):
    report = build_report(cleaned)
    assert report["rows"] == len(cleaned)
    assert report["nested_mismatches"] == 0
    assert report["incomplete_series"] == []


def test_missing_column_raises(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text('"Code_departement";"annee"\n"01";"2020"\n')
    with pytest.raises(ValueError, match="missing columns"):
        load_raw(path)
