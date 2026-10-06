"""Shared configuration, grid definition, and paths for the observatory pipeline."""
import hashlib
import json
import os
from pathlib import Path

import geopandas as gpd
import yaml
from rasterio.transform import from_origin

ROOT = Path("/home/hatch/workspace/karachi-heat-observatory")

# Egress proxy CA bundle: required for every remote raster read.
os.environ.setdefault("CURL_CA_BUNDLE", "/run/hatch/egress-tls/ca-bundle.pem")
os.environ.setdefault("GDAL_CURL_CA_BUNDLE", "/run/hatch/egress-tls/ca-bundle.pem")
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "120")


def load_config(path=ROOT / "config" / "study.yaml"):
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return cfg


def config_hash(cfg):
    blob = json.dumps(cfg, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def load_boundary_32642():
    g = gpd.read_file(ROOT / "data/boundaries/karachi-division-gadm41.geojson")
    return g.to_crs("EPSG:32642")


# Common 30 m analysis grid in EPSG:32642, fixed for every year and scene.
# Derived from the boundary bbox: origin snapped to the 30 m grid.
_GRID_ORIGIN_X = 262830.0
_GRID_ORIGIN_Y = 2838150.0  # top edge
_GRID_W = 3112
_GRID_H = 3327
_GRID_RES = 30.0
GRID_TRANSFORM = from_origin(_GRID_ORIGIN_X, _GRID_ORIGIN_Y, _GRID_RES, _GRID_RES)
GRID_CRS = "EPSG:32642"
GRID_SHAPE = (_GRID_H, _GRID_W)


def grid_bbox():
    """(minx, miny, maxx, maxy) of the common grid in EPSG:32642."""
    return (
        _GRID_ORIGIN_X,
        _GRID_ORIGIN_Y - _GRID_RES * _GRID_H,
        _GRID_ORIGIN_X + _GRID_RES * _GRID_W,
        _GRID_ORIGIN_Y,
    )


# 1 km analysis grid: 1000 m cells aligned to the same origin.
CELL_M = 1000
