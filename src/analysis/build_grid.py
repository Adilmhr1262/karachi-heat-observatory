"""Build the 1 km analysis grid dataset (contract: grid_1km.parquet).

One row per 1 km cell per year meeting the observation threshold.
Cells below threshold are absent, not zero-filled.

Columns: cell_id, year, cx, cy, ndvi, lst_c, n_obs, stqa_mean,
         ndbi, elev_m, dist_coast_km

Usage: python -m src.analysis.build_grid
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from scipy.ndimage import distance_transform_edt

from src.common import (
    ROOT, load_config, load_boundary_32642,
    GRID_SHAPE, GRID_TRANSFORM, GRID_CRS, CELL_M,
)
from src.acquisition.reader import sign_item

COMP = ROOT / "data" / "processed" / "v1" / "composites"
OUT = ROOT / "data" / "processed" / "v1" / "grid_1km.parquet"

MIN_VALID_PIXELS = 100  # min 30 m land pixels inside a 1 km cell-year
GRID_ORIGIN_X = 262830.0
GRID_ORIGIN_Y_TOP = 2838150.0


def land_mask():
    """Authoritative land mask: rasterized GADM boundary on the 30 m grid."""
    g = load_boundary_32642()
    shapes = [(geom, 1) for geom in g.geometry]
    mask = rasterize(shapes, out_shape=GRID_SHAPE, transform=GRID_TRANSFORM,
                     fill=0, dtype=np.uint8)
    return mask.astype(bool)


def cell_index_grids():
    H, W = GRID_SHAPE
    rows = np.arange(H)[:, None]
    cols = np.arange(W)[None, :]
    # 1 km cells aligned to the 30 m grid origin
    y_m = GRID_ORIGIN_Y_TOP - (rows + 0.5) * 30.0
    x_m = GRID_ORIGIN_X + (cols + 0.5) * 30.0
    ix = ((x_m - GRID_ORIGIN_X) // 1000).astype(np.int64)
    iy = ((GRID_ORIGIN_Y_TOP - y_m) // 1000).astype(np.int64)
    return ix, iy, x_m, y_m


def dist_to_coast_km(years):
    """Distance transform from the union of annual permanent-water masks."""
    H, W = GRID_SHAPE
    water_union = np.zeros((H, W), dtype=bool)
    for year in years:
        p = COMP / f"{year}_water.tif"
        if not p.exists():
            continue
        with rasterio.open(p) as src:
            water_union |= src.read(1).astype(bool)
    n_water = int(water_union.sum())
    print(f"  permanent-water pixels (union, all years): {n_water}", flush=True)
    if n_water == 0:
        return None, n_water
    # distance from each pixel to nearest water pixel, in km
    dist_px = distance_transform_edt(~water_union)
    return (dist_px * 30.0 / 1000.0).astype(np.float32), n_water


def read_dem():
    """Copernicus DEM GLO-30 via Planetary Computer, reprojected to the grid."""
    from src.acquisition.reader import read_asset_grid
    from rasterio.enums import Resampling
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    search = catalog.search(
        collections=["cop-dem-glo-30"],
        bbox=[66.6532, 24.7476, 67.5769, 25.6521],
        limit=10,
    )
    items = [planetary_computer.sign(it.to_dict()) for it in search.items()]
    if not items:
        raise RuntimeError("no cop-dem-glo-30 items found")
    H, W = GRID_SHAPE
    acc = np.zeros((H, W), dtype=np.float64)
    cnt = np.zeros((H, W), dtype=np.float64)
    for it in items:
        href = it["assets"]["data"]["href"]
        nodata = (it["assets"]["data"].get("raster:bands") or [{}])[0].get("nodata")
        arr, _ = read_asset_grid(href, nodata, Resampling.bilinear)
        ok = np.isfinite(arr)
        acc[ok] += arr[ok]
        cnt[ok] += 1
    dem = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan).astype(np.float32)
    return dem


def main():
    cfg = load_config()
    years = [int(p.stem.split("_")[0]) for p in sorted(COMP.glob("*_ndvi.tif"))]
    print("years with composites:", years, flush=True)

    land = land_mask()
    print(f"  land pixels on 30 m grid: {int(land.sum())} "
          f"({int(land.sum()) * 900 / 1e6:.0f} km2)", flush=True)
    ix, iy, x_m, y_m = cell_index_grids()
    cell_key = ix.astype(np.int64) * 100000 + iy.astype(np.int64)

    dist_coast, n_water = dist_to_coast_km(years)

    try:
        dem = read_dem()
        dem_ok = True
        print(f"  DEM read ok, range {np.nanmin(dem):.1f}..{np.nanmax(dem):.1f} m", flush=True)
    except Exception as e:  # noqa: BLE001 - DEM is optional per contract
        print(f"  DEM FAILED ({e}); elev_m will be null", flush=True)
        dem = None
        dem_ok = False

    rows_out = []
    min_obs = cfg["composite"]["min_valid_observations"]
    for year in years:
        with rasterio.open(COMP / f"{year}_ndvi.tif") as s:
            ndvi_a = s.read(1)
        with rasterio.open(COMP / f"{year}_lst_c.tif") as s:
            lstc_a = s.read(1)
        with rasterio.open(COMP / f"{year}_ndbi.tif") as s:
            ndbi_a = s.read(1)
        with rasterio.open(COMP / f"{year}_n_obs.tif") as s:
            nobs_a = s.read(1)
        with rasterio.open(COMP / f"{year}_stqa.tif") as s:
            stqa_a = s.read(1)
        with rasterio.open(COMP / f"{year}_water.tif") as s:
            water_a = s.read(1).astype(bool)
        pix_ok = land & ~water_a & np.isfinite(ndvi_a) & np.isfinite(lstc_a)
        if not pix_ok.any():
            print(f"  {year}: no valid pixels, skipped", flush=True)
            continue
        df = pd.DataFrame({
            "cell": cell_key[pix_ok],
            "ndvi": ndvi_a[pix_ok],
            "lst_c": lstc_a[pix_ok],
            "ndbi": ndbi_a[pix_ok],
            "n_obs": nobs_a[pix_ok].astype(np.float32),
            "stqa": stqa_a[pix_ok],
        })
        if dist_coast is not None:
            df["dist_coast_km"] = dist_coast[pix_ok]
        if dem_ok:
            df["elev_m"] = dem[pix_ok]
        g = df.groupby("cell")
        n_pix = g.size()
        keep = n_pix[n_pix >= MIN_VALID_PIXELS].index
        if len(keep) == 0:
            print(f"  {year}: no cells pass the pixel-count threshold", flush=True)
            continue
        agg = g.agg(ndvi=("ndvi", "median"), lst_c=("lst_c", "median"),
                    ndbi=("ndbi", "median"), n_obs=("n_obs", "median"),
                    stqa_mean=("stqa", "mean"))
        if dist_coast is not None:
            agg["dist_coast_km"] = g["dist_coast_km"].median()
        if dem_ok:
            agg["elev_m"] = g["elev_m"].median()
        agg = agg.loc[keep]
        agg = agg[agg["n_obs"] >= min_obs]  # min valid observations rule
        cell_ids = agg.index.to_numpy()
        # centroid of cell key: recover ix, iy
        ix_c = (cell_ids // 100000).astype(float)
        iy_c = (cell_ids % 100000).astype(float)
        cx = GRID_ORIGIN_X + (ix_c + 0.5) * 1000.0
        cy = GRID_ORIGIN_Y_TOP - (iy_c + 0.5) * 1000.0
        cell_str = [f"c{int(a):04d}_{int(b):04d}" for a, b in zip(ix_c, iy_c)]
        out = pd.DataFrame({
            "cell_id": cell_str,
            "year": year,
            "cx": cx,
            "cy": cy,
            "ndvi": agg["ndvi"].to_numpy(dtype=np.float64),
            "lst_c": agg["lst_c"].to_numpy(dtype=np.float64),
            "n_obs": agg["n_obs"].to_numpy(dtype=np.float64).round().astype(int),
            "stqa_mean": agg["stqa_mean"].to_numpy(dtype=np.float64),
            "ndbi": agg["ndbi"].to_numpy(dtype=np.float64),
        })
        out["elev_m"] = (agg["elev_m"].to_numpy(dtype=np.float64)
                         if dem_ok else np.nan)
        out["dist_coast_km"] = (agg["dist_coast_km"].to_numpy(dtype=np.float64)
                                if dist_coast is not None else np.nan)
        # sanity filters (contract ranges)
        out = out[(out["ndvi"] >= -1) & (out["ndvi"] <= 1)]
        out = out[(out["lst_c"] >= 0) & (out["lst_c"] <= 75)]
        rows_out.append(out)
        print(f"  {year}: {len(out)} cells", flush=True)

    grid = pd.concat(rows_out, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    grid.to_parquet(OUT, index=False)
    print(f"wrote {OUT} with {len(grid)} rows", flush=True)
    # total 1 km cells intersecting land (for the coverage denominator)
    n_land_cells = int(pd.Series(cell_key[land]).nunique())
    meta = {"years": years, "n_land_cells": n_land_cells,
            "n_water_union_px": n_water, "dem_ok": dem_ok,
            "min_valid_pixels": MIN_VALID_PIXELS,
            "min_valid_observations": min_obs}
    with open(OUT.parent / "_grid_meta.json", "w") as f:
        json.dump(meta, f, indent=2)


if __name__ == "__main__":
    main()
