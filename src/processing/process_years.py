"""Annual processing: per-date mosaics -> per-year median composites.

Reads signed Landsat C2 L2 assets, applies QA masking and the ST_CDIST /
ST_QA screens, derives NDVI / LST_C / NDBI per scene, mosaics same-date
tiles, then builds annual median composites with observation counts.

Outputs (contract docs/DATA_CONTRACT.md):
  data/interim/dates/{year}/{date}_{ndvi,lstc,ndbi,stqa,valid,water,observed}.tif
  data/processed/v1/composites/{year}_{ndvi,lst_c,n_obs,stqa,water}.tif

Usage: python -m src.processing.process_years [year ...]  (default: all)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from src.common import ROOT, load_config, GRID_SHAPE, GRID_TRANSFORM, GRID_CRS
from src.acquisition.reader import sign_item, asset_meta, grid_windows
from src.processing.masks import qa_mask, screen_stats
from src.processing.indices import ndvi, ndbi, lst_celsius, apply_sr_scaling

ASSETS = ["red", "nir08", "swir16", "lwir11", "qa_pixel", "qa", "cdist"]
INTERIM_VARS = ["ndvi", "lstc", "ndbi", "stqa", "valid", "water", "observed"]


def write_tif(path, arr, dtype=None, nodata=None, compress="LZW"):
    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": dtype or arr.dtype,
        "crs": GRID_CRS,
        "transform": GRID_TRANSFORM,
        "compress": compress,
    }
    if arr.dtype == np.float32:
        profile["nodata"] = np.nan
        profile["predictor"] = 3
    else:
        profile["nodata"] = nodata if nodata is not None else 0
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def process_date(cfg, date, items, interim_dir):
    """Mosaic one acquisition date's items into per-date interim files."""
    qa_cfg = cfg["qa"]
    out_paths = {v: interim_dir / f"{date}_{v}.tif" for v in INTERIM_VARS}
    if all(p.exists() for p in out_paths.values()):
        return out_paths, None  # resume

    H, W = GRID_SHAPE
    sum_f = {v: np.zeros((H, W), dtype=np.float64) for v in ["ndvi", "lstc", "ndbi", "stqa"]}
    cnt_f = np.zeros((H, W), dtype=np.float32)
    sum_c = {v: np.zeros((H, W), dtype=np.uint16) for v in ["valid", "water", "observed"]}
    n_items = 0
    diag = defaultdict(float)
    for item in items:
        signed = sign_item(item)
        try:
            per_item = _read_item(signed, qa_cfg)
        except Exception as e:  # noqa: BLE001 - record and continue
            print(f"    READ FAILED {item['id']}: {e}", flush=True)
            continue
        n_items += 1
        for k, v in per_item["diag"].items():
            diag[k] += v
        for v in ["ndvi", "lstc", "ndbi", "stqa"]:
            a = per_item[v]
            ok = ~np.isnan(a)
            sum_f[v][ok] += a[ok]
        cnt_f += (~np.isnan(per_item["ndvi"])).astype(np.float32)
        for v in ["valid", "water", "observed"]:
            sum_c[v] = np.clip(sum_c[v] + per_item[v].astype(np.uint16), 0, 255)
        del per_item
    if n_items == 0:
        raise RuntimeError(f"no readable items for date {date}")

    # Mosaic across same-date tiles: nanmean of index values; sums of counts.
    mosaic = {}
    with np.errstate(invalid="ignore"):
        for v in ["ndvi", "lstc", "ndbi", "stqa"]:
            mosaic[v] = np.where(cnt_f > 0, sum_f[v] / np.maximum(cnt_f, 1),
                                np.nan).astype(np.float32)
        for v in ["valid", "water", "observed"]:
            mosaic[v] = sum_c[v].astype(np.uint8)
    for v, p in out_paths.items():
        write_tif(p, mosaic[v])
    return out_paths, dict(diag)


def _read_item(signed, qa_cfg):
    """Read one item's assets into masked per-scene arrays (full grid).

    Each asset is fetched with a single reproject call into the common
    grid; intermediates are freed as soon as they are consumed.
    """
    hrefs = {}
    metas = {}
    for name in ASSETS:
        href, scale, offset, nodata = asset_meta(signed, name)
        hrefs[name] = href
        metas[name] = (scale, offset, nodata)

    H, W = GRID_SHAPE
    diag = defaultdict(float)

    s_scale, s_offset, _ = metas["red"]
    n_scale, n_offset, _ = metas["nir08"]
    w_scale, w_offset, _ = metas["swir16"]
    t_scale, t_offset, _ = metas["lwir11"]

    with rasterio.Env(GDAL_NUM_THREADS="ALL_CPUS"):
        srcs = {name: rasterio.open(hrefs[name]) for name in ASSETS}
        try:
            raw = {}
            for name in ASSETS:
                _, _, nodata = metas[name]
                rs = Resampling.nearest if name == "qa_pixel" else Resampling.bilinear
                arr = np.full((H, W), np.nan, dtype=np.float32)
                reproject(
                    rasterio.band(srcs[name], 1), arr,
                    src_transform=srcs[name].transform, src_crs=srcs[name].crs,
                    src_nodata=nodata,
                    dst_transform=GRID_TRANSFORM,
                    dst_crs=GRID_CRS, dst_nodata=np.nan, resampling=rs,
                )
                raw[name] = arr
        finally:
            for s in srcs.values():
                s.close()

    qa = raw.pop("qa_pixel")
    cdist = raw.pop("cdist")
    stqa_raw = raw.pop("qa")
    has_qa = np.isfinite(qa)
    cdist_km = np.where(np.isfinite(cdist), cdist * 0.01, np.nan)
    del cdist
    stqa_k = np.where(np.isfinite(stqa_raw), stqa_raw * 0.01, np.nan)
    del stqa_raw
    qa_filled = np.where(has_qa, qa, 0).astype(np.int32)
    del qa

    valid, water = qa_mask(qa_filled, cdist_km, stqa_k,
                          qa_cfg["cloud_distance_km"], qa_cfg["max_st_qa_kelvin"])
    valid = valid & has_qa
    water = water & has_qa
    del has_qa
    observed = (valid | water).astype(np.uint8)

    for k, v in screen_stats(qa_filled, cdist_km, stqa_k,
                            qa_cfg["cloud_distance_km"],
                            qa_cfg["max_st_qa_kelvin"]).items():
        diag[k] += v
    del qa_filled

    # Scale optical + thermal (metadata-driven)
    red = apply_sr_scaling(raw.pop("red"), s_scale, s_offset)
    nir = apply_sr_scaling(raw.pop("nir08"), n_scale, n_offset)
    swir = apply_sr_scaling(raw.pop("swir16"), w_scale, w_offset)
    lwir = raw.pop("lwir11")

    nd = ndvi(nir, red, valid)
    del red
    lb = ndbi(swir, nir, valid)
    del nir, swir
    lc = lst_celsius(lwir, valid, t_scale, t_offset)
    del lwir
    stqa = np.where(valid, stqa_k, np.nan).astype(np.float32)
    del stqa_k

    return {"ndvi": nd, "lstc": lc, "ndbi": lb, "stqa": stqa,
            "valid": valid.astype(np.uint8), "water": water.astype(np.uint8),
            "observed": observed, "diag": dict(diag)}


def annual_composite(cfg, year, date_paths, comp_dir):
    """Build the annual median composite from per-date interim files."""
    outs = {
        "ndvi": comp_dir / f"{year}_ndvi.tif",
        "ndbi": comp_dir / f"{year}_ndbi.tif",
        "lst_c": comp_dir / f"{year}_lst_c.tif",
        "n_obs": comp_dir / f"{year}_n_obs.tif",
        "stqa": comp_dir / f"{year}_stqa.tif",
        "water": comp_dir / f"{year}_water.tif",
    }
    if all(p.exists() for p in outs.values()):
        return outs, None

    H, W = GRID_SHAPE
    dates = sorted(date_paths.keys())
    n_dates = len(dates)
    if n_dates == 0:
        # D15: a year with no usable scenes is reported as missing, not crashed.
        return outs, {"n_dates": 0, "valid_pixel_frac": 0.0,
                      "water_pixel_frac": 0.0, "missing": True,
                      "reason": "no readable dates"}

    # Chunked nanmedian: process row chunks, stacking dates in memory per chunk.
    ndvi_out = np.full((H, W), np.nan, dtype=np.float32)
    lstc_out = np.full((H, W), np.nan, dtype=np.float32)
    ndbi_out = np.full((H, W), np.nan, dtype=np.float32)
    stqa_out = np.full((H, W), np.nan, dtype=np.float32)
    nobs_out = np.zeros((H, W), dtype=np.uint8)
    water_out = np.zeros((H, W), dtype=np.uint8)

    for window in grid_windows(chunk_rows=1024):
        sl = (slice(int(window.row_off), int(window.row_off + int(window.height))),
              slice(int(window.col_off), int(window.col_off + int(window.width))))
        stacks = {v: [] for v in ["ndvi", "lstc", "ndbi", "stqa", "valid", "water", "observed"]}
        for date in dates:
            paths = date_paths[date]
            for v in stacks:
                with rasterio.open(paths[v]) as src:
                    stacks[v].append(src.read(1, window=window))
        with np.errstate(invalid="ignore"):
            ndvi_out[sl] = np.nanmedian(np.stack(stacks["ndvi"]).astype(np.float32), axis=0)
            lstc_out[sl] = np.nanmedian(np.stack(stacks["lstc"]).astype(np.float32), axis=0)
            ndbi_out[sl] = np.nanmedian(np.stack(stacks["ndbi"]).astype(np.float32), axis=0)
            stqa_out[sl] = np.nanmean(np.stack(stacks["stqa"]).astype(np.float32), axis=0)
        nobs_out[sl] = np.clip(np.stack(stacks["valid"]).sum(axis=0), 0, 255).astype(np.uint8)
        wsum = np.stack(stacks["water"]).sum(axis=0)
        osum = np.stack(stacks["observed"]).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            wfrac = np.where(osum >= 2, wsum / np.maximum(osum, 1), 0)
        water_out[sl] = (wfrac >= 0.5).astype(np.uint8)

    write_tif(outs["ndvi"], ndvi_out)
    write_tif(outs["ndbi"], ndbi_out)
    write_tif(outs["lst_c"], lstc_out)
    write_tif(outs["n_obs"], nobs_out)
    write_tif(outs["stqa"], stqa_out)
    write_tif(outs["water"], water_out)
    diag = {"n_dates": n_dates,
            "valid_pixel_frac": float(np.sum(nobs_out > 0) / nobs_out.size),
            "water_pixel_frac": float(np.sum(water_out > 0) / water_out.size)}
    return outs, diag


def process_year(cfg, year):
    print(f"=== {year} ===", flush=True)
    with open(ROOT / "data" / "interim" / "scene_lists" / f"{year}.json") as f:
        items = json.load(f)
    by_date = defaultdict(list)
    for d in items:
        by_date[d["properties"]["datetime"][:10]].append(d)
    interim_dir = ROOT / "data" / "interim" / "dates" / str(year)
    interim_dir.mkdir(parents=True, exist_ok=True)
    comp_dir = ROOT / "data" / "processed" / "v1" / "composites"
    comp_dir.mkdir(parents=True, exist_ok=True)

    date_paths = {}
    all_diag = defaultdict(float)
    meta_items = []
    skipped_dates = []
    for date in sorted(by_date):
        try:
            paths, diag = process_date(cfg, date, by_date[date], interim_dir)
        except Exception as e:  # noqa: BLE001 - one bad date must not kill the year
            print(f"  SKIPPED DATE {date}: {e}", flush=True)
            skipped_dates.append({"date": date, "reason": str(e)})
            continue
        date_paths[date] = paths
        if diag:
            for k, v in diag.items():
                all_diag[k] += v
        for d in by_date[date]:
            p = d["properties"]
            meta_items.append({
                "id": d["id"],
                "datetime": p["datetime"],
                "platform": p.get("platform"),
                "wrs_path": p.get("landsat:wrs_path"),
                "wrs_row": p.get("landsat:wrs_row"),
                "cloud_cover": p.get("eo:cloud_cover"),
                "sun_elevation": p.get("view:sun_elevation"),
            })
    outs, cdiag = annual_composite(cfg, year, date_paths, comp_dir)
    if cdiag is None:
        cdiag = {"n_dates": len(date_paths), "valid_pixel_frac": float("nan"),
                 "water_pixel_frac": float("nan"), "resumed": True}
    year_diag = {"n_items": len(items), "n_dates": len(by_date),
                 "n_dates_used": len(date_paths), "skipped_dates": skipped_dates,
                 "qa_screen_totals": dict(all_diag), "composite": cdiag,
                 "items": meta_items}
    with open(interim_dir / f"_diag_{year}.json", "w") as f:
        json.dump(year_diag, f, indent=2)
    print(f"  items={len(items)} dates={len(by_date)} "
          f"valid_frac={cdiag['valid_pixel_frac']:.3f} water_frac={cdiag['water_pixel_frac']:.4f}",
          flush=True)
    return year_diag


def main():
    cfg = load_config()
    years = [int(a) for a in sys.argv[1:]] or list(
        range(cfg["period"]["start_year"], cfg["period"]["end_year"] + 1))
    for year in years:
        process_year(cfg, year)


if __name__ == "__main__":
    main()
