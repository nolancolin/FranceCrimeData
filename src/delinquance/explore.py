"""Explore: national trends per indicator and spread between departments, always in rates."""

import logging

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from delinquance import FIGURES_DIR, REPORTS_DIR
from delinquance.scrub import load_modelled

log = logging.getLogger(__name__)

OUT = REPORTS_DIR / "explore"
COLOR = "#1f5f8b"
SHOCK_YEAR = 2020  # lockdowns


def national_rates(df: pd.DataFrame) -> pd.DataFrame:
    """National rate per 1,000 = sum of department counts / sum of their denominators."""
    base = np.where(df["denominator"] == "housing", df["housing"], df["population"])
    sums = df.assign(base=base).groupby(["indicator", "year"])[["count", "base"]].sum()
    return (sums["count"] / sums["base"] * 1000).rename("rate").reset_index()


def changes(national: pd.DataFrame) -> pd.DataFrame:
    """Relative change over the whole period, during the shock year (2020) and in the last year."""
    wide = national.pivot(index="indicator", columns="year", values="rate")
    first, last = wide.columns.min(), wide.columns.max()
    return pd.DataFrame(
        {
            "change_whole_period": wide[last] / wide[first] - 1,
            "change_shock_year": wide[SHOCK_YEAR] / wide[SHOCK_YEAR - 1] - 1,
            "change_last_year": wide[last] / wide[last - 1] - 1,
        }
    ).round(3)


def department_spread(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Per indicator, how far apart departments are in a given year (P90 / P10 of the rate)."""
    rows = df[df["year"] == year]
    stats = rows.groupby("indicator")["rate"].quantile([0.1, 0.5, 0.9]).unstack()
    stats.columns = ["p10", "median", "p90"]
    stats["p90_over_p10"] = stats["p90"] / stats["p10"]
    top = rows.loc[rows.groupby("indicator")["rate"].idxmax(), ["indicator", "dep"]]
    stats["highest_dep"] = top.set_index("indicator")["dep"]
    return stats.sort_values("p90_over_p10").round(4)


def plot_national(national: pd.DataFrame, path) -> None:
    indicators = sorted(national["indicator"].unique())
    ncols = 4
    nrows = int(np.ceil(len(indicators) / ncols))
    fig = Figure(figsize=(14, 2.6 * nrows))
    axes = fig.subplots(nrows, ncols, sharex=True)
    for ax, ind in zip(axes.flat, indicators, strict=False):
        s = national[national["indicator"] == ind]
        ax.axvspan(SHOCK_YEAR - 0.5, SHOCK_YEAR + 0.5, color="0.9", lw=0)
        ax.plot(s["year"], s["rate"], color=COLOR, marker="o", ms=3)
        ax.set_title(ind, fontsize=9)
        ax.set_ylim(bottom=0)
        ax.tick_params(labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    for ax in axes.flat[len(indicators) :]:
        ax.set_visible(False)
    fig.suptitle("Taux national pour 1 000 habitants (logements pour les cambriolages), 2020 grisé")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def plot_spread(df: pd.DataFrame, spread: pd.DataFrame, year: int, path) -> None:
    rows = df[df["year"] == year]
    order = list(spread.index)
    fig = Figure(figsize=(10, 0.45 * len(order) + 1.5))
    ax = fig.subplots()
    rng = np.random.default_rng(0)
    for i, ind in enumerate(order):
        ratio = rows.loc[rows["indicator"] == ind, "rate"] / spread.loc[ind, "median"]
        jitter = rng.uniform(-0.18, 0.18, len(ratio))
        ax.scatter(ratio, i + jitter, s=9, color=COLOR, alpha=0.6, lw=0)
        p10, p90 = spread.loc[ind, ["p10", "p90"]] / spread.loc[ind, "median"]
        ax.plot([p10, p90], [i, i], color="black", lw=2)
    ax.set_xscale("log")
    ax.axvline(1, color="0.5", lw=0.8, ls="--")
    ax.set_yticks(range(len(order)), order, fontsize=8)
    ax.set_xlabel("Taux du département / taux médian des départements (échelle log)")
    ax.set_title(f"Écart entre départements en {year} (trait noir : 10e au 90e centile)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def run() -> None:
    df = load_modelled()
    year = int(df["year"].max())
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    national = national_rates(df)
    national.round(5).to_csv(OUT / "national_rates.csv", index=False)
    changes(national).to_csv(OUT / "national_changes.csv")
    plot_national(national, FIGURES_DIR / "national_trends.png")

    spread = department_spread(df, year)
    spread.to_csv(OUT / "department_spread.csv")
    plot_spread(df, spread, year, FIGURES_DIR / "department_spread.png")
    log.info("explore outputs written for %d indicators", national["indicator"].nunique())
