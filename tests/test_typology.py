import numpy as np
import pandas as pd

from delinquance.typology import (
    build_profile,
    choose_clustering,
    cluster_labels,
    find_twins,
    relabel_by_size,
    stability,
    standardize,
)


def test_profile_averages_last_three_years(cleaned):
    profile = build_profile(cleaned)
    recent = cleaned[(cleaned["dep"] == "48") & (cleaned["year"] >= 2023)]
    expected = recent.loc[recent["indicator"] == "Homicides", "rate"].mean()
    assert np.isclose(profile.loc["48", "Homicides"], expected)
    assert profile.shape == (cleaned["dep"].nunique(), cleaned["indicator"].nunique())


def test_standardized_profile_is_centered(cleaned):
    z = standardize(build_profile(cleaned))
    assert np.allclose(z.mean(), 0)
    assert np.allclose(z.std(ddof=0), 1)


def test_clustering_is_reproducible(cleaned):
    z = standardize(build_profile(cleaned)).to_numpy()
    first = relabel_by_size(cluster_labels(z, "kmeans", 3))
    second = relabel_by_size(cluster_labels(z, "kmeans", 3))
    assert (first == second).all()
    assert stability(z, "kmeans", 2, n_boot=5) == stability(z, "kmeans", 2, n_boot=5)


def test_choice_prefers_stable_then_silhouette():
    table = pd.DataFrame(
        {
            "method": ["kmeans", "kmeans", "ward", "ward"],
            "k": [2, 3, 2, 4],
            "silhouette": [0.313, 0.309, 0.40, 0.20],
            "stability_ari": [0.95, 0.85, 0.50, 0.90],
        }
    )
    # ward k=2 has the best silhouette but is unstable, so it is skipped.
    assert choose_clustering(table) == ("kmeans", 2)


def test_twins_exclude_self(cleaned):
    twins = find_twins(standardize(build_profile(cleaned)), n=3)
    assert (twins["dep"] != twins["twin"]).all()
    assert twins.groupby("dep").size().eq(3).all()
    assert twins.groupby("dep")["distance"].apply(lambda d: d.is_monotonic_increasing).all()
