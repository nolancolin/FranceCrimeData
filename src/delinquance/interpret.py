"""Interpret: gather key results in one file, the single source of the numbers in the README."""

import json
import logging

import pandas as pd

from delinquance import REPORTS_DIR
from delinquance.scrub import REPORT_JSON

log = logging.getLogger(__name__)

SUMMARY = REPORTS_DIR / "summary.json"


def read(name: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(REPORTS_DIR / name, **kwargs)


def top_loadings(loadings: pd.DataFrame, n: int = 3) -> dict:
    """For each axis, the indicators that pull it most in each direction."""
    out = {}
    for pc in loadings.columns:
        s = loadings[pc].sort_values()
        out[pc] = {
            "negative": s.head(n).round(2).to_dict(),
            "positive": s.tail(n)[::-1].round(2).to_dict(),
        }
    return out


def describe_clusters(profiles: pd.DataFrame, clusters: pd.DataFrame, n: int = 3) -> dict:
    """Size, members and the indicators furthest above and below average for each cluster."""
    out = {}
    for c, row in profiles.iterrows():
        s = row.sort_values()
        out[str(c)] = {
            "size": int((clusters["cluster"] == c).sum()),
            "members": sorted(clusters.index[clusters["cluster"] == c]),
            "above": s.tail(n)[::-1].round(2).to_dict(),
            "below": s.head(n).round(2).to_dict(),
        }
    return out


def summarize() -> dict:
    scrub = json.loads(REPORT_JSON.read_text())
    changes = read("explore/national_changes.csv", index_col=0)
    spread = read("explore/department_spread.csv", index_col=0)
    variance = read("typology/pca_variance.csv", index_col=0)["explained_variance"]
    selection = read("typology/cluster_selection.csv")
    clusters = read("typology/clusters.csv", index_col=0, dtype={"dep": str})
    profiles = read("typology/cluster_profiles.csv", index_col=0)
    by_indicator = read("forecast/scores_by_indicator.csv", index_col=0)
    choice = json.loads((REPORTS_DIR / "typology/choice.json").read_text())
    chosen = selection.set_index(["method", "k"]).loc[(choice["method"], choice["k"])]
    return {
        "data": {
            key: scrub[key]
            for key in ["rows", "departments", "years", "flag_counts", "rates_not_per_inhabitant"]
        }
        | {"indicators_modelled": len(changes), "iqr_outside": scrub["iqr_outside"]},
        "explore": {
            "largest_rises": changes["change_whole_period"].nlargest(3).to_dict(),
            "largest_falls": changes["change_whole_period"].nsmallest(3).to_dict(),
            "drop_2020": changes["change_shock_year"].nsmallest(3).to_dict(),
            "spread_p90_over_p10": spread["p90_over_p10"].agg(["min", "max"]).round(2).to_dict(),
        },
        "typology": {
            "variance_pc1_pc2": variance.head(2).round(3).to_dict(),
            "top_loadings": top_loadings(read("typology/pca_loadings.csv", index_col=0)),
            "method": choice["method"],
            "k": choice["k"],
            "silhouette": float(chosen["silhouette"]),
            "stability_ari": float(chosen["stability_ari"]),
            "best_ward_stability": float(
                selection.query("method == 'ward'")["stability_ari"].max()
            ),
            "clusters": describe_clusters(profiles, clusters),
        },
        "forecast": {
            "overall_mae": read("forecast/scores_overall.csv").iloc[0].to_dict(),
            "mae_by_year": read("forecast/scores_by_year.csv", index_col=0).to_dict(orient="index"),
            "gbm_minus_naive": read("forecast/gbm_minus_naive.csv", index_col=0).to_dict(
                orient="index"
            ),
            "indicators_where_gbm_beats_naive": sorted(
                by_indicator.index[by_indicator["mae_gbm"] < by_indicator["mae_naive"]]
            ),
        },
    }


def run() -> None:
    summary = summarize()
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    log.info("wrote %s", SUMMARY.name)
