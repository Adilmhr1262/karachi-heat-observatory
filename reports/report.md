# Karachi Urban Heat and Green Cover Observatory: analytical report

Association only; no causal or health claims.

## 1. Study area and period

The study area is Karachi Division, Sindh, Pakistan, as defined by the GADM 4.1
level-2 boundary (NAME_1=Sindh, NAME_2=Karachi, TYPE_2=Division). The boundary
polygon in EPSG:32642 covers 3,579.8 km2, which is 1.5 percent above the
published division total of 3,527 km2 and inside the 2 percent tolerance set in
the Master Research Protocol v1.0. The analysis period is the pre-monsoon hot
season, 1 May to 30 June, for each year 2015 through 2025.

## 2. Data and access route

All satellite inputs are USGS Landsat Collection 2 Level-2 Tier 1 products
(L2SP), the same products named in the protocol. Because no Google Earth Engine
credentials are available in this environment, the identical products are read
through the Microsoft Planetary Computer STAC API (collection `landsat-c2-l2`),
which serves the same USGS archive files; this amendment is recorded in
`config/study.yaml`. Landsat 8 is used for 2015-2025 and Landsat 9 from 2022.
Landsat 7 scenes present in the collection are excluded by the platform filter,
as are any items whose identifier does not contain L2SP.

Scene selection per year: May-June window, `eo:cloud_cover` below 20 percent,
daytime only (sun elevation above 0), Tier 1, L2SP.

## 3. Processing

Each item is signed immediately before reading (SAS tokens expire). Seven
assets are read: red (SR_B4), nir08 (SR_B5), swir16 (SR_B6), lwir11 (ST_B10),
qa_pixel, qa (ST_QA), and cdist (ST_CDIST). Assets are reprojected into a fixed
30 m EPSG:32642 grid (origin 262830 E, 2838150 N) so every scene aligns.
Scale and offset factors are taken from each asset's `raster:bands` metadata:
surface reflectance 0.0000275/-0.2, surface temperature 0.00341802/149.0,
ST_QA and ST_CDIST 0.01.

Quality masking (QA_PIXEL, CFMASK bits): a pixel is kept when bit 6 (clear) is
set and bits 0-5 (fill, dilated cloud, cirrus, cloud, cloud shadow, snow) are
unset. Bit 7 (water) is tracked separately as the water mask. Two further
screens are applied: ST_CDIST below 1.0 km from masked cloud is dropped, and
ST_QA above 2.0 K uncertainty is dropped. Pixels failing any screen are
excluded from every index.

Per scene: NDVI = (nir - red) / (nir + red); NDBI = (swir - nir) / (swir + nir);
LST in Celsius = lwir11 * 0.00341802 + 149.0 - 273.15. Same-date tiles are
mosaicked (mean of valid values); annual composites are the per-pixel median
across dates, with the valid-observation count, mean ST_QA, and a permanent
water mask (water bit in at least half of the observations, minimum two
observations).

Water-mask investigation: an earlier proof reported 0 percent water-bit pixels
over a window containing sea. Recomputation shows the QA_PIXEL water bit does
flag water (about 2.2 percent of the grid on 2024-05-04, of which 99.8 percent
falls outside the land polygon, i.e. the Arabian Sea). The earlier proof had
counted water bits only among pixels with the clear bit set; water pixels in
Collection 2 generally do not carry the clear bit. The authoritative land mask
is the rasterized GADM boundary; the water-bit mask supplies the coastline for
the distance covariate.

## 4. Grid and covariates

The 30 m composites are summarized on a 1 km grid in EPSG:32642 clipped to the
boundary. One row per cell per year holds the median NDVI, LST, and NDBI, the
median valid-observation count, and the mean ST_QA. A cell-year is kept when it
has at least 100 valid 30 m land pixels and a median of at least 2 valid
observations; otherwise it is absent, not zero-filled.

Covariates: distance to permanent water in km (distance transform of the
all-years permanent-water union, sampled per cell) and elevation in m
(Copernicus DEM GLO-30 via Planetary Computer, per-cell median; null with a
recorded reason if the DEM read fails).

## 5. Statistical methods

H1: per-year Pearson r and Spearman rho between cell NDVI and LST, with 95
percent confidence intervals (Fisher z for Pearson; 1,000 bootstrap replicates
for Spearman).

Pooled model: ordinary least squares of LST on NDVI with year fixed effects,
HC3 heteroskedasticity-consistent standard errors. Headline slope, confidence
interval, R squared, residual Moran's I (queen contiguity on the 1 km lattice,
averaged over years).

H2: NDVI-by-year interaction, F test on the interaction terms.

H4: extended model adding NDBI, distance to coast, and elevation; variance
inflation factors; R squared compared with the NDVI-only pooled model.

H3: hotspot persistence. Hotspot = top LST decile per year; low-vegetation =
bottom NDVI decile per year. Test statistic: cells in the joint set in at
least 3 of the 11 years. Chance model: independent Bernoulli draws per
cell-year at each year's observed joint rate; Monte Carlo p-value (20,000
simulations, fixed seed).

H5 / machine learning: Random Forest enters the conclusions only if all five
pre-registered go/no-go criteria hold: (1) at least about 1,000 cells per year;
(2) all covariates present in every included year; (3) at least 5 percent lower
cross-validated RMSE than the linear baseline on 5 km spatial blocks; (4)
stable permutation-importance rankings across folds; (5) out-of-fold residual
Moran's I no worse than the linear baseline. Random pixel splits are not used.
Permutation importance is reported as association, never causation.

D12 cross-sensor check: separate Landsat 8-only and Landsat 9-only May-June
2022 composites are compared for systematic NDVI and LST offsets.

## 6. Results

### 6.1 Scene inventory and coverage

The STAC query returned 176 Landsat 8/9 Collection 2 Level-2 scenes over
102 distinct dates in the May-June window, 2015-2025. After per-date
processing with the QA screens in Section 3, the usable date counts per
year were: 2015: 7, 2016: 6, 2017: 7, 2018: 7, 2019: 6, 2020: 8, 2021: 8,
2022: 12, 2023: 14, 2024: 15, 2025: 12.

Grid-cell coverage (fraction of the 3,823 land cells meeting the
valid-pixel and observation-count rules) varied by year from 0.01
(2017) to 0.67 (2022). Year 2016 yielded zero grid cells: the ST_QA
screen (Section 7) removed nearly all pixels, and the remaining
observations did not meet the minimum-count rule. Year 2016 is therefore
absent from the analysis. Year 2017 contributed 37 cells.

### 6.2 H1: NDVI-LST association

Per-year Pearson correlations between cell-mean NDVI and cell-mean LST
were: 2015: -0.14 (n=1450), 2017: -0.68 (n=37), 2018: +0.08 (n=2374),
2019: -0.13 (n=632), 2020: -0.04 (n=789), 2021: -0.38 (n=882),
2022: -0.12 (n=2572), 2023: -0.43 (n=1093), 2024: -0.47 (n=877),
2025: -0.20 (n=1857). The association is negative in nine of ten years.

Pooled OLS with year fixed effects (HC3 standard errors, n=12,563)
gives an NDVI slope of -11.28 C per NDVI unit (95% CI: -12.54 to
-10.03), R-squared 0.40. A 0.1 increase in NDVI is associated with
about 1.1 C lower land surface temperature. Residual Moran's I
(queen contiguity, averaged over years) is 0.70, indicating strong
remaining spatial autocorrelation, as expected for 1 km lattice data.

### 6.3 H2: Stability of the NDVI-LST relationship

An F-test of NDVI-by-year interaction terms rejects stability
(p = 4.4e-57). The strength of the NDVI-LST association differs across
years, ranging from near zero to strongly negative. This variation
reflects both interannual differences and the differing spatial
coverage per year (Section 6.1).

### 6.4 Extended model

Adding NDBI, distance to coast, and elevation raises R-squared from
0.40 to 0.54. NDBI carries a positive coefficient (+39.37 C per NDBI
unit), consistent with built-up surfaces running hotter. With NDBI in
the model, the NDVI coefficient attenuates to -0.89, reflecting the
negative correlation between the two indices over this landscape.

### 6.5 H5: Persistence of hot low-vegetation cells

Cells classified as hot with low vegetation in a given year overlap
with the same classification in other years more often than chance:
2,761 cells meet the joint criterion, against 0.123 expected under
independence (permutation p < 0.0001 over 14 year-overlaps).

### 6.6 Machine learning component

The Random Forest was not run. Go/no-go criterion 1 requires about
1000 cells per year; the minimum observed was 37 (2017), and 2016 had
none. The remaining criteria were therefore not assessed. The linear
baseline results in Sections 6.2-6.4 stand as the reported models.

## 7. Diagnostics and sensitivity checks

### 7.1 QA screen attrition

The ST_QA <= 2 K screen was the binding constraint. In 2016 and 2017,
scene-median ST_QA values were 2.28 K and 2.51 K respectively, so the
screen removed 97% or more of otherwise clear pixels. Other years had
scene medians of 1.75-1.90 K and retained 60-67% of clear pixels under
the screen. The cloud-distance (1 km) and cloud-bit screens removed
smaller fractions. This attrition is a property of the input data
quality flags, not a processing choice.

### 7.2 D12 cross-sensor check (2022)

Six Landsat 8 dates and six Landsat 9 dates from May-June 2022 were
composited separately (5.46M common valid 30 m pixels). NDVI offset
(Landsat 9 minus Landsat 8): mean -0.0003, median -0.0003, SD 0.0123.
LST offset: mean +0.26 C, median +1.18 C, SD 3.62 C. The LST comparison
pairs different calendar days, so the SD reflects day-to-day weather
variability in addition to any sensor difference. No systematic NDVI
bias was found. The LST median difference of about +1.2 C for Landsat 9
is noted but not adjusted, given the day-offset confound.

### 7.3 Observation counts

Median valid observations per grid cell per year ranged from 2 to 8.
Years 2022-2025, with both Landsat 8 and 9 active, had the highest
counts. The n_obs >= 2 rule excluded cells with single-observation
coverage, which were common in 2016 and 2017.

### 7.4 Boundary verification (D2)

The rasterized GADM boundary for Karachi Division covers 3,579.8 km2,
within 2% of the published 3,527 km2.

## 8. Limitations

LST here is late-morning land surface temperature from the Landsat
thermal band (native 100 m, resampled to 30 m), not air temperature and
not a heat-exposure metric. No health interpretation is made.

Surface emissivity comes from the static ASTER Global Emissivity
Dataset; changes in surface cover during 2015-2025 are not reflected
in emissivity, which can bias LST trends where land cover changed.

Cloud masking is imperfect near cloud edges despite the 1 km
cloud-distance buffer. Residual contamination is possible.

The May-June window captures the pre-monsoon hot season but not the
full annual cycle. Results do not generalize to other seasons.

Year 2016 is missing from the analysis due to ST_QA screen attrition
(Section 7.1). Year 2017 has only 37 cells. Trend statements rest on
the remaining years with uneven spatial coverage.

The 1 km grid aggregates 30 m pixels; sub-cell heterogeneity is lost.
Cells are absent (not zero-filled) where data did not meet the quality
rules, so maps show data availability rather than full coverage.

## 9. Reproducibility

Configuration: `config/study.yaml` (content hash in the run manifest).
Run manifest: `manifests/run_*.json` (scene IDs, acquisition dates, QA rules,
package versions, output paths). Code: `src/acquisition`, `src/processing`,
`src/analysis`. Unit tests: `tests/test_processing.py`.
