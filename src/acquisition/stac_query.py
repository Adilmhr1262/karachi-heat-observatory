"""STAC query + hard filters for Landsat Collection 2 Level-2 scenes.

Writes data/interim/scene_lists/{year}.json with the full item dicts that
pass every filter. Signing happens at read time (reader.py), never here.
"""
import json
from pathlib import Path

import planetary_computer
import pystac_client

from src.common import ROOT, load_config

ALLOWED_PLATFORMS = {"landsat-8", "landsat-9"}


def query_year(cfg, year, bbox4326):
    catalog = pystac_client.Client.open(
        cfg["data_access"]["stac_api"],
        modifier=planetary_computer.sign_inplace,
    )
    search = catalog.search(
        collections=[cfg["data_access"]["collection"]],
        bbox=bbox4326,
        datetime=f"{year}-05-01/{year}-06-30",
        query={"eo:cloud_cover": {"lt": cfg["selection"]["max_scene_cloud_cover_pct"]}},
        limit=200,
    )
    items = list(search.items())
    kept = []
    for it in items:
        d = it.to_dict()
        p = d["properties"]
        pid = d["id"]
        platform = p.get("platform")
        # HARD FILTERS (protocol Section 11; task spec)
        if platform not in ALLOWED_PLATFORMS:
            continue  # excludes landsat-7 and anything else
        if platform == "landsat-9" and year < cfg["sensors"]["use_landsat9_from"]:
            continue
        if "L2SP" not in pid:
            continue
        if p.get("landsat:collection_category") != cfg["selection"]["collection_category"]:
            continue
        if cfg["selection"]["require_daytime"]:
            sun_el = p.get("view:sun_elevation")
            if sun_el is None or sun_el <= 0:
                continue
        kept.append(d)
    kept.sort(key=lambda d: d["properties"]["datetime"])
    return kept


def main():
    cfg = load_config()
    import geopandas as gpd

    g = gpd.read_file(ROOT / "data/boundaries/karachi-division-gadm41.geojson")
    bbox4326 = list(g.total_bounds)  # minx, miny, maxx, maxy
    outdir = ROOT / "data" / "interim" / "scene_lists"
    outdir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for year in range(cfg["period"]["start_year"], cfg["period"]["end_year"] + 1):
        kept = query_year(cfg, year, bbox4326)
        with open(outdir / f"{year}.json", "w") as f:
            json.dump(kept, f)
        plats = {}
        for d in kept:
            pl = d["properties"]["platform"]
            plats[pl] = plats.get(pl, 0) + 1
        dates = sorted({d["properties"]["datetime"][:10] for d in kept})
        summary[year] = {"n_items": len(kept), "platforms": plats, "n_dates": len(dates)}
        print(year, summary[year], flush=True)
    with open(outdir / "_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
