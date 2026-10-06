"""Unit tests for the processing layer: known-value fixtures.

Covers: NDVI formula, surface reflectance scaling, ST scaling,
Kelvin-to-Celsius conversion, and QA_PIXEL bitmask logic
(project verification plan, Table 3).
"""
import numpy as np

from src.processing.indices import ndvi, ndbi, lst_celsius, apply_sr_scaling
from src.processing.masks import qa_mask, CLEAR_BIT, WATER_BIT


def test_ndvi_formula():
    nir = np.array([[0.5, 0.3]], dtype=np.float32)
    red = np.array([[0.2, 0.3]], dtype=np.float32)
    valid = np.array([[True, True]])
    out = ndvi(nir, red, valid)
    assert abs(float(out[0, 0]) - (0.5 - 0.2) / (0.5 + 0.2)) < 1e-6
    assert abs(float(out[0, 1]) - 0.0) < 1e-9
    # invalid pixels are NaN, never 0
    out2 = ndvi(nir, red, np.array([[False, True]]))
    assert np.isnan(out2[0, 0])
    assert out2[0, 1] == np.float32(0.0)


def test_ndvi_range_and_zero_division():
    nir = np.array([[0.0]], dtype=np.float32)
    red = np.array([[0.0]], dtype=np.float32)
    out = ndvi(nir, red, np.array([[True]]))
    assert np.isnan(out[0, 0])  # 0/0 -> NaN, not inf
    out = ndvi(np.array([[0.8]]), np.array([[0.1]]), np.array([[True]]))
    assert -1.0 <= out[0, 0] <= 1.0


def test_ndbi_formula():
    swir = np.array([[0.4]], dtype=np.float32)
    nir = np.array([[0.2]], dtype=np.float32)
    out = ndbi(swir, nir, np.array([[True]]))
    assert abs(float(out[0, 0]) - (0.4 - 0.2) / (0.4 + 0.2)) < 1e-6


def test_sr_scaling():
    # Landsat Collection 2: SR = DN * 0.0000275 - 0.2
    assert apply_sr_scaling(10000.0) == 10000.0 * 0.0000275 - 0.2
    assert abs(apply_sr_scaling(20000.0) - 0.35) < 1e-9


def test_st_scaling_and_kelvin_to_celsius():
    # ST_B10: K = DN * 0.00341802 + 149.0, applied BEFORE Celsius conversion.
    dn = np.array([[40000.0]], dtype=np.float32)
    out = lst_celsius(dn, np.array([[True]]))
    expected_k = 40000.0 * 0.00341802 + 149.0
    assert abs(float(out[0, 0]) - (expected_k - 273.15)) < 1e-3
    # A realistic hot Karachi surface: ~45 C -> K ~ 318.15 -> DN ~ 49487
    dn_hot = (45.0 + 273.15 - 149.0) / 0.00341802
    out_hot = lst_celsius(np.array([[dn_hot]], dtype=np.float32), np.array([[True]]))
    assert abs(float(out_hot[0, 0]) - 45.0) < 0.05


def test_qa_mask_clear_pixel():
    qa = np.array([[CLEAR_BIT]], dtype=np.int32)  # bit 6 only
    valid, water = qa_mask(qa, np.array([[5.0]]), np.array([[1.0]]),
                           cloud_distance_km=1.0, max_st_qa_k=2.0)
    assert valid[0, 0] and not water[0, 0]


def test_qa_mask_cloud_bits_rejected():
    for bit in (1, 2, 3, 4):
        qa = np.array([[CLEAR_BIT | (1 << bit)]], dtype=np.int32)
        valid, _ = qa_mask(qa, np.array([[5.0]]), np.array([[1.0]]),
                           cloud_distance_km=1.0, max_st_qa_k=2.0)
        assert not valid[0, 0], f"bit {bit} should be rejected"
    # fill bit
    qa = np.array([[(1 << 0)]], dtype=np.int32)
    valid, _ = qa_mask(qa, np.array([[5.0]]), np.array([[1.0]]),
                       cloud_distance_km=1.0, max_st_qa_k=2.0)
    assert not valid[0, 0]


def test_qa_mask_water_tracked_separately():
    qa = np.array([[WATER_BIT]], dtype=np.int32)  # water bit, clear bit unset
    valid, water = qa_mask(qa, np.array([[5.0]]), np.array([[1.0]]),
                           cloud_distance_km=1.0, max_st_qa_k=2.0)
    assert water[0, 0] and not valid[0, 0]


def test_qa_mask_cdist_screen():
    qa = np.array([[CLEAR_BIT]], dtype=np.int32)
    # within 1 km of cloud -> excluded
    valid, _ = qa_mask(qa, np.array([[0.5]]), np.array([[1.0]]),
                       cloud_distance_km=1.0, max_st_qa_k=2.0)
    assert not valid[0, 0]
    # cdist nodata -> excluded (cannot verify distance from cloud)
    valid, _ = qa_mask(qa, np.array([[np.nan]]), np.array([[1.0]]),
                       cloud_distance_km=1.0, max_st_qa_k=2.0)
    assert not valid[0, 0]


def test_qa_mask_stqa_screen():
    qa = np.array([[CLEAR_BIT]], dtype=np.int32)
    valid, _ = qa_mask(qa, np.array([[5.0]]), np.array([[2.5]]),
                       cloud_distance_km=1.0, max_st_qa_k=2.0)
    assert not valid[0, 0]
    valid, _ = qa_mask(qa, np.array([[5.0]]), np.array([[np.nan]]),
                       cloud_distance_km=1.0, max_st_qa_k=2.0)
    assert not valid[0, 0]
