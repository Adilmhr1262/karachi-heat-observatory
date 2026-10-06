#!/usr/bin/env python3
"""Synthetic fixture generator for the Karachi Heat Observatory dashboard.

Creates files that match docs/DATA_CONTRACT.md exactly, with plausible
value ranges, so the Streamlit app in src/app/ can be built and tested
before the real pipeline outputs exist.

This script is a test helper only. The app never imports it.

Usage:
    .venv/bin/python src/app/make_fixtures.py [--root data/fixtures]

Output layout under <root>:
    v1/grid_1km.parquet
    v1/composites/{year}_{ndvi,lst_c,n_obs,stqa,water}.tif   (subset of years)
    v1/boundary_32642.geojson
    reports/analysis_summary.json
    reports/figures/*.png
    manifests/run_fixture_20261001.json

Point the app at the fixtures with:
    KHO_DATA_ROOT=<root>/v1 KHO_REPORTS_ROOT=<root>/reports \\
        KHO_MANIFESTS_ROOT=<root>/manifests .venv/bin/streamlit run src/app/app.py
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import zoom
from shapely.geometry import Point

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_SRC = PROJECT_ROOT / "data" / "boundaries" / "karachi-division-gadm41.geojson"

YEARS = list(range(2015, 2026))
MISSING_YEAR = 2020  # no usable scenes: exercises the "no data" path
TIF_YEARS = [2019, 2021, 2023]  # years with 30 m GeoTIFF fixtures
GRID_M = 1000
PIX_M = 30
SEED = 20261001

# Plausible fixture ranges (contract-consistent, not real observations)
NDVI_RANGE = (-0.2, 0.6)
LST_RANGE = (30.0, 58.0)


def spatial_fields(xs, ys, coast_xy, rng, year_effect):
    """Return ndvi, lst_c, ndbi, elev_m, dist_coast_km on the given points."""
    dx = xs[:, None] - coast_xy[None, :, 0]
    dy = ys[:, None] - coast_xy[None, :, 1]
    dist_coast = np.sqrt((dx * dx + dy * dy).min(axis=1)) / 1000.0

    # Urban core around (approx, EPSG:32642) the city center: less vegetation.
    cx0, cy0 = 672000.0, 2756000.0
    d_core = np.sqrt((xs - cx0) ** 2 + (ys - cy0) ** 2) / 1000.0

    elev = np.clip(6.0 + (ys - 2740000.0) / 1000.0 * 1.1, 0, 160)
    elev += rng.normal(0, 4.0, size=xs.shape)
    elev = np.clip(elev, 0, 160)

    ndvi = (
        0.24
        + 0.10 * np.exp(-dist_coast / 9.0)      # greener near the coast/mangroves
        - 0.13 * np.exp(-(d_core / 9.0) ** 2)    # dense urban core
        + 0.05 * np.exp(-(((xs - 720000.0) / 14000.0) ** 2))  # Malir river belt, east
    )
    ndvi += rng.normal(0, 0.055, size=xs.shape)
    ndvi = np.clip(ndvi, *NDVI_RANGE)

    lst = (
        51.5
        - 21.0 * ndvi
        - 3.2 * np.exp(-dist_coast / 7.0)   # sea-breeze cooling near shore
        + 0.012 * elev
        + year_effect
    )
    lst += rng.normal(0, 1.1, size=xs.shape)
    lst = np.clip(lst, *LST_RANGE)

    ndbi = np.clip(0.28 - 0.95 * ndvi + rng.normal(0, 0.05, size=xs.shape), -0.4, 0.6)
    return ndvi, lst, ndbi, elev, dist_coast


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(PROJECT_ROOT / "data" / "fixtures"),
                    help="fixture root directory")
    args = ap.parse_args()
    root = Path(args.root)
    v1 = root / "v1"
    comp = v1 / "composites"
    rep = root / "reports"
    figd = rep / "figures"
    mand = root / "manifests"
    for d in (v1, comp, rep, figd, mand):
        d.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(SEED)
    print("reading boundary...")
    gdf = gpd.read_file(BOUNDARY_SRC).to_crs(32642)
    land = gdf.geometry.union_all()

    # Coastal reference points: exterior ring points in the south (lat < 24.92)
    g4326 = gdf.to_crs(4326)
    merged = g4326.geometry.union_all()
    polys = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    biggest = max(polys, key=lambda p: p.area)
    coast_ll = np.array([(x, y) for x, y in biggest.exterior.coords if y < 24.92])
    coast_g = gpd.GeoSeries([Point(x, y) for x, y in coast_ll], crs=4326).to_crs(32642)
    coast_xy = np.array([(p.x, p.y) for p in coast_g])

    minx, miny, maxx, maxy = land.bounds
    xs = np.arange(minx + GRID_M / 2, maxx, GRID_M)
    ys = np.arange(miny + GRID_M / 2, maxy, GRID_M)
    gx, gy = np.meshgrid(xs, ys)
    inside = np.array([land.contains(Point(x, y)) for x, y in zip(gx.ravel(), gy.ravel())])
    keep = np.where(inside)[0]
    cx = gx.ravel()[keep]
    cy = gy.ravel()[keep]
    n_cells = len(keep)
    print(f"grid cells inside boundary: {n_cells}")

    cell_ids = [f"c{int(x) // GRID_M}_{int(y) // GRID_M}" for x, y in zip(cx, cy)]

    usable_years = [y for y in YEARS if y != MISSING_YEAR]
    year_effects = {y: 0.09 * (y - 2015) + rng.normal(0, 0.55) for y in YEARS}

    rows = []
    per_year = {}
    for year in usable_years:
        ndvi, lst, ndbi, elev, dist_coast = spatial_fields(
            cx, cy, coast_xy, rng, year_effects[year])
        # Simulate the minimum-observation rule: drop ~5% of cells per year.
        valid = rng.random(n_cells) > 0.05
        n_obs = rng.integers(2, 9, size=n_cells)
        stqa = 0.6 + rng.random(n_cells) * 1.2
        idx = np.where(valid)[0]
        per_year[year] = (ndvi, lst, ndbi, elev, dist_coast, n_obs, stqa, valid)
        for i in idx:
            rows.append((cell_ids[i], year, float(cx[i]), float(cy[i]),
                         float(ndvi[i]), float(lst[i]), int(n_obs[i]),
                         float(stqa[i]), float(ndbi[i]), float(elev[i]),
                         float(dist_coast[i])))
    grid = pd.DataFrame(rows, columns=[
        "cell_id", "year", "cx", "cy", "ndvi", "lst_c", "n_obs",
        "stqa_mean", "ndbi", "elev_m", "dist_coast_km"])
    grid.to_parquet(v1 / "grid_1km.parquet", index=False)
    print(f"wrote grid_1km.parquet: {len(grid)} rows")

    gdf.to_crs(32642).to_file(v1 / "boundary_32642.geojson", driver="GeoJSON")
    print("wrote boundary_32642.geojson")

    # --- 30 m GeoTIFF fixtures for a subset of years ---
    transform = from_origin(minx, maxy, PIX_M, PIX_M)
    width = int(np.ceil((maxx - minx) / PIX_M))
    height = int(np.ceil((maxy - miny) / PIX_M))
    print(f"raster size: {width} x {height}")
    land_geom_32642 = [land]
    for year in TIF_YEARS:
        ndvi, lst, ndbi, elev, dist_coast, n_obs, stqa, valid = per_year[year]
        # Rasterize the 1 km cell values, then smooth-upsample to 30 m.
        ny, nx = len(ys), len(xs)
        def cell_field(vals):
            arr = np.full((ny, nx), np.nan)
            arr.ravel()[keep] = vals
            return arr
        zf = (height / ny, width / nx)
        kw = dict(order=1, mode="nearest")
        f_ndvi = zoom(cell_field(ndvi), zf, **kw)[:height, :width]
        f_lst = zoom(cell_field(lst), zf, **kw)[:height, :width]
        f_nobs = zoom(cell_field(n_obs.astype(float)), zf, **kw)[:height, :width]
        f_stqa = zoom(cell_field(stqa), zf, **kw)[:height, :width]
        # Small per-pixel texture so overlays do not look flat.
        f_ndvi += rng.normal(0, 0.012, f_ndvi.shape)
        f_lst += rng.normal(0, 0.25, f_lst.shape)
        f_ndvi = np.clip(f_ndvi, *NDVI_RANGE).astype(np.float32)
        f_lst = np.clip(f_lst, *LST_RANGE).astype(np.float32)
        f_nobs = np.clip(np.rint(np.nan_to_num(f_nobs, nan=0.0)), 0, 255).astype(np.uint8)
        f_stqa = np.clip(f_stqa, 0, 10).astype(np.float32)

        water = rasterize(
            [(g, 0) for g in land_geom_32642],
            out_shape=(height, width), transform=transform,
            fill=1, dtype="uint8")  # 1 = water (outside land polygon)
        on_land = water == 0
        f_ndvi[~on_land] = np.nan
        f_lst[~on_land] = np.nan
        f_nobs[~on_land] = 0
        f_stqa[~on_land] = np.nan

        layers = {
            "ndvi": (f_ndvi, "float32", float("nan")),
            "lst_c": (f_lst, "float32", float("nan")),
            "n_obs": (f_nobs, "uint8", 0),
            "stqa": (f_stqa, "float32", float("nan")),
            "water": (water, "uint8", 255),
        }
        for lname, (arr, dtype, nodata) in layers.items():
            path = comp / f"{year}_{lname}.tif"
            with rasterio.open(
                path, "w", driver="GTiff", height=height, width=width,
                count=1, dtype=dtype, crs="EPSG:32642", transform=transform,
                nodata=nodata, compress="LZW", tiled=True,
            ) as dst:
                dst.write(arr, 1)
        print(f"wrote composites for {year}")

    # --- analysis_summary.json ---
    corr = []
    for year in usable_years:
        ndvi, lst, *_ = per_year[year]
        r = float(np.corrcoef(ndvi, lst)[0, 1])
        rho = float(pd.Series(ndvi).corr(pd.Series(lst), method="spearman"))
        n = int((per_year[year][-1]).sum())
        corr.append({
            "year": year, "n": n,
            "pearson_r": round(r, 3),
            "pearson_ci": [round(r - 0.03, 3), round(r + 0.03, 3)],
            "spearman_rho": round(rho, 3),
            "spearman_ci": [round(rho - 0.03, 3), round(rho + 0.03, 3)],
        })
    all_ndvi = np.concatenate([per_year[y][0] for y in usable_years])
    all_lst = np.concatenate([per_year[y][1] for y in usable_years])
    slope = float(np.polyfit(all_ndvi, all_lst, 1)[0])
    ss_res = float(((all_lst - (slope * all_ndvi + np.polyfit(all_ndvi, all_lst, 1)[1])) ** 2).sum())
    ss_tot = float(((all_lst - all_lst.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot
    summary = {
        "headline_finding": (
            "Across the 2015-2025 hot seasons, grid cells with less vegetation "
            "were consistently warmer, with a moderate negative NDVI-LST association "
            "in every usable year."
        ),
        "years": usable_years,
        "correlation": corr,
        "regression": {
            "ndvi_slope": round(slope, 2),
            "slope_ci": [round(slope - 1.8, 2), round(slope + 1.8, 2)],
            "r_squared": round(r2, 3),
            "n": int(sum(per_year[y][-1].sum() for y in usable_years)),
            "morans_i_residuals": 0.17,
            "vif": {"ndvi": 1.9, "ndbi": 2.1, "dist_coast_km": 1.3, "elev_m": 1.1},
        },
        "year_interaction_p": 0.31,
        "persistence": {
            "n_hot_lowveg_cells": 214,
            "years_overlap_observed": 96,
            "expected_chance": 11.5,
            "p_value": 0.0004,
        },
        "ml": {
            "included": False,
            "reason": (
                "Random Forest did not beat the linear baseline by the pre-stated "
                "5% RMSE margin on spatial blocks (2.1% improvement); reported as "
                "exploratory only, per protocol Section 15."
            ),
            "cv_rmse_rf": 2.31,
            "cv_rmse_linear": 2.36,
            "cv_mae_rf": 1.78,
            "cv_mae_linear": 1.81,
        },
        "scene_counts": {str(y): int(rng.integers(4, 13)) for y in usable_years},
        "coverage": {str(y): round(float(per_year[y][-1].mean()), 3) for y in usable_years},
    }
    (rep / "analysis_summary.json").write_text(json.dumps(summary, indent=2))
    print("wrote analysis_summary.json")

    # --- figures ---
    plt.rcParams.update({
        "figure.facecolor": "#FAF7F0", "axes.facecolor": "#FAF7F0",
        "text.color": "#22303A", "axes.labelcolor": "#22303A",
        "xtick.color": "#22303A", "ytick.color": "#22303A",
        "font.family": "sans-serif",
    })
    TEAL, HEAT, INK = "#2E7D6B", "#C0562F", "#22303A"

    fig, ax = plt.subplots(figsize=(8, 4.2))
    yrs = [c["year"] for c in corr]
    ax.errorbar(yrs,
                [c["pearson_r"] for c in corr],
                yerr=[[c["pearson_r"] - c["pearson_ci"][0] for c in corr],
                      [c["pearson_ci"][1] - c["pearson_r"] for c in corr]],
                fmt="o-", color=TEAL, ecolor=TEAL, capsize=3, label="Pearson r")
    ax.errorbar(yrs,
                [c["spearman_rho"] for c in corr],
                yerr=[[c["spearman_rho"] - c["spearman_ci"][0] for c in corr],
                      [c["spearman_ci"][1] - c["spearman_rho"] for c in corr]],
                fmt="s--", color=HEAT, ecolor=HEAT, capsize=3, label="Spearman rho")
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Correlation (NDVI vs LST)")
    ax.set_title("NDVI-LST correlation by hot season, 1 May to 30 June")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(figd / "correlation_timeseries.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.bar(["Observed overlap", "Expected by chance"],
           [summary["persistence"]["years_overlap_observed"],
            summary["persistence"]["expected_chance"]],
           color=[HEAT, "#B9C4C0"])
    ax.set_ylabel("Cells")
    ax.set_title("Hot and low-vegetation cells recurring across years")
    fig.tight_layout()
    fig.savefig(figd / "hotspot_persistence.png", dpi=120)
    plt.close(fig)

    for year in TIF_YEARS:
        sub = grid[grid["year"] == year]
        fig, ax = plt.subplots(figsize=(6, 5))
        hb = ax.hexbin(sub["ndvi"], sub["lst_c"], gridsize=40, cmap="YlOrRd",
                       mincnt=1)
        ax.set_xlabel("NDVI (unitless)")
        ax.set_ylabel("LST (degrees C)")
        ax.set_title(f"NDVI vs LST, hot season {year}")
        fig.colorbar(hb, ax=ax, label="cells")
        fig.tight_layout()
        fig.savefig(figd / f"ndvi_lst_scatter_{year}.png", dpi=110)
        plt.close(fig)
        for lname, col, cmap, lab in [
            ("lst", "lst_c", "YlOrRd", "LST (degrees C)"),
            ("ndvi", "ndvi", "YlGn", "NDVI (unitless)"),
        ]:
            fig, ax = plt.subplots(figsize=(5.5, 5.5))
            sc = ax.scatter(sub["cx"], sub["cy"], c=sub[col], s=4, cmap=cmap)
            ax.set_aspect("equal")
            ax.set_title(f"{lab}, hot season {year}")
            fig.colorbar(sc, ax=ax, label=lab)
            fig.tight_layout()
            fig.savefig(figd / f"{lname}_map_{year}.png", dpi=100)
            plt.close(fig)
    print("wrote figures")

    # --- manifest fixture ---
    manifest = {
        "run_id": "fixture_20261001",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_version": "1.0",
        "config_hash": "fixture-config-hash",
        "years": usable_years,
        "scenes": {
            str(y): [f"LC08_L1TP_fixture_{y}_{i:03d}" for i in range(summary["scene_counts"][str(y)])]
            for y in usable_years
        },
        "qa_rules": {
            "mask_bits": [0, 1, 2, 3, 4, 5],
            "require_clear_bit": 6,
            "cloud_distance_km": 1.0,
            "max_st_qa_kelvin": 2.0,
            "min_valid_observations": 2,
        },
        "software": {"python": "3.12", "rasterio": "1.5.2", "geopandas": "1.1.1"},
        "outputs": ["grid_1km.parquet", "composites/", "boundary_32642.geojson"],
        "note": "Synthetic fixture manifest for dashboard testing only. Not real observations.",
    }
    (mand / "run_fixture_20261001.json").write_text(json.dumps(manifest, indent=2))
    print("wrote manifest fixture")
    print("done:", root)


if __name__ == "__main__":
    main()
