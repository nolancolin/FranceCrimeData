"""Model, part 1: typology of departments from their rate profile (PCA, clustering, twins)."""

import json
import logging

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from delinquance import FIGURES_DIR, REPORTS_DIR
from delinquance.scrub import load_modelled

log = logging.getLogger(__name__)

OUT = REPORTS_DIR / "typology"
PROFILE_YEARS = 3
K_RANGE = range(2, 9)
CLUSTER_METHODS = ("kmeans", "ward")
MIN_STABILITY = 0.8
N_BOOT = 50
N_TWINS = 5
SEED = 0


def build_profile(df: pd.DataFrame, n_years: int = PROFILE_YEARS) -> pd.DataFrame:
    """Mean rate per department and indicator over the last n years (one row per department)."""
    recent = df[df["year"] > df["year"].max() - n_years]
    return recent.groupby(["dep", "indicator"])["rate"].mean().unstack()


def standardize(profile: pd.DataFrame) -> pd.DataFrame:
    """log(1 + rate per 100,000) then z-score, so every indicator weighs the same."""
    logged = np.log1p(profile * 100)
    z = StandardScaler().fit_transform(logged)
    return pd.DataFrame(z, index=profile.index, columns=profile.columns)


def run_pca(z: pd.DataFrame, n: int = 3) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    pca = PCA(random_state=SEED).fit(z)
    names = [f"PC{i + 1}" for i in range(len(pca.components_))]
    variance = pd.Series(pca.explained_variance_ratio_, index=names, name="explained_variance")
    loadings = pd.DataFrame(pca.components_[:n].T, index=z.columns, columns=names[:n])
    scores = pd.DataFrame(pca.transform(z)[:, :n], index=z.index, columns=names[:n])
    return variance, loadings, scores


def cluster_labels(x: np.ndarray, method: str, k: int, seed: int = SEED) -> np.ndarray:
    if method == "kmeans":
        return KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(x)
    return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(x)


def stability(x: np.ndarray, method: str, k: int, n_boot: int = N_BOOT) -> float:
    """Mean ARI between the full clustering and clusterings of random 80% subsamples."""
    rng = np.random.default_rng(SEED)
    full = cluster_labels(x, method, k)
    scores = []
    for b in range(n_boot):
        idx = rng.choice(len(x), size=int(0.8 * len(x)), replace=False)
        scores.append(adjusted_rand_score(full[idx], cluster_labels(x[idx], method, k, seed=b)))
    return float(np.mean(scores))


def compare_clusterings(z: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for method in CLUSTER_METHODS:
        for k in K_RANGE:
            labels = cluster_labels(z.to_numpy(), method, k)
            rows.append(
                {
                    "method": method,
                    "k": k,
                    "silhouette": silhouette_score(z, labels),
                    "stability_ari": stability(z.to_numpy(), method, k),
                    "smallest_cluster": int(np.bincount(labels).min()),
                }
            )
    return pd.DataFrame(rows).round(3)


def choose_clustering(table: pd.DataFrame) -> tuple[str, int]:
    """Best silhouette among the settings whose stability reaches MIN_STABILITY."""
    stable = table[table["stability_ari"] >= MIN_STABILITY]
    if stable.empty:
        raise ValueError("no clustering reaches the stability threshold")
    best = stable.loc[stable["silhouette"].idxmax()]
    return str(best["method"]), int(best["k"])


def relabel_by_size(labels: np.ndarray) -> np.ndarray:
    """Number clusters 1, 2, ... from the largest to the smallest, so labels are reproducible."""
    order = pd.Series(labels).value_counts().index
    mapping = {old: new for new, old in enumerate(order, start=1)}
    return np.array([mapping[label] for label in labels])


def find_twins(z: pd.DataFrame, n: int = N_TWINS) -> pd.DataFrame:
    """The n departments closest to each department in the standardized profile space."""
    distances, indices = NearestNeighbors(n_neighbors=n + 1).fit(z).kneighbors(z)
    rows = []
    for i, dep in enumerate(z.index):
        others = [(j, d) for j, d in zip(indices[i], distances[i], strict=True) if j != i][:n]
        for rank, (j, d) in enumerate(others, start=1):
            rows.append({"dep": dep, "rank": rank, "twin": z.index[j], "distance": round(d, 3)})
    return pd.DataFrame(rows)


def plot_pca(scores: pd.DataFrame, clusters: pd.Series, variance: pd.Series, path) -> None:
    fig = Figure(figsize=(9, 7))
    ax = fig.subplots()
    for c in sorted(clusters.unique()):
        s = scores[clusters == c]
        ax.scatter(s["PC1"], s["PC2"], s=28, label=f"Groupe {c} ({len(s)})")
    for dep, (x, y) in scores[["PC1", "PC2"]].iterrows():
        ax.annotate(dep, (x, y), fontsize=6, xytext=(2, 2), textcoords="offset points")
    ax.set_xlabel(f"PC1 ({variance['PC1']:.0%} de la variance)")
    ax.set_ylabel(f"PC2 ({variance['PC2']:.0%} de la variance)")
    ax.set_title("Départements sur les deux premiers axes de l'ACP")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def plot_profiles(profiles: pd.DataFrame, path) -> None:
    fig = Figure(figsize=(8, 7))
    ax = fig.subplots()
    image = ax.imshow(profiles.T, cmap="RdBu_r", vmin=-3, vmax=3, aspect="auto")
    ax.set_xticks(range(len(profiles)), [f"Groupe {c}" for c in profiles.index])
    ax.set_yticks(range(len(profiles.columns)), profiles.columns, fontsize=8)
    for (i, j), v in np.ndenumerate(profiles.T.to_numpy()):
        color = "white" if abs(v) > 1.8 else "black"
        ax.text(j, i, f"{v:+.1f}", ha="center", va="center", fontsize=7, color=color)
    fig.colorbar(image, ax=ax, label="écart à la moyenne des départements (écarts-types)")
    ax.set_title("Profil moyen de chaque groupe")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def run() -> None:
    df = load_modelled()
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    profile = build_profile(df)
    z = standardize(profile)
    variance, loadings, scores = run_pca(z)

    table = compare_clusterings(z)
    method, k = choose_clustering(table)
    log.info("chosen clustering: %s with k=%d", method, k)
    clusters = pd.Series(relabel_by_size(cluster_labels(z.to_numpy(), method, k)), index=z.index)
    cluster_profiles = z.groupby(clusters).mean()

    profile.round(5).to_csv(OUT / "profile_rates.csv")
    variance.round(4).to_csv(OUT / "pca_variance.csv")
    loadings.round(3).to_csv(OUT / "pca_loadings.csv")
    table.to_csv(OUT / "cluster_selection.csv", index=False)
    (OUT / "choice.json").write_text(json.dumps({"method": method, "k": k}) + "\n")
    scores.round(3).assign(cluster=clusters).to_csv(OUT / "clusters.csv")
    cluster_profiles.round(3).to_csv(OUT / "cluster_profiles.csv")
    find_twins(z).to_csv(OUT / "twins.csv", index=False)
    plot_pca(scores, clusters, variance, FIGURES_DIR / "pca_clusters.png")
    plot_profiles(cluster_profiles, FIGURES_DIR / "cluster_profiles.png")
