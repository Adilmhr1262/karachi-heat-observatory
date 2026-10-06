"""Read-only access to versioned pipeline outputs.

Follows docs/DATA_CONTRACT.md exactly. The dashboard never recomputes
analysis; it only reads the files the pipeline wrote. Every loader returns
(value, error): value is None and error names the missing file when a
contract file is absent, so pages can show a clear message instead of a
traceback.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_LINE = "USGS Landsat Collection 2 Level-2 via Planetary Computer STAC"
WINDOW_LABEL = "1 May to 30 June (pre-monsoon hot season)"
ALL_YEARS = list(range(2015, 2026))
VERSION_LABEL = "v1"


@dataclass(frozen=True)
class Roots:
    data: Path       # versioned outputs, e.g. data/processed/v1
    reports: Path    # e.g. reports
    manifests: Path  # e.g. manifests


def resolve_roots() -> Roots:
    data = Path(os.environ.get("KHO_DATA_ROOT", PROJECT_ROOT / "data" / "processed" / "v1"))
    reports = Path(os.environ.get("KHO_REPORTS_ROOT", PROJECT_ROOT / "reports"))
    manifests = Path(os.environ.get("KHO_MANIFESTS_ROOT", PROJECT_ROOT / "manifests"))
    return Roots(data=data, reports=reports, manifests=manifests)


@st.cache_data(show_spinner=False)
def load_grid(_roots: Roots):
    path = _roots.data / "grid_1km.parquet"
    if not path.exists():
        return None, f"Grid dataset not found: {path}"
    try:
        import pandas as pd

        df = pd.read_parquet(path)
        return df, None
    except Exception as exc:  # keep the page alive; name the file
        return None, f"Could not read {path}: {exc}"


@st.cache_data(show_spinner=False)
def load_summary(_roots: Roots):
    path = _roots.reports / "analysis_summary.json"
    if not path.exists():
        return None, f"Analysis summary not found: {path}"
    try:
        return json.loads(path.read_text()), None
    except Exception as exc:
        return None, f"Could not read {path}: {exc}"


@st.cache_data(show_spinner=False)
def load_manifest(_roots: Roots):
    runs = sorted(_roots.manifests.glob("run_*.json"), key=lambda p: p.stat().st_mtime)
    if not runs:
        return None, None, f"No run manifest found in {_roots.manifests}"
    path = runs[-1]
    try:
        return json.loads(path.read_text()), path.name, None
    except Exception as exc:
        return None, path.name, f"Could not read {path}: {exc}"


@st.cache_data(show_spinner=False)
def load_boundary(_roots: Roots):
    path = _roots.data / "boundary_32642.geojson"
    if not path.exists():
        return None, f"Boundary file not found: {path}"
    try:
        import geopandas as gpd

        gdf = gpd.read_file(path)
        if gdf.crs is None or gdf.crs.to_epsg() != 32642:
            gdf = gdf.to_crs(32642)
        return gdf, None
    except Exception as exc:
        return None, f"Could not read {path}: {exc}"


@st.cache_data(show_spinner=False)
def load_config():
    path = PROJECT_ROOT / "config" / "study.yaml"
    if not path.exists():
        return None, f"Study config not found: {path}"
    try:
        import yaml

        return yaml.safe_load(path.read_text()), None
    except Exception as exc:
        return None, f"Could not read {path}: {exc}"


def composite_tif(roots: Roots, year: int, layer: str):
    """Local path of a composite GeoTIFF, or None if absent."""
    path = roots.data / "composites" / f"{year}_{layer}.tif"
    return path if path.exists() else None


def figure_png(roots: Roots, name: str):
    path = roots.reports / "figures" / name
    return path if path.exists() else None


def usable_years(summary):
    if summary and isinstance(summary.get("years"), list):
        return [int(y) for y in summary["years"]]
    return []


def year_has_composite(roots: Roots, year: int) -> bool:
    return composite_tif(roots, year, "lst_c") is not None


def coverage_share(summary, year: int):
    if not summary:
        return None
    cov = summary.get("coverage") or {}
    val = cov.get(str(year), cov.get(year))
    return float(val) if val is not None else None


def scene_count(summary, year: int):
    if not summary:
        return None
    sc = summary.get("scene_counts") or {}
    val = sc.get(str(year), sc.get(year))
    return int(val) if val is not None else None


def coverage_sentence(summary, year: int) -> str:
    cov = coverage_share(summary, year)
    if cov is None:
        return "coverage not reported for this year"
    return f"coverage {cov:.1%} of land cells met the observation threshold"
