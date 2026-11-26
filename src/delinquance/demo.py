"""Build the static demo page in docs/ (GitHub Pages): rate maps, typology map and twins."""

import json
import logging
import shutil
from pathlib import Path

import pandas as pd

from delinquance import DOCS_DIR, REPORTS_DIR
from delinquance.obtain import MANIFEST, RAW_GEOJSON
from delinquance.scrub import load_modelled
from delinquance.typology import N_TWINS, PROFILE_YEARS

log = logging.getLogger(__name__)

TEMPLATE = Path(__file__).with_name("demo_template.html")
# The map outline covers mainland France only; overseas departments are shown in a table.
OVERSEAS = {
    "971": "Guadeloupe",
    "972": "Martinique",
    "973": "Guyane",
    "974": "La Réunion",
    "976": "Mayotte",
}


def round_coords(coords, digits: int = 3):
    """Round nested GeoJSON coordinates (3 decimals is about 100 m, enough for a national map)."""
    if isinstance(coords[0], (int, float)):
        return [round(c, digits) for c in coords]
    return [round_coords(c, digits) for c in coords]


def light_geojson(path: Path) -> dict:
    geo = json.loads(path.read_text())
    for feature in geo["features"]:
        feature["geometry"]["coordinates"] = round_coords(feature["geometry"]["coordinates"])
        feature["properties"] = {"code": feature["properties"]["code"]}
    return geo


def department_names(geo_path: Path) -> dict[str, str]:
    geo = json.loads(geo_path.read_text())
    return {f["properties"]["code"]: f["properties"]["nom"] for f in geo["features"]} | OVERSEAS


def rates_by_indicator(df: pd.DataFrame) -> dict:
    """{indicator: {year: {dep: rate}}} with 4 significant digits."""
    out: dict = {}
    for (indicator, year), rows in df.groupby(["indicator", "year"]):
        rates = rows.set_index("dep")["rate"].map(lambda r: float(f"{r:.4g}"))
        out.setdefault(indicator, {})[str(year)] = rates.to_dict()
    return out


def national_series(df: pd.DataFrame) -> dict:
    """{indicator: [rate per year]} from the explore step, in year order."""
    national = pd.read_csv(REPORTS_DIR / "explore/national_rates.csv")
    return national.groupby("indicator")["rate"].apply(lambda s: s.round(4).tolist()).to_dict()


def build_data(df: pd.DataFrame, names: dict[str, str]) -> dict:
    clusters = pd.read_csv(REPORTS_DIR / "typology/clusters.csv", dtype={"dep": str})
    twins = pd.read_csv(REPORTS_DIR / "typology/twins.csv", dtype={"dep": str, "twin": str})
    summary = json.loads((REPORTS_DIR / "summary.json").read_text())
    manifest = json.loads(MANIFEST.read_text())
    typology = summary["typology"]
    return {
        "names": names,
        "overseas": list(OVERSEAS),
        "indicators": sorted(df["indicator"].unique()),
        "per_housing": sorted(df.loc[df["denominator"] == "housing", "indicator"].unique()),
        "years": sorted(int(y) for y in df["year"].unique()),
        "rates": rates_by_indicator(df),
        "national": national_series(df),
        "method": {
            "name": typology["method"],
            "k": typology["k"],
            "profile_years": PROFILE_YEARS,
            "n_twins": N_TWINS,
        },
        "clusters": clusters.set_index("dep")["cluster"].to_dict(),
        "cluster_info": typology["clusters"],
        "twins": {
            dep: g.sort_values("rank")[["twin", "distance"]].values.tolist()
            for dep, g in twins.groupby("dep")
        },
        "source": {
            "updated": manifest["dataset_last_modified"][:10],
            "sha256": manifest["sha256"][:12],
        },
    }


def run() -> None:
    df = load_modelled()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    data = build_data(df, department_names(RAW_GEOJSON))
    (DOCS_DIR / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    geo = light_geojson(RAW_GEOJSON)
    (DOCS_DIR / "departements.geojson").write_text(json.dumps(geo, separators=(",", ":")))
    shutil.copy(TEMPLATE, DOCS_DIR / "index.html")
    log.info("demo written to %s", DOCS_DIR.name)
