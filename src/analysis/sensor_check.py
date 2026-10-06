"""D12 cross-sensor check: Landsat 8 vs Landsat 9 composites for 2022.

Builds separate L8-only and L9-only May-June 2022 composites from the
per-date interim files (dates assigned by majority platform), then compares
NDVI and LST over cells valid in both. A material systematic offset is
reported so the analysis can include sensor as a model factor.

Writes data/interim/sensor_check/2022_{L8,L9}_{ndvi,lstc}.tif and prints
the comparison. Read-only with respect to the main products.
"""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio

from src.common import ROOT, GRID_SHAPE
from src.processing.process_years import write_tif

OUTDIR = ROOT / "data" / "interim" / "sensor_check"


def composite_for_dates(dates, interim_dir, tag):
    """Median composite over a subset of dates; writes interim tifs."""
    H, W = GRID_SHAPE
    paths = {}
    for var in ["ndvi", "lstc", "valid"]:
        stacks = []
        for date in dates:
            p = interim_dir / f"{date}_{var}.tif"
            with rasterio.open(p) as src:
                stacks.append(src.read(1))
        stacks = np.stack(stacks).astype(np.float32)
        if var == "valid":
            paths[var] = np.clip(np.nansum(stacks, axis=0), 0, 255).astype(np.uint8)
        else:
            with np.errstate(invalid="ignore"):
                paths[var] = np.nanmedian(stacks, axis=0).astype(np.float32)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for var in ["ndvi", "lstc"]:
        write_tif(OUTDIR / f"2022_{tag}_{var}.tif", paths[var])
    return paths


def main():
    with open(ROOT / "data" / "interim" / "scene_lists" / "2022.json") as f:
        items = json.load(f)
    interim_dir = ROOT / "data" / "interim" / "dates" / "2022"
    by_date = defaultdict(list)
    for d in items:
        by_date[d["properties"]["datetime"][:10]].append(
            d["properties"]["platform"])
    l8_dates = sorted(dt for dt, ps in by_date.items()
                      if sum(p == "landsat-8" for p in ps) >= sum(p == "landsat-9" for p in ps)
                      and (interim_dir / f"{dt}_ndvi.tif").exists())
    l9_dates = sorted(dt for dt, ps in by_date.items()
                      if sum(p == "landsat-9" for p in ps) > sum(p == "landsat-8" for p in ps)
                      and (interim_dir / f"{dt}_ndvi.tif").exists())
    print(f"L8 dates ({len(l8_dates)}): {l8_dates}", flush=True)
    print(f"L9 dates ({len(l9_dates)}): {l9_dates}", flush=True)
    if not l8_dates or not l9_dates:
        print("insufficient dates for a sensor comparison", flush=True)
        return
    c8 = composite_for_dates(l8_dates, interim_dir, "L8")
    c9 = composite_for_dates(l9_dates, interim_dir, "L9")
    common = (c8["valid"] > 0) & (c9["valid"] > 0)
    print(f"common valid pixels: {int(common.sum())}", flush=True)
    for var, unit in [("ndvi", ""), ("lstc", "C")]:
        a, b = c8[var][common], c9[var][common]
        d = b - a  # L9 minus L8
        print(f"{var}: L9-L8 mean={np.mean(d):.4f}{unit} "
              f"median={np.median(d):.4f}{unit} std={np.std(d):.4f}{unit} "
              f"n={d.size}", flush=True)
    result = {
        "l8_dates": l8_dates, "l9_dates": l9_dates,
        "common_valid_pixels": int(common.sum()),
        "ndvi_l9_minus_l8_mean": float(np.mean(c9["ndvi"][common] - c8["ndvi"][common])),
        "lst_l9_minus_l8_mean_c": float(np.mean(c9["lstc"][common] - c8["lstc"][common])),
    }
    with open(OUTDIR / "sensor_check_2022.json", "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
