"""Statistical analysis (protocol Sections 14-15, hypotheses H1-H5).

Reads data/processed/v1/grid_1km.parquet and writes
reports/analysis_summary.json plus PNG figures in reports/figures/.

Association language only. No causal or health claims.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from scipy.sparse import csr_matrix
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

from src.common import ROOT, load_config

GRID = ROOT / "data" / "processed" / "v1" / "grid_1km.parquet"
FIGDIR = ROOT / "reports" / "figures"
SUMMARY = ROOT / "reports" / "analysis_summary.json"
RNG = np.random.default_rng(20261001)

FEATURES_EXT = ["ndvi", "ndbi", "dist_coast_km", "elev_m"]


def load_grid():
    df = pd.read_parquet(GRID)
    # cell lattice indices for spatial weights
    df["ix"] = ((df["cx"] - 262830.0) // 1000).astype(int)
    df["iy"] = ((2838150.0 - df["cy"]) // 1000).astype(int)
    return df


def pearson_ci(r, n, alpha=0.05):
    z = np.arctanh(np.clip(r, -0.999999, 0.999999))
    se = 1.0 / np.sqrt(n - 3)
    lo, hi = z + stats.norm.ppf([alpha / 2, 1 - alpha / 2]) * se
    return [float(np.tanh(lo)), float(np.tanh(hi))]


def spearman_ci(x, y, n_boot=1000, alpha=0.05):
    n = len(x)
    idx = RNG.integers(0, n, size=(n_boot, n))
    boots = [stats.spearmanr(x[i], y[i]).statistic for i in idx]
    return [float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2))]


def correlations(df):
    out = []
    for year, g in df.groupby("year"):
        x = g["ndvi"].to_numpy()
        y = g["lst_c"].to_numpy()
        r = float(stats.pearsonr(x, y).statistic)
        rho = float(stats.spearmanr(x, y).statistic)
        out.append({
            "year": int(year), "n": int(len(g)),
            "pearson_r": r, "pearson_ci": pearson_ci(r, len(g)),
            "spearman_rho": rho, "spearman_ci": spearman_ci(x, y),
        })
    return out


def pooled_ols(df, features, add_year_fe=True):
    X = df[features].copy()
    if add_year_fe:
        dummies = pd.get_dummies(df["year"], prefix="yr", drop_first=True, dtype=float)
        X = pd.concat([X, dummies], axis="columns")
    X = sm.add_constant(X, has_constant="add")
    y = df["lst_c"].to_numpy()
    model = sm.OLS(y, X).fit(cov_type="HC3")
    return model, X


def morans_i(values, ix, iy):
    """Moran's I with queen contiguity on the integer lattice."""
    n = len(values)
    key = pd.DataFrame({"ix": ix, "iy": iy})
    key["pos"] = np.arange(n)
    lut = {(a, b): p for a, b, p in zip(key["ix"], key["iy"], key["pos"])}
    rows, cols = [], []
    for a, b, p in zip(key["ix"], key["iy"], key["pos"]):
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                if da == 0 and db == 0:
                    continue
                q = lut.get((a + da, b + db))
                if q is not None:
                    rows.append(p)
                    cols.append(q)
    W = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    wsum = W.sum()
    x = values - values.mean()
    denom = float(x @ x)
    if denom == 0 or wsum == 0:
        return float("nan")
    num = float(x @ (W @ x))
    return float((n / wsum) * (num / denom))


def vif_max(df, features):
    X = sm.add_constant(df[features].to_numpy(), has_constant="add")
    vifs = [variance_inflation_factor(X, i) for i in range(1, X.shape[1])]
    return float(np.max(vifs))


def persistence_test(df, n_sims=20000):
    """H3: do hot+low-veg cells recur across years more often than chance?

    Hotspot = top LST decile per year; low-veg = bottom NDVI decile per year.
    Statistic: cells in the joint set in >= 3 of the years.
    Chance model: independent Bernoulli draws per cell-year with the
    year's observed joint-set rate. Monte Carlo p-value (fixed seed).
    """
    df = df.copy()
    df["hot"] = df.groupby("year")["lst_c"].transform(
        lambda s: s >= s.quantile(0.9))
    df["lowveg"] = df.groupby("year")["ndvi"].transform(
        lambda s: s <= s.quantile(0.1))
    df["joint"] = df["hot"] & df["lowveg"]
    years = sorted(df["year"].unique())
    p_y = {y: float(df.loc[df["year"] == y, "joint"].mean()) for y in years}
    counts = df.groupby("cell_id")["joint"].sum()
    obs = int((counts >= 3).sum())
    n_cells = int(counts.shape[0])
    # Monte Carlo under independence
    sim_counts = np.zeros(n_sims, dtype=int)
    cell_years = df.groupby("cell_id")["year"].apply(list)
    py_arr = np.array([p_y[y] for y in years])
    year_index = {y: i for i, y in enumerate(years)}
    for ci, (cell, ys) in enumerate(cell_years.items()):
        probs = np.array([p_y[y] for y in ys])
        draws = RNG.random((n_sims, len(ys))) < probs
        sim_counts += (draws.sum(axis=1) >= 3).astype(int)
    expected = float(sim_counts.mean())
    p_value = float((np.sum(sim_counts >= obs) + 1) / (n_sims + 1))
    return {
        "n_hot_lowveg_cells": n_cells,
        "years_overlap_observed": obs,
        "expected_chance": expected,
        "p_value": p_value,
    }


def spatial_block_folds(df, block_m=5000):
    """Assign each row to a spatial block fold (5 km blocks)."""
    bx = ((df["cx"] - 262830.0) // block_m).astype(int)
    by = ((2838150.0 - df["cy"]) // block_m).astype(int)
    blocks = list(zip(bx, by))
    uniq = sorted(set(blocks))
    fold_of = {b: i % 5 for i, b in enumerate(uniq)}
    return np.array([fold_of[b] for b in blocks])


def run_ml(df, cfg):
    """Random Forest vs linear baseline under the five go/no-go criteria."""
    ml_cfg = cfg["hypotheses"]
    feats = [f for f in FEATURES_EXT if df[f].notna().all()]
    result = {"included": False, "reason": "", "cv_rmse_rf": None,
              "cv_rmse_linear": None, "cv_mae_rf": None, "cv_mae_linear": None}
    # Criterion 1: sample size
    per_year = df.groupby("year").size()
    if (per_year < ml_cfg["ml_min_cells_per_year"]).any():
        result["reason"] = (
            f"criterion 1 failed: some years have fewer than "
            f"{ml_cfg['ml_min_cells_per_year']} cells "
            f"(min observed {int(per_year.min())})")
        return result
    # Criterion 2: covariates consistent across years
    if len(feats) < len(FEATURES_EXT):
        missing = [f for f in FEATURES_EXT if f not in feats]
        result["reason"] = (
            f"criterion 2 failed: covariates not available in all years: {missing}")
        return result
    X = df[feats].to_numpy()
    y = df["lst_c"].to_numpy()
    folds = spatial_block_folds(df, block_m=cfg["grid"]["cv_block_m"])
    rf_rmses, lin_rmses, rf_maes, lin_maes = [], [], [], []
    importances = []
    rf_oof = np.full_like(y, np.nan)
    lin_oof = np.full_like(y, np.nan)
    for k in range(5):
        tr, te = folds != k, folds == k
        rf = RandomForestRegressor(n_estimators=300, n_jobs=-1,
                                   random_state=20261001, min_samples_leaf=5)
        rf.fit(X[tr], y[tr])
        pr = rf.predict(X[te])
        Xtr = sm.add_constant(X[tr], has_constant="add")
        Xte = sm.add_constant(X[te], has_constant="add")
        lin = sm.OLS(y[tr], Xtr).fit()
        pl = lin.predict(Xte)
        rf_oof[te] = pr
        lin_oof[te] = pl
        rf_rmses.append(float(np.sqrt(np.mean((y[te] - pr) ** 2))))
        lin_rmses.append(float(np.sqrt(np.mean((y[te] - pl) ** 2))))
        rf_maes.append(float(np.mean(np.abs(y[te] - pr))))
        lin_maes.append(float(np.mean(np.abs(y[te] - pl))))
        imp = permutation_importance(rf, X[te], y[te], n_repeats=5,
                                     random_state=20261001, n_jobs=-1)
        importances.append(imp.importances_mean)
    cv_rmse_rf = float(np.mean(rf_rmses))
    cv_rmse_lin = float(np.mean(lin_rmses))
    result.update({
        "cv_rmse_rf": cv_rmse_rf, "cv_rmse_linear": cv_rmse_lin,
        "cv_mae_rf": float(np.mean(rf_maes)),
        "cv_mae_linear": float(np.mean(lin_maes)),
    })
    # Criterion 3: margin over the linear baseline
    improvement = (cv_rmse_lin - cv_rmse_rf) / cv_rmse_lin * 100.0
    if improvement < ml_cfg["ml_min_rmse_improvement_pct"]:
        result["reason"] = (
            f"criterion 3 failed: RF improves RMSE by {improvement:.2f}%, "
            f"below the {ml_cfg['ml_min_rmse_improvement_pct']}% margin")
        return result
    # Criterion 4: stable permutation importance rankings
    ranks = [list(np.argsort(-imp)) for imp in importances]
    top1 = {r[0] for r in ranks}
    if len(top1) > 1:
        result["reason"] = (
            "criterion 4 failed: top permutation-importance predictor "
            f"differs across folds ({sorted(feats[i] for i in top1)})")
        return result
    # Criterion 5: residual spatial autocorrelation no worse than baseline
    res_rf = y - rf_oof
    res_lin = y - lin_oof
    mi_rf = np.nanmean([morans_i(res_rf[df["year"].to_numpy() == yr],
                                 df.loc[df["year"] == yr, "ix"].to_numpy(),
                                 df.loc[df["year"] == yr, "iy"].to_numpy())
                        for yr in sorted(df["year"].unique())])
    mi_lin = np.nanmean([morans_i(res_lin[df["year"].to_numpy() == yr],
                                  df.loc[df["year"] == yr, "ix"].to_numpy(),
                                  df.loc[df["year"] == yr, "iy"].to_numpy())
                         for yr in sorted(df["year"].unique())])
    result["morans_i_rf_oof"] = float(mi_rf)
    result["morans_i_linear_oof"] = float(mi_lin)
    if mi_rf > mi_lin:
        result["reason"] = (
            f"criterion 5 failed: RF out-of-fold Moran's I ({mi_rf:.3f}) exceeds "
            f"the linear baseline ({mi_lin:.3f})")
        return result
    result["included"] = True
    result["reason"] = (
        f"all five go/no-go criteria passed: {int(per_year.min())}+ cells/yr, "
        f"all covariates present, RF RMSE {improvement:.1f}% below linear, "
        f"stable importance (top: {feats[ranks[0][0]]}), "
        f"Moran's I RF {mi_rf:.3f} <= linear {mi_lin:.3f}")
    return result


def main():
    cfg = load_config()
    FIGDIR.mkdir(parents=True, exist_ok=True)
    df = load_grid()
    years = sorted(df["year"].unique())
    print(f"grid rows: {len(df)}, years: {years}", flush=True)

    corr = correlations(df)

    # Pooled OLS: LST ~ NDVI + year fixed effects (HC3)
    model, X = pooled_ols(df, ["ndvi"])
    slope = float(model.params["ndvi"])
    ci = model.conf_int(alpha=0.05).loc["ndvi"]
    # Moran's I on residuals, per year, averaged
    resid = model.resid.to_numpy() if hasattr(model.resid, "to_numpy") else np.asarray(model.resid)
    mis = []
    for yr in years:
        m = df["year"].to_numpy() == yr
        mis.append(morans_i(resid[m], df.loc[m, "ix"].to_numpy(), df.loc[m, "iy"].to_numpy()))
    mi_mean = float(np.nanmean(mis))

    # Interaction test H2: NDVI x year
    Xi = df[["ndvi"]].copy()
    dummies = pd.get_dummies(df["year"], prefix="yr", drop_first=True, dtype=float)
    Xi = pd.concat([Xi, dummies], axis="columns")
    for c in dummies.columns:
        Xi[f"ndvi:{c}"] = df["ndvi"].to_numpy() * dummies[c].to_numpy()
    Xi = sm.add_constant(Xi, has_constant="add")
    mi_model = sm.OLS(df["lst_c"].to_numpy(), Xi.to_numpy()).fit(cov_type="HC3")
    inter_terms = [f"ndvi:{c}" for c in dummies.columns]
    R = np.zeros((len(inter_terms), len(mi_model.params)))
    for i, t in enumerate(inter_terms):
        R[i, list(Xi.columns).index(t)] = 1.0
    f_test = mi_model.f_test(R)
    year_interaction_p = float(f_test.pvalue)

    # Extended model H4 (+ NDBI, dist_coast_km, elev_m where available)
    feats_ext = [f for f in FEATURES_EXT if df[f].notna().all()]
    model_ndvi_only, _ = pooled_ols(df, ["ndvi"])
    model_ext, _ = pooled_ols(df, feats_ext)
    vif = vif_max(df, feats_ext) if len(feats_ext) > 1 else 1.0

    persist = persistence_test(df)

    ml = run_ml(df, cfg)

    scene_counts = {}
    coverage = {}
    with open(ROOT / "data" / "processed" / "v1" / "_grid_meta.json") as f:
        n_land_cells = json.load(f)["n_land_cells"]
    for year in years:
        with open(ROOT / "data" / "interim" / "dates" / str(year) / f"_diag_{year}.json") as f:
            d = json.load(f)
        scene_counts[str(year)] = d["n_dates"]
        n_cells = int((df["year"] == year).sum())
        coverage[str(year)] = round(n_cells / n_land_cells, 4)

    summary = {
        "years": [int(y) for y in years],
        "correlation": corr,
        "regression": {
            "ndvi_slope": slope,
            "slope_ci": [float(ci[0]), float(ci[1])],
            "r_squared": float(model.rsquared),
            "n": int(model.nobs),
            "morans_i_residuals": mi_mean,
            "vif": vif,
        },
        "year_interaction_p": year_interaction_p,
        "persistence": persist,
        "ml": ml,
        "scene_counts": scene_counts,
        "coverage": coverage,
        "extended_model": {
            "features": feats_ext,
            "r_squared": float(model_ext.rsquared),
            "r_squared_ndvi_only": float(model_ndvi_only.rsquared),
            "params": {k: float(v) for k, v in
                       zip(model_ext.params.index, model_ext.params.to_numpy())
                       if k != "const" and not k.startswith("yr_")},
        },
    }
    with open(SUMMARY, "w") as f:
        json.dump(summary, f, indent=2)
    print("wrote", SUMMARY, flush=True)

    make_figures(df, corr)
    return summary


def make_figures(df, corr):
    from src.common import GRID_SHAPE, GRID_TRANSFORM
    import rasterio
    from rasterio.enums import Resampling
    years = sorted(df["year"].unique())
    for year in years:
        g = df[df["year"] == year]
        # scatter
        fig, ax = plt.subplots(figsize=(6, 4.5))
        ax.scatter(g["ndvi"], g["lst_c"], s=4, alpha=0.25, rasterized=True)
        ax.set_xlabel("NDVI (median composite)")
        ax.set_ylabel("Land surface temperature (C)")
        ax.set_title(f"Karachi: NDVI vs LST, May-June {year} "
                     f"(n={len(g)} cells; USGS Landsat C2 L2 via Planetary Computer)")
        fig.tight_layout()
        fig.savefig(FIGDIR / f"ndvi_lst_scatter_{year}.png", dpi=120)
        plt.close(fig)
        # maps from the 30 m composites (downsampled for display)
        for var, fname, label, cmap, vmin, vmax in [
            ("lst_c", f"lst_map_{year}.png", "Land surface temperature (C)", "inferno", 25, 60),
            ("ndvi", f"ndvi_map_{year}.png", "NDVI", "YlGn", -0.2, 0.8),
        ]:
            p = ROOT / "data" / "processed" / "v1" / "composites" / f"{year}_{var}.tif"
            with rasterio.open(p) as src:
                arr = src.read(1, out_shape=(src.height // 4, src.width // 4),
                               resampling=Resampling.bilinear)
            fig, ax = plt.subplots(figsize=(6, 6))
            im = ax.imshow(arr, cmap=cmap, vmin=vmin, vmax=vmax)
            ax.set_title(f"{label}, Karachi, May-June {year}")
            ax.set_axis_off()
            fig.colorbar(im, ax=ax, label=label, shrink=0.7)
            fig.tight_layout()
            fig.savefig(FIGDIR / fname, dpi=120)
            plt.close(fig)
    # correlation time series
    fig, ax = plt.subplots(figsize=(8, 4))
    ys = [c["year"] for c in corr]
    rs = [c["pearson_r"] for c in corr]
    lo = [c["pearson_ci"][0] for c in corr]
    hi = [c["pearson_ci"][1] for c in corr]
    ax.errorbar(ys, rs, yerr=[np.array(rs) - np.array(lo), np.array(hi) - np.array(rs)],
                fmt="o-", capsize=3)
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Pearson r (NDVI vs LST)")
    ax.set_title("NDVI-LST association by year, Karachi May-June (95% CI)")
    fig.tight_layout()
    fig.savefig(FIGDIR / "correlation_timeseries.png", dpi=120)
    plt.close(fig)
    # hotspot persistence map: count of years each cell was hot+low-veg
    df = df.copy()
    df["hot"] = df.groupby("year")["lst_c"].transform(lambda s: s >= s.quantile(0.9))
    df["lowveg"] = df.groupby("year")["ndvi"].transform(lambda s: s <= s.quantile(0.1))
    df["joint"] = (df["hot"] & df["lowveg"]).astype(int)
    piv = df.pivot_table(index="iy", columns="ix", values="joint",
                         aggfunc="sum", fill_value=0)
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(piv.to_numpy()[::-1], cmap="Reds", vmin=0, vmax=len(years))
    ax.set_title("Hotspot persistence: years each 1 km cell was in the top LST\n"
                 "decile and bottom NDVI decile (2015-2025)")
    ax.set_axis_off()
    fig.colorbar(im, ax=ax, label="years", shrink=0.7)
    fig.tight_layout()
    fig.savefig(FIGDIR / "hotspot_persistence.png", dpi=120)
    plt.close(fig)
    print("figures written", flush=True)


if __name__ == "__main__":
    main()
