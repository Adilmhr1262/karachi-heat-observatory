"""Signed, windowed, reprojected reads of Planetary Computer assets.

Each item dict is signed with planetary_computer.sign() immediately before
reading (SAS tokens expire). Assets are reprojected on the fly into the
common 30 m EPSG:32642 grid (src/common.py) so every scene aligns.
"""
import numpy as np
import planetary_computer
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.windows import Window, transform as window_transform

from src.common import GRID_CRS, GRID_SHAPE, GRID_TRANSFORM


def sign_item(item_dict):
    """Sign an item dict, forcing fresh SAS tokens.

    Scene lists saved by stac_query carry query-time signed hrefs (the
    search client uses sign_inplace). Those tokens expire, and sign()
    does not refresh an already-signed href, so strip any query string
    first to guarantee a fresh token for this read.
    """
    import copy
    from urllib.parse import urlsplit, urlunsplit
    item = copy.deepcopy(item_dict)
    for asset in item.get("assets", {}).values():
        href = asset.get("href") or ""
        if "?" in href:
            p = urlsplit(href)
            asset["href"] = urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    return planetary_computer.sign(item)


def asset_meta(signed_item, name):
    """(href, scale, offset, nodata) from the STAC raster:bands metadata."""
    a = signed_item["assets"][name]
    bands = (a.get("raster:bands") or [{}])[0]
    return a["href"], bands.get("scale"), bands.get("offset"), bands.get("nodata")


def read_asset_grid(href, nodata, resampling, window=None):
    """Read an asset reprojected into the common grid (or a grid window).

    window: rasterio Window in grid pixels, or None for the full grid.
    Returns (array float32 with NaN for nodata, transform of the read).
    """
    h, w = GRID_SHAPE
    tr = GRID_TRANSFORM
    if window is not None:
        w = int(window.width)
        h = int(window.height)
        tr = window_transform(window, GRID_TRANSFORM)
    out = np.full((h, w), np.nan, dtype=np.float32)
    with rasterio.Env(GDAL_NUM_THREADS="ALL_CPUS"):
        with rasterio.open(href) as src:
            reproject(
                rasterio.band(src, 1),
                out,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=nodata,
                dst_transform=tr,
                dst_crs=GRID_CRS,
                dst_nodata=np.nan,
                resampling=resampling,
            )
    return out, tr


def grid_windows(chunk_rows=512):
    """Yield rasterio Windows tiling the grid in row chunks (memory control)."""
    h, w = GRID_SHAPE
    for r0 in range(0, h, chunk_rows):
        yield Window(0, r0, w, min(chunk_rows, h - r0))
