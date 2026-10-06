"""Karachi Urban Heat and Green Cover Observatory: research dashboard.

Reads versioned pipeline outputs only (docs/DATA_CONTRACT.md). Never
recomputes analysis. Missing contract files produce a plain message naming
the file, never a traceback.
"""

import streamlit as st
from streamlit_folium import st_folium

import charts
import content
import data_loader as dl
import maps
from styles import HEAT, caption, inject_styles, rule

st.set_page_config(
    page_title="Karachi Urban Heat and Green Cover Observatory",
    page_icon=":world_map:",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_styles()
roots = dl.resolve_roots()


# ---------- shared pieces ----------

def header():
    st.markdown(
        '<p class="obs-kicker">Field note / Environmental systems</p>'
        '<h1 class="obs-title">Karachi: Urban Heat and Green Cover Observatory</h1>'
        '<p class="obs-subtitle">A reproducible Landsat study of vegetation and '
        "land surface temperature, 2015 to 2025</p>",
        unsafe_allow_html=True,
    )
    rule()


def sidebar_status():
    st.sidebar.markdown("### Versioned outputs")
    grid, grid_err = dl.load_grid(roots)
    summary, sum_err = dl.load_summary(roots)
    manifest, mname, man_err = dl.load_manifest(roots)
    lines = []
    lines.append(f"Data root: `{roots.data}`")
    lines.append("Grid dataset: found" if grid is not None else f"Grid dataset: missing ({grid_err})")
    lines.append("Analysis summary: found" if summary is not None else f"Analysis summary: missing ({sum_err})")
    if summary:
        n_tif = sum(1 for y in dl.usable_years(summary) if dl.year_has_composite(roots, y))
        lines.append(f"Composites on disk: {n_tif} year(s)")
    lines.append(f"Run manifest: {mname}" if manifest else f"Run manifest: missing ({man_err})")
    for ln in lines:
        st.sidebar.caption(ln)
    return grid, summary, manifest, mname


def year_selector(label, usable, key):
    def fmt(y):
        return str(y) if y in usable else f"{y} (no usable scenes)"

    default = dl.ALL_YEARS.index(usable[-1]) if usable else 0
    return st.selectbox(label, dl.ALL_YEARS, index=default, format_func=fmt, key=key)


def layer_radio(key):
    def fmt(layer):
        return maps.LAYER_DEFS[layer]["label"]

    return st.radio("Layer", ["lst_c", "ndvi", "n_obs"], format_func=fmt,
                    key=key, horizontal=True)


def map_caption(layer, year, summary):
    spec = maps.LAYER_DEFS[layer]
    caption(
        f"{spec['label']}, hot season {year} ({dl.WINDOW_LABEL}). "
        f"Unit: {spec['unit']}. Source: {dl.SOURCE_LINE}. "
        f"{dl.coverage_sentence(summary, year)}."
    )


def render_year_map(year, layer, summary, boundary_4326, height=620, key="map"):
    """Map from GeoTIFF overlay, else figure PNG, else a plain no-data note."""
    tif = dl.composite_tif(roots, year, layer)
    if tif is not None:
        overlay = maps.render_overlay(tif, layer)
        if overlay is not None:
            try:
                m = maps.build_map(overlay, boundary_4326,
                                   maps.legend_html(layer, str(year)))
                st_folium(m, height=height, use_container_width=True, key=key)
                map_caption(layer, year, summary)
                return
            except Exception:
                st.error("The map could not be rendered from the composite file.")
                return
    fallback = {"lst_c": "lst", "ndvi": "ndvi"}.get(layer)
    if fallback is not None:
        fig = dl.figure_png(roots, f"{fallback}_map_{year}.png")
        if fig is not None:
            st.image(str(fig))
            map_caption(layer, year, summary)
            return
    st.info(
        f"No composite file found for {year} at the expected path under the data "
        "root. The year has usable scenes in the summary, but the raster was not "
        "written or not copied here. Missing files are shown as missing, never as zeros."
    )


# ---------- pages ----------

def page_overview(grid, summary):
    st.markdown("## Overview")
    finding = summary.get("headline_finding") if summary else None
    if finding:
        st.markdown(f'<p class="obs-finding">{finding}</p>', unsafe_allow_html=True)
    elif summary is None:
        st.info(
            "Analysis outputs are not available yet, so this page describes the "
            "study design. No finding is stated until the analysis summary exists."
        )

    st.markdown("### Study facts")
    facts = [
        ("Study period", "2015 to 2025, annual hot seasons"),
        ("Study area", "Karachi Division, Sindh, Pakistan (3,527 km2)"),
        ("Seasonal window", dl.WINDOW_LABEL),
        ("Sensors", "Landsat 8 (2015 onward); Landsat 9 (2022 onward)"),
        ("Analysis unit", "1 km grid cells (statistics); 30 m rasters (maps)"),
        ("Outputs version", dl.VERSION_LABEL),
    ]
    for label, value in facts:
        st.markdown(f'<p class="obs-fact"><b>{label}.</b> {value}</p>', unsafe_allow_html=True)
    rule()

    if summary is None:
        st.info("Coverage and scene counts will appear here once the pipeline writes its summary.")
        return

    usable = dl.usable_years(summary)
    missing = [y for y in dl.ALL_YEARS if y not in usable]
    if missing:
        st.info(
            "No usable scenes for: " + ", ".join(str(y) for y in missing) +
            ". Those years are excluded from every chart and map."
        )

    st.markdown("### Coverage by year")
    fig = charts.fig_coverage(summary)
    if fig is not None:
        st.pyplot(fig)
        caption(
            "Share of land grid cells meeting the minimum observation threshold per "
            f"hot season. Source: {dl.SOURCE_LINE}."
        )
    rule()
    st.markdown("### Scenes used per year")
    fig = charts.fig_scene_counts(summary)
    if fig is not None:
        st.pyplot(fig)
        caption(
            "Landsat scenes admitted to each annual composite after Tier 1, L2SP, "
            f"daytime, and cloud-cover screening. Source: {dl.SOURCE_LINE}."
        )


def page_map_studio(grid, summary, boundary_4326):
    st.markdown("## Map studio")
    usable = dl.usable_years(summary) if summary else []
    year = year_selector("Hot season", usable, key="ms_year")
    layer = layer_radio(key="ms_layer")
    if year not in usable:
        st.info(
            f"No usable scenes for {year}: no scenes met the QA rules, so there is "
            "nothing to map. This year is shown as missing, never as zeros."
        )
        return
    render_year_map(year, layer, summary, boundary_4326, height=620, key="ms_map")


def page_compare(grid, summary, boundary_4326):
    st.markdown("## Compare")
    usable = dl.usable_years(summary) if summary else []
    if not usable:
        st.info("Comparison needs usable years in the analysis summary.")
        return
    year = year_selector("Hot season", usable, key="cmp_year")
    if year not in usable:
        st.info(f"No usable scenes for {year}.")
        return

    st.markdown("### Side by side")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Vegetation (NDVI)")
        render_year_map(year, "ndvi", summary, boundary_4326, height=430, key="cmp_ndvi")
    with c2:
        st.markdown("#### Land surface temperature")
        render_year_map(year, "lst_c", summary, boundary_4326, height=430, key="cmp_lst")
    rule()

    st.markdown("### Distributions")
    if grid is not None:
        sub = grid[grid["year"] == year]
        fig = charts.fig_distributions(sub, year)
        if fig is not None:
            st.pyplot(fig)
            caption(
                f"Distributions across 1 km grid cells, hot season {year}. "
                f"n = {len(sub)} cells. Source: {dl.SOURCE_LINE}."
            )
    rule()

    st.markdown("### NDVI vs LST")
    if grid is not None:
        sub = grid[grid["year"] == year]
        fig = charts.fig_scatter(sub, year)
        if fig is not None:
            st.pyplot(fig)
            caption(
                f"Each point is a 1 km grid cell, hot season {year} "
                f"({dl.WINDOW_LABEL}). n = {len(sub)} cells. "
                f"Source: {dl.SOURCE_LINE}."
            )
    rule()

    st.markdown("### Correlation trend")
    if summary is not None:
        fig = charts.fig_correlation_timeseries(summary)
        if fig is not None:
            st.pyplot(fig)
            caption(
                "Pearson r and Spearman rho between NDVI and LST per hot season, "
                "with 95% confidence intervals. "
                f"Source: {dl.SOURCE_LINE}."
            )
    if summary is not None and summary.get("persistence"):
        st.markdown("### Hotspot persistence")
        fig = charts.fig_persistence(summary)
        if fig is not None:
            st.pyplot(fig)
            p = summary["persistence"]
            caption(
                f"Grid cells in the top LST decile and bottom NDVI decile recurring "
                f"across years: {p['years_overlap_observed']} observed vs "
                f"{p['expected_chance']} expected by chance "
                f"(p = {p['p_value']}). Source: {dl.SOURCE_LINE}."
            )


def page_methods(summary, manifest, mname):
    st.markdown("## Methods and data")
    st.markdown("### Workflow")
    for title, text in content.WORKFLOW_STEPS:
        st.markdown(f'<p class="obs-fact"><b>{title}.</b> {text}</p>', unsafe_allow_html=True)
    rule()

    st.markdown("### Processing decisions")
    config, config_err = dl.load_config()
    if config is None:
        st.info(config_err)
    else:
        rows = [
            ("Seasonal window", f"{config['period']['window_start']} to {config['period']['window_end']}"),
            ("Study years", f"{config['period']['start_year']} to {config['period']['end_year']}"),
            ("Landsat 9 from", str(config["sensors"]["use_landsat9_from"])),
            ("Scene cloud-cover limit", f"{config['selection']['max_scene_cloud_cover_pct']}%"),
            ("Processing level", config["selection"]["processing_level"]),
            ("Cloud-distance screen", f"{config['qa']['cloud_distance_km']} km"),
            ("ST_QA limit", f"{config['qa']['max_st_qa_kelvin']} K"),
            ("Min observations per cell", str(config["composite"]["min_valid_observations"])),
            ("Grid resolution", f"{config['grid']['resolution_m']} m"),
            ("Imagery source", f"{config['data_access']['stac_api']} ({config['data_access']['collection']})"),
        ]
        html = ['<table class="obs-table">']
        for label, value in rows:
            html.append(f"<tr><td><b>{label}</b></td><td>{value}</td></tr>")
        html.append("</table>")
        st.markdown("\n".join(html), unsafe_allow_html=True)
        caption("Values above are read from config/study.yaml, the same file the pipeline records in its manifest.")
    rule()

    st.markdown("### Quality rules")
    for item in content.QA_RULES:
        st.markdown(f"- {item}")
    rule()

    st.markdown("### Sources")
    for label, url in content.SOURCE_LINKS:
        st.markdown(f"- [{label}]({url})")
    rule()

    st.markdown("### Limitations")
    for item in content.LIMITATIONS:
        st.markdown(f"- {item}")
    rule()

    st.markdown("### Run identifier")
    if manifest is None:
        st.info("No run manifest found yet. The pipeline writes one per run.")
    else:
        st.markdown(f'<p class="obs-fact"><b>Run.</b> {mname}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="obs-fact"><b>Run ID.</b> {manifest.get("run_id", "not recorded")}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="obs-fact"><b>Created.</b> {manifest.get("created_utc", "not recorded")}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="obs-fact"><b>Config hash.</b> {manifest.get("config_hash", "not recorded")}</p>', unsafe_allow_html=True)


def page_notes(grid, summary):
    st.markdown("## Research notes")
    if summary is None:
        st.info("Findings will appear here once the pipeline writes its analysis summary.")
        return

    st.markdown("### Correlation by year")
    corr = summary.get("correlation") or []
    if corr:
        html = ['<table class="obs-table"><tr><th>Year</th><th>Cells</th>'
                "<th>Pearson r [95% CI]</th><th>Spearman rho [95% CI]</th></tr>"]
        for c in corr:
            pr, prci = c["pearson_r"], c["pearson_ci"]
            sr, srci = c["spearman_rho"], c["spearman_ci"]
            html.append(
                f"<tr><td>{c['year']}</td><td>{c['n']}</td>"
                f"<td>{pr} [{prci[0]}, {prci[1]}]</td>"
                f"<td>{sr} [{srci[0]}, {srci[1]}]</td></tr>"
            )
        html.append("</table>")
        st.markdown("\n".join(html), unsafe_allow_html=True)
        caption(
            "NDVI-LST association per 1 km grid cell, hot season "
            f"({dl.WINDOW_LABEL}). Source: {dl.SOURCE_LINE}."
        )
    rule()

    st.markdown("### Regression")
    reg = summary.get("regression") or {}
    if reg:
        ci = reg.get("slope_ci") or [None, None]
        for label, value in [
            ("NDVI slope", f"{reg.get('ndvi_slope')} C per NDVI unit "
             f"[{ci[0]}, {ci[1]}]"),
            ("R squared", reg.get("r_squared")),
            ("Cells", reg.get("n")),
            ("Moran's I on residuals", reg.get("morans_i_residuals")),
        ]:
            st.markdown(f'<p class="obs-fact"><b>{label}.</b> {value}</p>', unsafe_allow_html=True)
        p = summary.get("year_interaction_p")
        if p is not None:
            st.markdown(f'<p class="obs-fact"><b>Year interaction p.</b> {p} '
                        "(tests whether the NDVI slope differs by year)</p>", unsafe_allow_html=True)
    rule()

    st.markdown("### Machine learning comparison")
    ml = summary.get("ml") or {}
    if ml:
        st.markdown(f'<p class="obs-fact"><b>In main conclusions.</b> '
                    f"{'Yes' if ml.get('included') else 'No'}</p>", unsafe_allow_html=True)
        st.markdown(f'<p class="obs-fact"><b>Reason.</b> {ml.get("reason", "")}</p>', unsafe_allow_html=True)
        html = ['<table class="obs-table"><tr><th>Model</th><th>CV RMSE</th><th>CV MAE</th></tr>']
        html.append(f"<tr><td>Random Forest</td><td>{ml.get('cv_rmse_rf')}</td><td>{ml.get('cv_mae_rf')}</td></tr>")
        html.append(f"<tr><td>Linear baseline</td><td>{ml.get('cv_rmse_linear')}</td><td>{ml.get('cv_mae_linear')}</td></tr>")
        html.append("</table>")
        st.markdown("\n".join(html), unsafe_allow_html=True)
        caption("Spatial block cross-validation on 1 km grid cells. Lower is better.")
    rule()

    st.markdown("### Uncertainty")
    st.markdown(content.UNCERTAINTY_TEXT)
    rule()

    st.markdown("### Downloads")
    st.markdown(f"Versioned outputs, version {dl.VERSION_LABEL}.")
    d1, d2, d3 = st.columns(3)
    with d1:
        p = roots.data / "grid_1km.parquet"
        if p.exists():
            st.download_button("Grid dataset (Parquet, v1)", p.read_bytes(),
                               file_name="kho_grid_1km_v1.parquet")
        else:
            st.caption(f"Not available: {p}")
    with d2:
        p = roots.data / "boundary_32642.geojson"
        if p.exists():
            st.download_button("Boundary (GeoJSON, v1)", p.read_bytes(),
                               file_name="kho_boundary_32642_v1.geojson")
        else:
            st.caption(f"Not available: {p}")
    with d3:
        p = roots.reports / "analysis_summary.json"
        if p.exists():
            st.download_button("Analysis summary (JSON, v1)", p.read_bytes(),
                               file_name="kho_analysis_summary_v1.json")
        else:
            st.caption(f"Not available: {p}")


# ---------- run ----------

header()

PAGES = ["Overview", "Map studio", "Compare", "Methods and data", "Research notes"]
page = st.sidebar.radio("Sections", PAGES, label_visibility="collapsed")

grid, summary, manifest, mname = sidebar_status()
boundary, _ = dl.load_boundary(roots)
boundary_4326 = maps.boundary_to_4326(boundary) if boundary is not None else None

if page == "Overview":
    page_overview(grid, summary)
elif page == "Map studio":
    page_map_studio(grid, summary, boundary_4326)
elif page == "Compare":
    page_compare(grid, summary, boundary_4326)
elif page == "Methods and data":
    page_methods(summary, manifest, mname)
else:
    page_notes(grid, summary)

rule()
caption(
    "Karachi Urban Heat and Green Cover Observatory. Satellite data: "
    f"{dl.SOURCE_LINE}. Boundary: GADM 4.1, Karachi Division. "
    "Design: Master Research Protocol v1.0."
)
