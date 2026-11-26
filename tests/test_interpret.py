import pandas as pd

from delinquance.interpret import describe_clusters, top_loadings


def test_top_loadings_orders_each_axis():
    loadings = pd.DataFrame({"PC1": [0.5, -0.2, 0.1]}, index=["a", "b", "c"])
    out = top_loadings(loadings, n=1)
    assert out["PC1"] == {"negative": {"b": -0.2}, "positive": {"a": 0.5}}


def test_describe_clusters_lists_members():
    profiles = pd.DataFrame({"x": [1.0, -1.0], "y": [-0.5, 0.5]}, index=[1, 2])
    clusters = pd.DataFrame({"cluster": [1, 1, 2]}, index=["01", "02", "75"])
    out = describe_clusters(profiles, clusters, n=1)
    assert out["1"]["members"] == ["01", "02"]
    assert out["2"]["above"] == {"y": 0.5}
