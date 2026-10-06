# Observatory dashboard

Streamlit app for the Karachi Urban Heat and Green Cover Observatory.
Reads versioned pipeline outputs only (see `docs/DATA_CONTRACT.md`); it never
recomputes analysis.

## Run (real data)

From the project root:

```bash
.venv/bin/streamlit run src/app/app.py
```

The app reads, relative to the project root:

- `data/processed/v1/` (grid parquet, composites, boundary GeoJSON)
- `reports/` (`analysis_summary.json`, `figures/`)
- `manifests/` (`run_*.json`)
- `config/study.yaml` (processing decisions shown on the Methods page)

Missing contract files produce a plain message naming the file, never a traceback.

## Run against synthetic fixtures

`src/app/make_fixtures.py` is a test helper, not part of the app. It writes a
contract-shaped fixture tree under `data/fixtures/` (kept out of
`data/processed/` so it never collides with real pipeline outputs):

```bash
.venv/bin/python src/app/make_fixtures.py
KHO_DATA_ROOT=$PWD/data/fixtures/v1 \
KHO_REPORTS_ROOT=$PWD/data/fixtures/reports \
KHO_MANIFESTS_ROOT=$PWD/data/fixtures/manifests \
.venv/bin/streamlit run src/app/app.py
```

Fixtures use plausible ranges (NDVI -0.2 to 0.6, LST 30 to 58 C, 11 seasons,
about 3,500 grid cells) and deliberately leave 2020 without usable scenes, so
the "no usable scenes" states can be tested. GeoTIFF fixtures are written for
2019, 2021, and 2023 only; other usable years exercise the missing-file path.

## Layout

- `app.py`: pages (Overview, Map studio, Compare, Methods and data, Research notes)
- `data_loader.py`: contract readers with graceful missing-file handling
- `maps.py`: folium maps from local GeoTIFFs (downsampled PNG overlays)
- `charts.py`: matplotlib charts in the editorial theme
- `content.py`: static workflow, limitations, and source text
- `styles.py`: warm-paper theme, serif titles, teal + one heat accent
