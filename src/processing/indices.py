"""Per-scene index derivations (protocol Section 12.3/12.4).

All functions take already-scaled float arrays and a boolean valid mask,
and return float32 arrays with NaN outside the mask. Pure functions, so
they are unit-testable with known-value fixtures.
"""
import numpy as np


def ndvi(nir, red, valid):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (nir - red) / (nir + red)
    out = np.where(valid, out, np.nan).astype(np.float32)
    return out


def ndbi(swir, nir, valid):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (swir - nir) / (swir + nir)
    out = np.where(valid, out, np.nan).astype(np.float32)
    return out


def lst_celsius(lwir11_dn, valid, st_scale=0.00341802, st_offset=149.0):
    """ST_B10 DN -> Kelvin (scale/offset) -> Celsius. Scale applied first."""
    kelvin = lwir11_dn * st_scale + st_offset
    out = np.where(valid, kelvin - 273.15, np.nan).astype(np.float32)
    return out


def apply_sr_scaling(dn, scale=0.0000275, offset=-0.2):
    return dn * scale + offset
