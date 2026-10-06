"""Folium maps rendered from local GeoTIFF composites.

Every map is built from files on disk; no remote reads. Rasters are
downsampled before display, masked values stay transparent, and the legend
carries numeric ticks with units so color is never the only encoding.
"""

import base64
import io

import folium
import numpy as np
import rasterio
import streamlit as st
from matplotlib import cm
from matplotlib.colors import LinearSegmentedColormap
from rasterio.warp import transform_bounds

from styles import HEAT, INK, MUTED, PAPER, RULE, TEAL

# Display ranges are fixed so years stay comparable.
LAYER_DEFS = {
    "lst_c": {
        "label": "Land surface temperature",
        "unit": "degrees C",
        "vmin": 30.0,
        "vmax": 58.0,
        "colors": ["#F6EFDD", "#EFC98F", "#E08A4C", HEAT],
    },
    "ndvi": {
        "label": "Vegetation (NDVI)",
        "unit": "unitless",
        "vmin": -0.2,
        "vmax": 0.6,
        "colors": ["#E4DFC8", "#9DBEA4", TEAL, "#173F34"],
    },
    "n_obs": {
        "label": "Observation count",
        "unit": "scenes",
        "vmin": 0,
        "vmax": 8,
        "colors": ["#EDE9DC", "#B9CFC2", TEAL],
    },
}


def _cmap(colors):
    return LinearSegmentedColormap.from_list("obs", colors)


@st.cache_data(show_spinner=False)
def render_overlay(tif_path, layer, max_px=900):
    """Read a GeoTIFF, downsample, colorize. Returns dict or None on failure."""
    tif_path = str(tif_path)
    spec = LAYER_DEFS[layer]
    try:
        with rasterio.open(tif_path) as src:
            scale = max(1, int(max(src.height, src.width) / max_px))
            arr = src.read(
                1,
                out_shape=(max(1, src.height // scale), max(1, src.width // scale)),
                resampling=rasterio.enums.Resampling.bilinear,
            ).astype("float64")
            bounds_4326 = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    except Exception:
        return None

    if layer == "n_obs":
        valid = arr > 0
    else:
        valid = np.isfinite(arr)
    norm = np.clip((arr - spec["vmin"]) / (spec["vmax"] - spec["vmin"]), 0, 1)
    rgba = _cmap(spec["colors"])(norm)
    rgba[~valid, 3] = 0.0  # missing stays transparent, never zero-filled

    buf = io.BytesIO()
    # flip vertically: folium ImageOverlay expects [south, west] to [north, east]
    from PIL import Image

    Image.fromarray((rgba[::-1] * 255).astype("uint8")).save(buf, format="PNG")
    return {
        "png": buf.getvalue(),
        "bounds": [[bounds_4326[1], bounds_4326[0]], [bounds_4326[3], bounds_4326[2]]],
        "spec": spec,
    }


def legend_html(layer, year_label):
    """HTML legend with a rendered colorbar image, ticks, and units."""
    spec = LAYER_DEFS[layer]
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(0.55, 2.2), dpi=100)
    fig.patch.set_alpha(0.0)
    ax.set_axis_off()
    gradient = np.linspace(spec["vmax"], spec["vmin"], 128).reshape(128, 1)
    ax.imshow(gradient, aspect="auto", cmap=_cmap(spec["colors"]),
              extent=[0, 1, spec["vmin"], spec["vmax"]])
    ticks = [spec["vmax"], (spec["vmax"] + spec["vmin"]) / 2, spec["vmin"]]
    for t in ticks:
        ax.text(1.15, t, f"{t:g}", va="center", ha="left",
                fontsize=9, color=INK, transform=ax.transData)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", transparent=True)
    plt.close(fig)
    img = base64.b64encode(buf.getvalue()).decode()

    return f"""
    <div class="map-legend">
      <div class="legend-title">{spec["label"]}, {year_label}</div>
      <img src="data:image/png;base64,{img}" alt="color scale">
      <div class="legend-unit">unit: {spec["unit"]}; fixed scale across years</div>
    </div>
    """


def build_map(overlay, boundary_4326, legend):
    """Folium map with the raster overlay and a thin boundary outline."""
    (s, w), (n, e) = overlay["bounds"]
    m = folium.Map(
        location=[(s + n) / 2, (w + e) / 2],
        zoom_start=10,
        tiles="OpenStreetMap",  # keyless; CartoDB now needs an API key
        control_scale=True,
    )
    folium.raster_layers.ImageOverlay(
        image="data:image/png;base64," + base64.b64encode(overlay["png"]).decode(),
        bounds=overlay["bounds"],
        opacity=0.85,
        name=overlay["spec"]["label"],
    ).add_to(m)
    if boundary_4326 is not None:
        folium.GeoJson(
            boundary_4326.__geo_interface__,
            style_function=lambda f: {
                "color": INK, "weight": 1.5, "fillOpacity": 0,
            },
            name="Karachi Division boundary",
        ).add_to(m)
    m.fit_bounds(overlay["bounds"])
    m.get_root().html.add_child(folium.Element(
        f'<div style="position:absolute;bottom:28px;right:12px;z-index:9999;">{legend}</div>'
    ))
    return m


def boundary_to_4326(boundary_32642):
    try:
        return boundary_32642.to_crs(4326)
    except Exception:
        return None
