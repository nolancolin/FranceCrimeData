"""Model, part 2: forecast next year's rate for every (department, indicator) pair.

Rolling backtest: to predict year N, the model only sees targets up to N-1 and features up to N-1.
All errors are measured on y = log(1 + rate per 100,000).
"""

import logging

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from sklearn.ensemble import HistGradientBoostingRegressor

from delinquance import REPORTS_DIR
from delinquance.scrub import independent_indicators, load_clean

log = logging.getLogger(__name__)

OUT = REPORTS_DIR / "forecast"
FIGURES = REPORTS_DIR / "figures"
N_LAGS = 3
N_TEST_YEARS = 4
METHODS = ["naive", "trend", "gbm"]
SEED = 0
# Set once before looking at test scores; not tuned on the backtest years.
GBM_PARAMS = dict(
    max_iter=200,
    learning_rate=0.05,
    max_leaf_nodes=15,
    min_samples_leaf=40,
    early_stopping=False,
    categorical_features="from_dtype",
    random_state=SEED,
)


def build_panel(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (dep, indicator), one column per year, values y = log(1 + rate per 100,000)."""
    y = np.log1p(df["rate"] * 100)
    return df.assign(y=y).pivot_table(index=["dep", "indicator"], columns="year", values="y")


def features_for_year(panel: pd.DataFrame, year: int) -> pd.DataFrame:
    """Features to predict `year`, built only from the N_LAGS previous years."""
    lags = {f"lag{k}": panel[year - k] for k in range(1, N_LAGS + 1)}
    f = pd.DataFrame(lags)
    f["diff1"] = f["lag1"] - f["lag2"]
    # Mean change of the indicator across departments last year: a shared national signal.
    f["national_diff1"] = f.groupby(level="indicator")["diff1"].transform("mean")
    indicators = sorted(panel.index.get_level_values("indicator").unique())
    f["indicator"] = pd.Categorical(f.index.get_level_values("indicator"), categories=indicators)
    return f


def baselines(f: pd.DataFrame) -> pd.DataFrame:
    """Naive = last year's value. Trend = last value plus the mean yearly slope over 3 years."""
    return pd.DataFrame({"naive": f["lag1"], "trend": f["lag1"] + (f["lag1"] - f["lag3"]) / 2})


def training_set(panel: pd.DataFrame, last_year: int) -> tuple[pd.DataFrame, pd.Series]:
    """Stack every target year from the first one with full lags up to `last_year` included."""
    years = range(int(panel.columns.min()) + N_LAGS, last_year + 1)
    x = pd.concat([features_for_year(panel, y) for y in years])
    target = pd.concat([panel[y] - panel[y - 1] for y in years])
    return x, target


def predict_year(panel: pd.DataFrame, year: int) -> pd.DataFrame:
    """Fit on years < `year`, predict `year`. The model learns the change from last year."""
    x_train, y_train = training_set(panel, year - 1)
    model = HistGradientBoostingRegressor(**GBM_PARAMS).fit(x_train, y_train)
    f = features_for_year(panel, year)
    out = baselines(f)
    out["gbm"] = f["lag1"] + model.predict(f)
    out["y"] = panel[year]
    out["year"] = year
    out["train_years"] = len(y_train) // len(f)
    return out.reset_index()


def backtest(panel: pd.DataFrame, n_test_years: int = N_TEST_YEARS) -> pd.DataFrame:
    last = int(panel.columns.max())
    return pd.concat([predict_year(panel, y) for y in range(last - n_test_years + 1, last + 1)])


def to_rate(y: pd.Series) -> pd.Series:
    return np.expm1(y) / 100


def mae(preds: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Mean absolute error on log-rates, per group."""
    errors = {f"mae_{m}": (preds[m] - preds["y"]).abs() for m in METHODS}
    return pd.DataFrame(errors).groupby([preds[c] for c in by]).mean().round(4)


def wape_by_indicator(preds: pd.DataFrame) -> pd.DataFrame:
    """Sum of absolute rate errors / sum of true rates, per indicator (units are never mixed)."""
    rate = to_rate(preds["y"])
    errors = {f"wape_{m}": (to_rate(preds[m]) - rate).abs() for m in METHODS}
    sums = pd.DataFrame(errors).groupby(preds["indicator"]).sum()
    return sums.div(rate.groupby(preds["indicator"]).sum(), axis=0).round(4)


def bootstrap_gap(preds: pd.DataFrame, n_boot: int = 1000) -> pd.DataFrame:
    """95% interval of MAE(gbm) - MAE(naive) per test year, resampling departments."""
    rng = np.random.default_rng(SEED)
    rows = []
    for year, p in preds.groupby("year"):
        gap = ((p["gbm"] - p["y"]).abs() - (p["naive"] - p["y"]).abs()).groupby(p["dep"]).mean()
        draws = [gap.sample(len(gap), replace=True, random_state=rng).mean() for _ in range(n_boot)]
        low, high = np.percentile(draws, [2.5, 97.5])
        rows.append({"year": year, "gap": gap.mean(), "low": low, "high": high})
    return pd.DataFrame(rows).round(4)


def plot_scores(by_indicator: pd.DataFrame, years: list[int], path) -> None:
    data = by_indicator[[f"mae_{m}" for m in METHODS]].sort_values("mae_naive")
    fig = Figure(figsize=(9, 7))
    ax = fig.subplots()
    pos = np.arange(len(data))
    labels = {"naive": "année précédente", "trend": "tendance", "gbm": "gradient boosting"}
    for i, method in enumerate(METHODS):
        ax.barh(pos + (i - 1) * 0.27, data[f"mae_{method}"], height=0.27, label=labels[method])
    ax.set_yticks(pos, data.index, fontsize=8)
    ax.set_xlabel("Erreur absolue moyenne sur log(1 + taux pour 100 000)")
    ax.set_title(f"Prévision de l'année suivante, backtest {min(years)} à {max(years)}")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def run() -> None:
    df = load_clean()
    df = df[df["indicator"].isin(independent_indicators(df))]
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    preds = backtest(build_panel(df))
    by_indicator = mae(preds, ["indicator"]).join(wape_by_indicator(preds))
    by_year = mae(preds, ["year"])
    overall = mae(preds.assign(all="all"), ["all"])
    preds.round(5).to_csv(OUT / "backtest_predictions.csv", index=False)
    by_indicator.to_csv(OUT / "scores_by_indicator.csv")
    by_year.to_csv(OUT / "scores_by_year.csv")
    overall.to_csv(OUT / "scores_overall.csv", index=False)
    bootstrap_gap(preds).to_csv(OUT / "gbm_minus_naive.csv", index=False)
    plot_scores(by_indicator, sorted(preds["year"].unique()), FIGURES / "forecast_scores.png")
    log.info("overall MAE: %s", overall.iloc[0].to_dict())
