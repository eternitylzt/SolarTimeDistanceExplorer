from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits

from app.data.fits_common import normalize_legacy_solar_header
from app.data.fits_image import FitsImageDataset


def _legacy_header() -> fits.Header:
    """Representative header emitted by older SSW map2fits workflows."""
    header = fits.Header()
    header["CTYPE1"] = "SOLAR-X"
    header["CTYPE2"] = "SOLAR-Y"
    header["CUNIT1"] = "arcsecs"
    header["CUNIT2"] = "arcsecs"
    header["CRPIX1"] = 16.5
    header["CRPIX2"] = 16.5
    header["XCEN"] = 120.0
    header["YCEN"] = -45.0
    header["DX"] = 0.6
    header["DY"] = 0.6
    header["DATE_OBS"] = "2026-01-02T03:04:05.250"
    header["HGLN_OBS"] = 0.0
    header["HGLT_OBS"] = 2.5
    header["DSUN_OBS"] = 1.495978707e11
    header["RSUN_REF"] = 6.957e8
    header["INSTRUME"] = "SSW TEST"
    return header


def test_legacy_map2fits_cards_become_hpc_wcs_and_time(tmp_path: Path) -> None:
    target = tmp_path / "ssw_map2fits.fits"
    fits.PrimaryHDU(np.ones((32, 32), dtype=np.float32), header=_legacy_header()).writeto(target)
    dataset = FitsImageDataset(target, prepare_aia=False)

    assert dataset.times is not None
    assert dataset.times[0].isot == "2026-01-02T03:04:05.250"
    header = dataset.get_header(0)
    assert header["CTYPE1"] == "HPLN-TAN"
    assert header["CTYPE2"] == "HPLT-TAN"
    assert header["CUNIT1"] == "arcsec"
    assert header["CRVAL1"] == 120.0
    assert header["CDELT1"] == 0.6
    smap = dataset.get_map(0)
    assert smap is not None
    assert smap.coordinate_frame.name == "helioprojective"


def test_cd_only_legacy_header_is_normalized_to_pc_cdelt() -> None:
    header = _legacy_header()
    for key in ("DX", "DY"):
        del header[key]
    angle = np.deg2rad(15.0)
    scale = 0.6
    header["CD1_1"] = scale * np.cos(angle)
    header["CD1_2"] = -scale * np.sin(angle)
    header["CD2_1"] = scale * np.sin(angle)
    header["CD2_2"] = scale * np.cos(angle)
    normalized = normalize_legacy_solar_header(header)

    assert "CD1_1" not in normalized
    assert np.isclose(abs(normalized["CDELT1"]), scale)
    assert np.isclose(abs(normalized["CDELT2"]), scale)
    assert all(key in normalized for key in ("PC1_1", "PC1_2", "PC2_1", "PC2_2"))
