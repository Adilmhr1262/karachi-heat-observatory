LITE TEST VERSION - Karachi Urban Heat Observatory
================================================

This is a lightweight test copy. Everything works, but to keep the download
small it includes the full 30 m map rasters for 2024 and 2025 only.

- Overview, Compare, Methods, Research notes: full data (all years).
- Map studio: interactive 30 m maps for 2024 and 2025. Other years show the
  pre-rendered PNG map figures (still the real results).

The full 729 MB package (all 11 years of 30 m rasters) is in your
Google Drive > Projects folder.

Run it the same way (see RUN-ON-MAC.txt):
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  .venv/bin/streamlit run src/app/app.py
