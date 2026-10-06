"""Static editorial text for the Methods and Research notes pages.

Plain-language descriptions of the workflow, limits, and sources. These
describe the study design from the protocol; they state no results.
"""

WORKFLOW_STEPS = [
    ("1. Select scenes",
     "For each hot season (1 May to 30 June), list Tier 1 Landsat 8 and 9 "
     "Collection 2 Level-2 scenes intersecting Karachi Division, keep daytime "
     "acquisitions processed to surface temperature (L2SP), and drop scenes "
     "with more than 20 percent cloud cover."),
    ("2. Mask poor-quality pixels",
     "Apply the official QA_PIXEL mask: keep clear pixels only, remove fill, "
     "cloud, dilated cloud, cirrus, and cloud shadow. Water pixels are kept "
     "separately as the water mask. Pixels near cloud edges and pixels with "
     "high surface-temperature uncertainty are also excluded."),
    ("3. Scale and derive indices",
     "Convert stored values to physical units: surface reflectance with "
     "SR = DN x 0.0000275 - 0.2, surface temperature with "
     "ST = DN x 0.00341802 + 149.0 (Kelvin), then Celsius. Compute NDVI from "
     "the red and near-infrared bands per scene."),
    ("4. Composite the window",
     "Reduce each year's masked scenes with the median, and record how many "
     "valid observations support each pixel plus the mean temperature "
     "uncertainty. Years with no usable scenes are reported as missing, "
     "never filled."),
    ("5. Summarize on a 1 km grid",
     "Aggregate the 30 m composites to a fixed 1 km grid over the division. "
     "Cells with fewer than two valid observations are marked missing for "
     "that year. Statistics run at the grid scale because the thermal sensor "
     "measures at 100 m natively."),
    ("6. Analyze and validate",
     "Describe per-year patterns, correlate NDVI with LST, fit regression "
     "models with diagnostics, test year-to-year persistence, and compare a "
     "Random Forest against the linear baseline only if pre-stated criteria "
     "are met. Every run is recorded in a manifest for repeat runs."),
]

LIMITATIONS = [
    "Landsat LST is the radiometric temperature of the land surface at about "
    "10:00 local time on clear days. It is not air temperature, not the "
    "temperature a person feels, and not a heat-stress metric.",
    "The late-morning overpass misses the afternoon heat peak and the "
    "nighttime urban heat island, which is often the stronger signal.",
    "Each 100 m thermal pixel averages roofs, streets, trees, and soil into "
    "one value; fine-grained contrasts are lost, and the 30 m product grid "
    "does not mean 30 m independent measurement.",
    "Surface temperature emissivity comes from a static 2000-2008 climatology, "
    "so areas built after 2008 may carry biased emissivity values.",
    "The NDVI-LST association is observational. Built materials, moisture, "
    "distance to the coast, and land use move together with vegetation, so a "
    "correlation does not show that planting cools a given surface.",
    "No claims are made about human heat exposure, health risk, income, or "
    "neighborhood vulnerability from satellite temperature alone.",
]

SOURCE_LINKS = [
    ("USGS: Landsat Collection 2 surface temperature",
     "https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature"),
    ("USGS: Landsat Collection 2 Level-2 science products",
     "https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products"),
    ("Microsoft Planetary Computer STAC (landsat-c2-l2)",
     "https://planetarycomputer.microsoft.com/api/stac/v1"),
    ("Earth Engine catalog: Landsat 8 Collection 2 Level-2",
     "https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2"),
    ("Earth Engine catalog: Landsat 9 Collection 2 Level-2",
     "https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T1_L2"),
    ("GADM administrative boundaries",
     "https://gadm.org/"),
]

QA_RULES = [
    "Keep QA_PIXEL clear bit (bit 6) set and bits 0-5 (fill, dilated cloud, "
    "cirrus, cloud, cloud shadow, snow) unset.",
    "Exclude pixels within 1.0 km of masked cloud (ST_CDIST screen).",
    "Exclude pixels with ST_QA uncertainty above 2.0 K.",
    "Require at least 2 valid scene-level observations per 1 km cell per year.",
    "Admit Tier 1, L2SP, daytime scenes with scene cloud cover at or below 20%.",
]

UNCERTAINTY_TEXT = (
    "Every value shown here rests on a count of clear observations and a mean "
    "temperature uncertainty. Thin cloud, cloud shadow, dust, and the static "
    "emissivity climatology all add error that the QA screens reduce but do not "
    "remove. Treat year-to-year differences smaller than the reported "
    "uncertainty with caution, and check the observation-count layer before "
    "reading much into any single cell."
)
