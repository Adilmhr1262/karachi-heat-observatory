"""Write manifests/run_<timestamp>.json for a processing run.

Records: config hash + full config, scene IDs and acquisition dates per
year, QA rules applied, software versions, output paths, run timestamps,
and the water-mask investigation findings.
"""
import datetime
import importlib
import json
import sys

from src.common import ROOT, load_config, config_hash


def package_versions():
    mods = ["python", "rasterio", "numpy", "pandas", "scipy", "sklearn",
            "pyarrow", "planetary_computer", "pystac_client", "yaml",
            "matplotlib", "shapely", "geopandas", "esda", "statsmodels"]
    out = {}
    for m in mods:
        if m == "python":
            out[m] = sys.version.split()[0]
            continue
        try:
            mod = importlib.import_module(m)
            out[m] = getattr(mod, "__version__", "installed")
        except Exception:  # noqa: BLE001
            out[m] = "missing"
    return out


def main():
    cfg = load_config()
    now = datetime.datetime.now(datetime.timezone.utc)
    scenes = {}
    for year in range(cfg["period"]["start_year"], cfg["period"]["end_year"] + 1):
        p = ROOT / "data" / "interim" / "scene_lists" / f"{year}.json"
        diag_p = ROOT / "data" / "interim" / "dates" / str(year) / f"_diag_{year}.json"
        items = json.load(open(p)) if p.exists() else []
        scenes[str(year)] = [
            {"id": d["id"],
             "datetime": d["properties"]["datetime"],
             "platform": d["properties"].get("platform"),
             "wrs_path": d["properties"].get("landsat:wrs_path"),
             "wrs_row": d["properties"].get("landsat:wrs_row"),
             "cloud_cover": d["properties"].get("eo:cloud_cover")}
            for d in items
        ]
        if diag_p.exists():
            d = json.load(open(diag_p))
            scenes[str(year) + "_diagnostics"] = {
                "n_items": d["n_items"], "n_dates": d["n_dates"],
                "n_dates_used": d.get("n_dates_used"),
                "skipped_dates": d.get("skipped_dates", []),
                "qa_screen_totals": d["qa_screen_totals"],
                "composite": d["composite"],
            }
    grid_meta = {}
    gm = ROOT / "data" / "processed" / "v1" / "_grid_meta.json"
    if gm.exists():
        grid_meta = json.load(open(gm))
    sensor_check = {}
    sc = ROOT / "data" / "interim" / "sensor_check" / "sensor_check_2022.json"
    if sc.exists():
        sensor_check = json.load(open(sc))
    manifest = {
        "study": cfg["study"]["name"],
        "protocol_version": cfg["study"]["protocol_version"],
        "run_utc": now.isoformat(),
        "config_sha16": config_hash(cfg),
        "config": cfg,
        "qa_rules": cfg["qa"],
        "selection_filters": {
            "platforms": ["landsat-8", "landsat-9"],
            "landsat9_from": cfg["sensors"]["use_landsat9_from"],
            "collection_category": cfg["selection"]["collection_category"],
            "processing_level": cfg["selection"]["processing_level"],
            "max_scene_cloud_cover_pct": cfg["selection"]["max_scene_cloud_cover_pct"],
            "window": f"{cfg['period']['window_start']}..{cfg['period']['window_end']}",
        },
        "scenes": scenes,
        "grid": grid_meta,
        "sensor_check_2022": sensor_check,
        "outputs": {
            "composites": "data/processed/v1/composites/{year}_{ndvi,lst_c,n_obs,stqa,water}.tif",
            "grid": "data/processed/v1/grid_1km.parquet",
            "boundary_32642": "data/processed/v1/boundary_32642.geojson",
            "analysis_summary": "reports/analysis_summary.json",
            "figures": "reports/figures/*.png",
        },
        "package_versions": package_versions(),
        "data_access": cfg["data_access"],
    }
    out = ROOT / "manifests" / f"run_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    with open(out, "w") as f:
        json.dump(manifest, f, indent=2)
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
