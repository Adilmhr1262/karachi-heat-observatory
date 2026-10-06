"""QA masking and quality screens (protocol Section 12.1, config qa:).

QA_PIXEL bit layout (CFMASK, official GEE/USGS definitions):
  bit 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow,
  5 snow, 6 clear, 7 water.

A pixel is VALID for analysis when: bit 6 is set, bits 0-5 are unset,
it is not water, it is at least `cloud_distance_km` from masked cloud
(ST_CDIST screen), and its ST_QA uncertainty is at most `max_st_qa_kelvin`.
Water pixels (bit 7) are tracked separately for the water mask.
"""
import numpy as np

CLEAR_BIT = 1 << 6
CLOUD_BITS = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
WATER_BIT = 1 << 7


def qa_mask(qa_pixel, cdist_km, stqa_k, cloud_distance_km, max_st_qa_k):
    """Return (valid, water) boolean arrays.

    qa_pixel: int array (NaN already excluded by caller where fill).
    cdist_km: float array, NaN where the ST_CDIST band had nodata.
    stqa_k: float array, NaN where the ST_QA band had nodata.
    """
    qa = qa_pixel.astype(np.int32)
    fill_or_cloud = (qa & CLOUD_BITS) != 0
    clear = (qa & CLEAR_BIT) != 0
    water = ((qa & WATER_BIT) != 0) & ~fill_or_cloud
    far_from_cloud = np.isfinite(cdist_km) & (cdist_km >= cloud_distance_km)
    low_uncertainty = np.isfinite(stqa_k) & (stqa_k <= max_st_qa_k)
    valid = clear & ~fill_or_cloud & ~water & far_from_cloud & low_uncertainty
    return valid, water


def screen_stats(qa_pixel, cdist_km, stqa_k, cloud_distance_km, max_st_qa_k):
    """Diagnostic counts for the water-bit investigation and QA reporting."""
    qa = qa_pixel.astype(np.int32)
    n = qa.size
    out = {
        "n_total": int(n),
        "fill_or_cloud_bits": int(np.sum((qa & CLOUD_BITS) != 0)),
        "clear_bit": int(np.sum((qa & CLEAR_BIT) != 0)),
        "water_bit": int(np.sum(((qa & WATER_BIT) != 0) & ((qa & CLOUD_BITS) == 0))),
        "water_bit_frac": float(
            np.sum(((qa & WATER_BIT) != 0) & ((qa & CLOUD_BITS) == 0)) / n
        ),
        "cdist_valid_frac": float(np.sum(np.isfinite(cdist_km)) / n),
        "stqa_valid_frac": float(np.sum(np.isfinite(stqa_k)) / n),
        "stqa_gt_threshold_frac": float(
            np.sum(np.isfinite(stqa_k) & (stqa_k > max_st_qa_k)) / n
        ),
        "cdist_lt_buffer_frac": float(
            np.sum(np.isfinite(cdist_km) & (cdist_km < cloud_distance_km)) / n
        ),
    }
    return out
