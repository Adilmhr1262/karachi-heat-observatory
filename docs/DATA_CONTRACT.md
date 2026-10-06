# Data contract between the processing/analysis pipeline and the dashboard

Version: v1. All paths relative to the project root `karachi-heat-observatory/`.
The dashboard MUST read only these versioned outputs; it never recomputes.

## Grid dataset

`data/processed/v1/grid_1km.parquet`
One row per 1 km grid cell per year (2015-2025) that meets the minimum
valid-observation threshold. Cells below the threshold are absent (not zero-filled).

Columns:
- cell_id: string, e.g. "c1234_5678" (stable across years)
- year: int
- cx, cy: float — cell centroid in EPSG:32642 (meters)
- ndvi: float — median composite NDVI
- lst_c: float — median composite LST in degrees Celsius
- n_obs: int — valid scene-level observations behind the composite
- stqa_mean: float — mean ST_QA (Kelvin) over contributing pixels
- ndbi: float — median composite NDBI (may be null if not produced)
- elev_m: float — elevation in meters (may be null)
- dist_coast_km: float — distance to permanent water in km (may be null)

## Annual composites (30 m, EPSG:32642, LZW GeoTIFF)

`data/processed/v1/composites/{year}_ndvi.tif`      — float32, nodata NaN
`data/processed/v1/composites/{year}_lst_c.tif`      — float32 Celsius, nodata NaN
`data/processed/v1/composites/{year}_n_obs.tif`      — uint8 valid-observation count
`data/processed/v1/composites/{year}_stqa.tif`       — float32 mean ST_QA (Kelvin)
`data/processed/v1/composites/{year}_water.tif`      — uint8 permanent-water mask (1=water)

`data/processed/v1/boundary_32642.geojson` — Karachi Division boundary in EPSG:32642.

## Analysis results

`reports/analysis_summary.json` with keys:
- years: list of years with usable composites
- correlation: list of {year, n, pearson_r, pearson_ci, spearman_rho, spearman_ci}
- regression: {ndvi_slope, slope_ci, r_squared, n, morans_i_residuals, vif}
- year_interaction_p: float or null
- persistence: {n_hot_lowveg_cells, years_overlap_observed, expected_chance, p_value} or null
- ml: {included: bool, reason: string, cv_rmse_rf, cv_rmse_linear, cv_mae_rf, cv_mae_linear} 
- scene_counts: {year: number of scenes used}
- coverage: {year: share of land cells meeting the observation threshold}

`reports/figures/` — PNG files:
- `ndvi_lst_scatter_{year}.png`, `lst_map_{year}.png`, `ndvi_map_{year}.png`
- `correlation_timeseries.png`, `hotspot_persistence.png`

## Manifests

`manifests/run_*.json` — config hash, scene IDs + acquisition dates per year,
QA rules, software versions, output paths, run timestamps.

## Conventions

- Missing data is NaN/null, never 0 and never silently filled.
- Every map or chart in the dashboard shows: units, year/window, source
  ("USGS Landsat Collection 2 Level-2 via Planetary Computer STAC"),
  and the coverage share for that year.
- No health, exposure, or causal claims anywhere in the UI.
