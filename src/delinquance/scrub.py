"""Scrub: parse and validate the raw base without dropping or overwriting any value.

Every check adds a flag to the rows it concerns. The output has exactly the rows of the input.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from delinquance import PROCESSED_DIR, REPORTS_DIR
from delinquance.obtain import RAW_CSV

log = logging.getLogger(__name__)

COLUMNS = {
    "Code_departement": "dep",
    "Code_region": "region",
    "annee": "year",
    "indicateur": "indicator",
    "unite_de_compte": "unit",
    "nombre": "count",
    "taux_pour_mille": "rate",
    "insee_pop": "population",
    "insee_pop_millesime": "population_vintage",
    "insee_log": "housing",
    "insee_log_millesime": "housing_vintage",
}
NUMERIC = [
    "year",
    "count",
    "rate",
    "population",
    "population_vintage",
    "housing",
    "housing_vintage",
]
KEY = ["dep", "year", "indicator"]

# Units listed in the SSMSI documentation (July 2026). Used to check rows, never to filter them.
EXPECTED_UNITS = {
    "Homicides": "Victime",
    "Tentatives d'homicide": "Victime",
    "Violences physiques intrafamiliales": "Victime",
    "Violences physiques hors cadre familial": "Victime",
    "Violences sexuelles": "Victime",
    "Vols avec armes": "Infraction",
    "Vols violents sans arme": "Infraction",
    "Vols sans violence contre des personnes": "Victime entendue",
    "Cambriolages de logement": "Infraction",
    "Vols de véhicule": "Véhicule",
    "Vols dans les véhicules": "Véhicule",
    "Vols d'accessoires sur véhicules": "Véhicule",
    "Destructions et dégradations volontaires": "Infraction",
    "Usage de stupéfiants": "Mis en cause",
    "Usage de stupéfiants (AFD)": "Mis en cause",
    "Usage de stupéfiants (hors AFD)": "Mis en cause",
    "Trafic de stupéfiants": "Mis en cause",
    "Escroqueries et fraudes aux moyens de paiement": "Victime",
}
# Sub-indicators that split a parent indicator: adding them to the parent would count twice.
NESTED = {"Usage de stupéfiants": ["Usage de stupéfiants (AFD)", "Usage de stupéfiants (hors AFD)"]}

DEP_PATTERN = r"^(\d{2}|2A|2B|97[1-6])$"
RATE_RTOL = 1e-4
MAX_VINTAGE_LAG = 3

CLEAN_CSV = PROCESSED_DIR / "delinquance_clean.csv"
REPORT_JSON = REPORTS_DIR / "scrub_report.json"


def load_raw(path: Path) -> pd.DataFrame:
    """Read every column as text so that nothing is silently converted."""
    df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False)
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    return df.rename(columns=COLUMNS)[list(COLUMNS.values())]


def parse_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """Convert numeric columns (French decimal comma). Unparsable values become NaN."""
    out = df.copy()
    for col in NUMERIC:
        out[col] = pd.to_numeric(df[col].str.replace(",", ".", regex=False), errors="coerce")
    out["year"] = out["year"].astype("Int64")
    return out


def infer_denominator(df: pd.DataFrame) -> pd.Series:
    """For each indicator, pick the denominator (population or housing) that reproduces the rate."""
    matches = pd.DataFrame(
        {
            "population": np.isclose(df["rate"], df["count"] / df["population"] * 1000, RATE_RTOL),
            "housing": np.isclose(df["rate"], df["count"] / df["housing"] * 1000, RATE_RTOL),
            "indicator": df["indicator"],
        }
    )
    share = matches.groupby("indicator")[["population", "housing"]].mean()
    return share.idxmax(axis=1).rename("denominator")


def flag_rows(df: pd.DataFrame) -> pd.Series:
    """Return one string of semicolon-separated flags per row (empty when the row is fine)."""
    denominator = np.where(df["denominator"] == "housing", df["housing"], df["population"])
    expected_rate = df["count"] / denominator * 1000
    checks = {
        "unparsable_number": df[NUMERIC].isna().any(axis=1),
        "bad_dep_code": ~df["dep"].str.match(DEP_PATTERN),
        "duplicate_key": df.duplicated(KEY, keep=False),
        "negative_count": df["count"] < 0,
        "unexpected_unit": df["unit"] != df["indicator"].map(EXPECTED_UNITS),
        "rate_mismatch": ~np.isclose(df["rate"], expected_rate, RATE_RTOL),
        "stale_population": df["year"] - df["population_vintage"] > MAX_VINTAGE_LAG,
    }
    flags = pd.Series("", index=df.index)
    for name, mask in checks.items():
        mask = pd.Series(mask, index=df.index).fillna(False).astype(bool)
        flags = flags.where(~mask, flags + name + ";")
    return flags.str.rstrip(";")


def incomplete_series(df: pd.DataFrame) -> list[dict]:
    """List (dep, indicator) pairs that miss some of the years present in the file."""
    n_years = df["year"].nunique()
    counts = df.groupby(["dep", "indicator"])["year"].nunique()
    short = counts[counts < n_years]
    return [{"dep": d, "indicator": i, "years": int(n)} for (d, i), n in short.items()]


def nested_mismatches(df: pd.DataFrame) -> int:
    """Count (dep, year) cells where a parent indicator differs from the sum of its parts."""
    wide = df.pivot_table(index=["dep", "year"], columns="indicator", values="count")
    bad = 0
    for parent, parts in NESTED.items():
        if parent in wide and all(p in wide for p in parts):
            bad += int((wide[parent] != wide[parts].sum(axis=1)).sum())
    return bad


def iqr_outside(values: pd.Series) -> pd.Series:
    """Mask of values outside Q1 - 1.5 IQR and Q3 + 1.5 IQR (reported, never capped)."""
    q1, q3 = values.quantile([0.25, 0.75])
    return (values < q1 - 1.5 * (q3 - q1)) | (values > q3 + 1.5 * (q3 - q1))


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = parse_numbers(raw)
    df["denominator"] = df["indicator"].map(infer_denominator(df))
    df["flags"] = flag_rows(df)
    return df


def build_report(df: pd.DataFrame) -> dict:
    flags = df["flags"].str.split(";").explode()
    flags = flags[flags != ""]
    by_indicator = df.groupby("indicator").agg(
        unit=("unit", "first"), denominator=("denominator", "first")
    )
    yearly = df.groupby(["indicator", "year"])["count"].sum()
    return {
        "rows": len(df),
        "departments": int(df["dep"].nunique()),
        "years": [int(df["year"].min()), int(df["year"].max())],
        "indicators": by_indicator.to_dict(orient="index"),
        "flag_counts": flags.value_counts().to_dict(),
        "flagged_by_department": df.loc[df["flags"] != "", "dep"].value_counts().to_dict(),
        "zero_years": {
            ind: [int(y) for y in s.index.get_level_values("year")[s.to_numpy() == 0]]
            for ind, s in yearly.groupby(level="indicator")
            if (s == 0).any()
        },
        "incomplete_series": incomplete_series(df),
        "nested_mismatches": nested_mismatches(df),
        # Checks that the first version of the project got wrong, kept here as evidence.
        "rates_not_per_inhabitant": int(
            (~np.isclose(df["rate"], df["count"] / df["population"] * 1000, RATE_RTOL)).sum()
        ),
        "iqr_outside": {
            col: sorted(df.loc[iqr_outside(df[col]), "dep"].unique())
            for col in ["population", "housing"]
        },
    }


def load_clean(path: Path = CLEAN_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"dep": str, "region": str, "flags": str}, keep_default_na=False)


def independent_indicators(df: pd.DataFrame) -> list[str]:
    """Indicators that are not a sub-part of another one (used for profiles and models)."""
    parts = {p for children in NESTED.values() for p in children}
    return sorted(set(df["indicator"]) - parts)


def run() -> None:
    raw = load_raw(RAW_CSV)
    df = clean(raw)
    assert len(df) == len(raw), "scrub must keep every row"
    report = build_report(df)
    for name, n in report["flag_counts"].items():
        log.warning("%d rows flagged %s", n, name)
    CLEAN_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEAN_CSV, index=False)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    log.info("%d rows kept, report in %s", len(df), REPORT_JSON.name)
