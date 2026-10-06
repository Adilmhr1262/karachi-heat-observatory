---
title: Karachi Urban Heat Observatory
emoji: "\U0001F30D"
colorFrom: green
colorTo: blue
sdk: streamlit
sdk_version: 1.64.0
app_file: src/app/app.py
pinned: false
---

# Karachi Urban Heat & Green Cover Observatory

An observational study of the association between vegetation condition (NDVI) and
land surface temperature (LST) in Karachi Division, Pakistan, across the hot
seasons of 2015-2025, using USGS Landsat Collection 2 Level-2 products.

## Status

Built end-to-end from the Master Research Protocol v1.0 (Deliverable 1).
The protocol document is at `~/workspace/your_files/Karachi Urban Heat and Green Cover Observatory - Master Research Protocol v1.0.docx`.

## Layout

- `config/study.yaml` - all study parameters; every run records its hash
- `src/acquisition/` - scene discovery via Planetary Computer STAC
- `src/processing/` - QA masking, scaling, NDVI/LST, compositing
- `src/analysis/` - grid summaries, statistics, machine-learning comparison
- `src/app/` - Streamlit dashboard (reads versioned outputs only)
- `data/boundaries/` - Karachi Division boundary + source note
- `data/processed/` - versioned analysis outputs
- `manifests/` - machine-readable run manifests
- `tests/` - unit tests (scaling, NDVI, QA bitmask logic)
- `reports/` - figures and the final report

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export CURL_CA_BUNDLE=/run/hatch/egress-tls/ca-bundle.pem
export GDAL_CURL_CA_BUNDLE=/run/hatch/egress-tls/ca-bundle.pem
PYTHONPATH=. .venv/bin/python -m src.acquisition.stac_query  # scene inventory
PYTHONPATH=. .venv/bin/python -m src.processing.process_years # annual composites
PYTHONPATH=. .venv/bin/python -m src.analysis.build_grid      # 1 km grid summaries
PYTHONPATH=. .venv/bin/python -m src.analysis.analyze         # stats, figures, summary
.venv/bin/python -m pytest tests/ -q                          # unit tests
.venv/bin/streamlit run src/app/app.py                        # dashboard
```

## Data

USGS Landsat Collection 2 Level-2 (Landsat 8: 2015-2025, Landsat 9: 2022-2025),
accessed through the Microsoft Planetary Computer STAC API, which serves the
same USGS archive files. Public domain with USGS acknowledgment. See the
protocol for the authorized source list and the access-route amendment note.

## Reproducibility

Each run writes a manifest under `manifests/` recording the config hash,
scene IDs, acquisition dates, QA rules, software versions, and output paths.
Re-running a fixed config reproduces the outputs within documented tolerance.
