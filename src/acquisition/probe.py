#!/usr/bin/env python3
"""Probe the Planetary Computer STAC collection for landsat-c2-l2.

Prints one item's id, key properties, asset keys, and raster:bands
metadata for the assets we plan to read. Read-only; no downloads.
"""
import os
os.environ.setdefault("CURL_CA_BUNDLE", "/run/hatch/egress-tls/ca-bundle.pem")
os.environ.setdefault("GDAL_CURL_CA_BUNDLE", "/run/hatch/egress-tls/ca-bundle.pem")

import json
import planetary_computer
import pystac_client

BBOX = [66.6532, 24.7476, 67.5769, 25.6521]  # Karachi Division, EPSG:4326

catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)
search = catalog.search(
    collections=["landsat-c2-l2"],
    bbox=BBOX,
    datetime="2024-05-01/2024-06-30",
    query={"eo:cloud_cover": {"lt": 20}},
    limit=50,
)
items = list(search.items())
print("n items:", len(items))
for it in items[:12]:
    props = it.properties
    print(
        it.id,
        "| platform:", props.get("platform"),
        "| cat:", props.get("landsat:collection_category"),
        "| cloud:", props.get("eo:cloud_cover"),
        "| sun_el:", props.get("view:sun_elevation"),
    )

# Inspect the first landsat-8 L2SP T1 item in detail
pick = None
for it in items:
    if it.id.startswith("LC08") and "L2SP" in it.id:
        pick = it
        break
if pick is None:
    pick = items[0]
print("\nPicked:", pick.id)
print("Assets:", sorted(pick.assets.keys()))
for name in ["red", "nir08", "swir16", "lwir11", "qa_pixel", "qa", "cdist"]:
    a = pick.assets.get(name)
    if a is None:
        print(f"  {name}: MISSING")
        continue
    eb = (a.extra_fields.get("raster:bands") or [{}])[0]
    print(f"  {name}: scale={eb.get('scale')} offset={eb.get('offset')} nodata={eb.get('nodata')}")
    print(f"    title={a.title!r} desc={(a.description or '')[:90]!r}")
print("\nAll properties keys:", sorted(pick.properties.keys()))
